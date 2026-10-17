#!/usr/bin/env python3
"""Codex as read-only deputy coordinator while Claude is unavailable (usage limit or coordinator down).

Pieces (all pure or injectable, so tests mock the subprocess):
  maybe_file_request(db, health, now)   health_watch calls this; files ONE proposal for the researcher, de-duplicated
  approved_request(db, lab)             the researcher's approval (Decisions tab), never decided here
  pick_messages(db)                     researcher messages (new/delivered) the coordinator has not taken
  build_command / build_prompt          `codex exec` read-only, approval never, gpt-6-sol, medium effort
  handle_message(...)                   take, ask Codex, post the answer, queue it for Claude if it needs execution
  tick(lab)                             health_watch: start the `deputy` tmux window when needed (idempotent)
  main()                                the loop; stops (and posts a note) as soon as health is ok again

Run:  python3 tools/deputy.py          (normally started by health_watch in tmux window `deputy`)
Execution requests from Codex are never executed here: they go to .lab/deputy_queue.jsonl for the coordinator.
"""
import datetime as dt
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from labdb import LabDB, LabError  # noqa: E402
import agent_log  # noqa: E402
import codex_health  # noqa: E402

KIT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TITLE_PREFIX = "Να αναλάβει ο Codex"
DEDUP_SECONDS = 6 * 3600
DOWN_GRACE = 600
TIMEOUT = 600
INTERVAL = float(os.environ.get("QRL_DEPUTY_INTERVAL", "10"))
ACTOR = "codex-deputy"
# Model per message (DECISIONS 2026-10-17): simple/short -> luna, otherwise sol. Both read-only.
SOL_MODEL, SOL_EFFORT = "gpt-6.1-sol", "medium"
LUNA_MODEL, LUNA_EFFORT = "gpt-6-luna", "low"
SIMPLE_MAX_CHARS = 200
COMPLEX_HINTS = ("κώδικ", "code", "sim", "paper", "review", "έλεγξ", "ανάλυσ", "analy", "σχέδι", "design", "plan",
                 "literature", "βιβλιογραφ", "bug", "test", "why", "γιατί")
MODEL_LABEL = "gpt-6.1-sol · αναπληρωτής"  # default / stop note
CODEX_MODEL = SOL_MODEL
CODEX_EFFORT = SOL_EFFORT
MARK = "NEEDS_EXECUTION:"
OUTAGE_STATES = ("limit", "down")
BODY = (
    "Ο Claude (συντονιστής) δεν είναι διαθέσιμος ({state}{reset}). Αν εγκρίνεις, ο Codex αναλαμβάνει προσωρινά σε "
    "ΚΑΤΑΣΤΑΣΗ ΜΟΝΟ-ΑΝΑΓΝΩΣΗΣ: απαντά στα μηνύματά σου στο chat, κάνει έρευνα και σχέδια. Δεν αλλάζει αρχεία, δεν "
    "τρέχει πειράματα, δεν κάνει sudo. Ό,τι χρειάζεται εκτέλεση γράφεται σε ουρά (.lab/deputy_queue.jsonl) και το "
    "παίρνει ο Claude όταν επιστρέψει. Σταματά αυτόματα μόλις ο Claude ξαναδουλέψει."
)


def _ts(s):
    try:
        return dt.datetime.fromisoformat(s).timestamp()
    except (TypeError, ValueError):
        return 0.0


def _read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, path)


def deputy_requests(db):
    return [r for r in db.requests(limit=500) if r["title"].startswith(TITLE_PREFIX)]


def maybe_file_request(db, health, now=None):
    """File one deputy proposal when the coordinator is limited, or down for more than 10 min. Returns id or None."""
    now = time.time() if now is None else now
    state = health.get("state")
    if state == "limit":
        pass
    elif state == "down" and now - (health.get("since") or now) > DOWN_GRACE:
        pass
    else:
        return None
    for r in deputy_requests(db):
        if r["state"] == "open":
            return None
        if now - max(_ts(r["ts"]), _ts(r["decided_at"])) < DEDUP_SECONDS:
            return None
    reset = (health.get("detail") or "").strip()
    title = f"{TITLE_PREFIX} μέχρι {reset or 'να ξαναδουλέψει ο Claude'};"
    body = BODY.format(state="όριο χρήσης" if state == "limit" else "δεν τρέχει",
                       reset=f", επαναφορά {reset}" if reset else "")
    try:
        return db.ask("proposal", title, body, author="system", scope="other", options=["approve", "reject"])
    except LabError:
        return None


def approved_request(db, lab):
    """The newest approved, not yet consumed deputy request, or None."""
    consumed = set(_read_json(os.path.join(lab, "deputy_state.json"), {}).get("consumed", []))
    for r in deputy_requests(db):  # newest first
        if r["state"] == "approved" and r["id"] not in consumed:
            return r
    return None


def pick_messages(db):
    """Researcher messages nobody took yet (new/delivered), oldest first."""
    return [m for m in db.researcher_open() if m["status"] in ("new", "delivered")]


def choose_model(thread):
    """(model, effort) for the researcher's last message: short and without complexity hints -> luna, else sol."""
    last = ""
    for m in thread:
        if m.get("author") == "researcher":
            last = m.get("body") or ""
    low = last.lower()
    if last and len(last) <= SIMPLE_MAX_CHARS and last.count("\n") < 3 and not any(h in low for h in COMPLEX_HINTS):
        return LUNA_MODEL, LUNA_EFFORT
    return SOL_MODEL, SOL_EFFORT


def build_prompt(agents_md, thread):
    lines = []
    for m in thread:
        lines.append(f"[{m['id']} · {m['author']} · {m['kind']}]\n{m['body']}")
    return (
        f"{agents_md}\n\n---\nYou are the READ-ONLY deputy coordinator of QRL-Lab while Claude is unavailable. "
        "Read docs/PLAN.md if needed. Never read or print secrets (.env, ~/.ssh, tokens, credentials). "
        "You may delegate simple sub-tasks (lookups, summaries, formatting) to gpt-6-luna; keep the important reasoning "
        "on gpt-6.1-sol. You stay read-only either way. "
        "Answer the researcher's last message in Greek, under 300 words, short and direct, with file pointers. "
        "If answering well requires execution (editing files, code changes, running anything, sudo, kubectl, "
        "starting runs), do not attempt it: say what is needed and end your answer with a final line "
        f"'{MARK} yes'. Otherwise end with '{MARK} no'.\n\n--- THREAD ---\n" + "\n\n".join(lines))


def build_command(out_file, cwd=KIT, model=CODEX_MODEL, effort=CODEX_EFFORT):
    return ["codex", "exec", "--sandbox", "read-only", "-c", 'approval_policy="never"',
            "-c", f'model_reasoning_effort="{effort}"', "-m", model, "-C", cwd,
            "--skip-git-repo-check", "--ephemeral", "-o", out_file, "-"]


def parse_answer(text):
    """Split Codex's text into (answer, needs_execution)."""
    lines = (text or "").rstrip().splitlines()
    needs = False
    if lines and lines[-1].strip().upper().startswith(MARK):
        needs = lines[-1].split(":", 1)[1].strip().lower().startswith("y")
        lines = lines[:-1]
    return "\n".join(lines).strip(), needs


def queue_append(lab, entry):
    with open(os.path.join(lab, "deputy_queue.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def handle_message(db, lab, mid, run=subprocess.run, now=None):
    """Take one message, run Codex read-only, post the answer. Returns "done" or "queued"."""
    import tempfile
    m, thread = db.take(mid, actor=ACTOR)
    with open(os.path.join(KIT, "AGENTS.md"), encoding="utf-8") as f:
        agents = f.read()
    prompt = build_prompt(agents, thread)
    model, effort = choose_model(thread)
    label = f"{model} · αναπληρωτής"
    out = tempfile.mktemp(prefix="deputy-", suffix=".txt")
    log_id = agent_log.start("codex-deputy", model, effort, f"deputy reply to {mid}", m["thread_id"])
    answer, needs, err = "", False, ""
    try:
        r = run(build_command(out, model=model, effort=effort), input=prompt, capture_output=True, text=True,
                timeout=TIMEOUT, cwd=KIT)
        if r.returncode == 0 and os.path.exists(out):
            with open(out, encoding="utf-8") as f:
                answer, needs = parse_answer(f.read())
            codex_health.mark_ok(lab)
        else:
            err = f"codex exit {r.returncode}"
            if codex_health.record(getattr(r, "stdout", "") or "", getattr(r, "stderr", "") or "", lab=lab):
                err += " (όριο χρήσης Codex)"
    except subprocess.TimeoutExpired:
        err = f"timeout {TIMEOUT}s"
    except OSError as e:
        err = f"{type(e).__name__}: {e}"
    finally:
        if os.path.exists(out):
            os.remove(out)
    agent_log.end(log_id, "failed" if (err or not answer) else "done")
    if err or not answer:
        needs, answer = True, f"Ο αναπληρωτής Codex δεν κατάφερε να απαντήσει ({err or 'κενή απάντηση'})."
    if needs:
        answer += "\n\n_(σε ουρά για τον Claude)_"
    db.post("codex", answer, mid, kind="reply", model=label, set_status="waiting_approval" if needs else "done")
    if needs:
        queue_append(lab, {"ts": time.time() if now is None else now, "message": mid, "thread": m["thread_id"],
                           "reason": err or "needs execution", "answer": answer[:2000]})
    return "queued" if needs else "done"


def stop_note(db, lab, handled):
    for mid in handled:
        try:
            db.post("codex", "Ο Claude επέστρεψε· ο αναπληρωτής Codex σταματά. Ό,τι χρειάζεται εκτέλεση είναι στην ουρά.",
                    mid, kind="status", model=MODEL_LABEL)
        except LabError:
            pass


def cycle(db, lab, health, run=subprocess.run):
    """One loop iteration. Returns "stop" when the deputy should exit, else the number of messages handled."""
    st_path = os.path.join(lab, "deputy_state.json")
    st = _read_json(st_path, {})
    req = approved_request(db, lab)
    if req is None:
        return "stop"
    if health.get("state") not in OUTAGE_STATES:
        if st.get("handled"):
            stop_note(db, lab, st["handled"])
        st["consumed"] = st.get("consumed", []) + [req["id"]]
        st["handled"] = []
        _write_json(st_path, st)
        return "stop"
    n = 0
    for m in pick_messages(db):
        handle_message(db, lab, m["id"], run=run)
        st.setdefault("handled", []).append(m["id"])
        _write_json(st_path, st)
        n += 1
    return n


def tick(lab, session="lab", window="deputy"):
    """health_watch hook: file the request when due and start the deputy window when approved. Idempotent."""
    health = _read_json(os.path.join(lab, "health.json"), {})
    db = LabDB(os.path.join(lab, "lab.db"))
    try:
        maybe_file_request(db, health)
        if health.get("state") in OUTAGE_STATES and approved_request(db, lab) is not None:
            r = subprocess.run(["tmux", "list-windows", "-t", session, "-F", "#W"], capture_output=True, text=True,
                               timeout=10)
            if r.returncode == 0 and window not in r.stdout.split():
                subprocess.run(["tmux", "new-window", "-d", "-t", session, "-n", window, "-c", KIT,
                                "python3 tools/deputy.py; exec bash"], timeout=10)
    finally:
        db.close()


def main():
    from labdb import lab_dir
    lab = lab_dir(os.environ.get("QRL_LAB_DIR") or KIT)
    db = LabDB(os.path.join(lab, "lab.db"))
    print("deputy: started", flush=True)
    while True:
        try:
            if cycle(db, lab, _read_json(os.path.join(lab, "health.json"), {})) == "stop":
                print("deputy: stopping", flush=True)
                return
        except Exception as e:
            print(f"deputy warning: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
