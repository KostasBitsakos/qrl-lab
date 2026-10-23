#!/usr/bin/env python3
"""Codex acting deputy coordinator while Claude is unavailable (usage limit or coordinator down).

Pieces (all pure or injectable, so tests mock the subprocess):
  maybe_file_request(db, health, now)   health_watch calls this; files ONE proposal for the researcher, de-duplicated
  approved_request(db, lab)             the researcher's approval (Decisions tab), never decided here
  pick_messages(db)                     researcher messages (new/delivered) the coordinator has not taken
  build_command / build_prompt          `codex exec` workspace-write, existing project approval rules
  handle_message(...)                   take, execute approved work, post the answer and a Claude handoff
  tick(lab)                             health_watch: start the `deputy` tmux window when needed (idempotent)
  main()                                the loop; stops (and posts a note) as soon as health is ok again

Run:  python3 tools/deputy.py          (normally started by health_watch in tmux window `deputy`)
Project edits are allowed; experiments and privileged actions retain their existing approval gates.
"""
import datetime as dt
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from labdb import LabDB, LabError, CODEX_MODELS, CODEX_MODEL_EFFORTS  # noqa: E402
import agent_log  # noqa: E402
import codex_health  # noqa: E402

KIT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TITLE_PREFIX = "Να αναλάβει ο Codex"
DEDUP_SECONDS = 6 * 3600
DOWN_GRACE = 600
TIMEOUT = 600
INTERVAL = float(os.environ.get("QRL_DEPUTY_INTERVAL", "10"))
ACTOR = "codex-deputy"
# Automatic routing stays economical; explicit researcher choices take precedence.
SOL_MODEL, SOL_EFFORT = "gpt-6.1-sol", "medium"
LUNA_MODEL, LUNA_EFFORT = "gpt-6-luna", "low"
SIMPLE_MAX_CHARS = 200
COMPLEX_HINTS = ("κώδικ", "code", "sim", "paper", "review", "έλεγξ", "ανάλυσ", "analy", "σχέδι", "design", "plan",
                 "literature", "βιβλιογραφ", "bug", "test", "why", "γιατί")
MODEL_LABEL = "codex-deputy · αναπληρωτής"  # No model is inferred when no action was recorded.
CODEX_MODEL = SOL_MODEL
CODEX_EFFORT = SOL_EFFORT
MARK = "NEEDS_EXECUTION:"
APPROVAL_MARK = "NEEDS_APPROVAL:"
OUTAGE_STATES = ("limit", "down")
BODY = (
    "Ο Claude (συντονιστής) «κοιμάται» ({state}{reset}). Αν εγκρίνεις, ο Codex αναλαμβάνει ΠΛΗΡΗ συντονισμό με δικαίωμα "
    "εγγραφής μέσα στο ~/qrl-lab (κανόνες: docs/rules/handoff.md): απαντά, εκτελεί, τρέχει εγκεκριμένα πειράματα "
    "μέσω launch_run.py, αλλάζει κώδικα ΜΟΝΟ σε νέα single-purpose branches, κρατά αναλυτικές σημειώσεις για κοινό review, "
    "και χρησιμοποιεί πράκτορες με την ισχύ που ορίζουν οι υπάρχοντες κανόνες. Sudo, πραγματικό cluster, QPU και νέες "
    "εγκρίσεις budget παραμένουν υποχρεωτικές. Όταν ο Claude «ξυπνήσει», κάνουν μαζί review και αποφασίζουν τα merges."
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
    """Honor this message's selection; legacy Claude choices map to bounded Codex equivalents."""
    last, request = "", {}
    for m in thread:
        if m.get("author") == "researcher":
            last = m.get("body") or ""
            request = m
    low = last.lower()
    if last and len(last) <= SIMPLE_MAX_CHARS and last.count("\n") < 3 and not any(h in low for h in COMPLEX_HINTS):
        model, effort = LUNA_MODEL, LUNA_EFFORT
    else:
        model, effort = SOL_MODEL, SOL_EFFORT
    selected = request.get("req_model")
    if isinstance(selected, str) and selected.startswith("coordinator:"):
        selected = selected[len("coordinator:"):]
    legacy = {"haiku": (LUNA_MODEL, LUNA_EFFORT), "sonnet": (SOL_MODEL, SOL_EFFORT),
              "opus": ("gpt-6-astra", "high"),
              "claude-haiku-5-5": (LUNA_MODEL, LUNA_EFFORT), "claude-sonnet-5-5": (SOL_MODEL, SOL_EFFORT),
              "claude-opus-5-5": ("gpt-6-astra", "high"), "claude-fable-5-1": (SOL_MODEL, SOL_EFFORT)}
    if selected in legacy:
        model, effort = legacy[selected]
    elif selected in CODEX_MODELS:
        model = selected
        effort = "low" if model.endswith("luna") else ("high" if model == "gpt-6-astra" else "medium")
    elif selected not in (None, "", "codex"):
        raise LabError(f"Unknown deputy model: {selected}")
    requested_effort = request.get("req_effort")
    if requested_effort:
        effort = "medium" if requested_effort == "med" else requested_effort
        if effort == "ultra" and selected in (None, "", "codex") and model.endswith("luna"):
            model = SOL_MODEL  # Automatic routing must choose a model supporting the requested effort.
    validate_routing(model, effort)
    return model, effort


def validate_routing(model, effort):
    if model not in CODEX_MODELS or effort not in CODEX_MODEL_EFFORTS[model]:
        raise LabError("Unsupported Codex model or effort.")


def build_prompt(agents_md, thread):
    lines = []
    for m in thread:
        lines.append(f"[{m['id']} · {m['author']} · {m['kind']}]\n{m['body']}")
    return (
        f"{agents_md}\n\n---\nYou are the acting Codex deputy coordinator of QRL-Lab while Claude is unavailable. "
        "This is approved implementation work for the researcher's requested task inside ~/qrl-lab. "
        "Read CLAUDE.md, docs/PLAN.md sections 1, 2 and 6, and relevant docs/rules before acting. "
        "You may edit project tools, dashboard and docs within the task scope, run focused checks, and complete "
        "ordinary approved execution work. Honor the researcher's per-message model/effort. Automatic routing "
        "is bounded to gpt-6-luna/low for simple work and gpt-6.1-sol/medium otherwise; do not launch other agents "
        "without an explicit delegation request. Never read or print secrets (.env, ~/.ssh, tokens, credentials). "
        "Never modify experiments, model code, run configs, live drivers or results without explicit task-specific "
        "approval. All experiment launches MUST use tools/launch_run.py with its matching approved frozen spec; "
        "never bypass approval checks, forge decisions, edit approval records/specs, or run training directly. "
        "Sudo, changes outside qrl-lab, real-cluster mutations, QPU jobs, git push and publishing require their "
        "existing explicit approvals. Do not run sudo, kubectl mutations or QPU jobs here. "
        "Report changed paths, checks, remaining work and any approval needed so Claude can resume. "
        "Answer the researcher's last message in Greek, under 300 words, short and direct, with file pointers. "
        "Address the researcher as Κώστα. Complete authorized work now. If an existing approval boundary blocks "
        f"remaining work, explain precisely and end with '{APPROVAL_MARK} yes'; otherwise end with "
        f"'{APPROVAL_MARK} no'.\n\n--- THREAD ---\n" + "\n\n".join(lines))


def codex_bin():
    """Find executable CLI and its Node runtime even in the watchdog's clean PATH."""
    def versions(path):
        return tuple(int(n) for n in re.findall(r"\d+", path))
    bins = sorted(glob.glob(os.path.expanduser("~/.nvm/versions/node/*/bin")), key=versions, reverse=True)
    candidates = [shutil.which("codex")] + [os.path.join(d, "codex") for d in bins]
    for path in candidates:
        if not path or not os.path.isfile(path) or not os.access(path, os.X_OK):
            continue
        # The npm CLI uses /usr/bin/env node; prefer the Node installed beside it.
        dirs = [os.path.dirname(os.path.abspath(path))] + bins
        for directory in dirs:
            node = os.path.join(directory, "node")
            if os.path.isfile(node) and os.access(node, os.X_OK):
                os.environ["PATH"] = directory + os.pathsep + os.environ.get("PATH", "")
                return os.path.abspath(path)
        if shutil.which("node"):
            return os.path.abspath(path)
    raise FileNotFoundError("Codex CLI or Node.js runtime not found; restore the project Codex/nvm installation and retry")


def build_command(out_file, cwd=KIT, model=CODEX_MODEL, effort=CODEX_EFFORT):
    validate_routing(model, effort)
    return [codex_bin(), "exec", "--sandbox", "workspace-write", "-c", 'approval_policy="never"',
            "-c", f'model_reasoning_effort="{effort}"', "-m", model, "-C", cwd,
            "--skip-git-repo-check", "--ephemeral", "-o", out_file, "-"]


def parse_answer(text):
    """Split Codex's text into (answer, needs_approval); accept the historical marker too."""
    lines = (text or "").rstrip().splitlines()
    needs = False
    if lines and lines[-1].strip().upper().startswith((APPROVAL_MARK, MARK)):
        needs = lines[-1].split(":", 1)[1].strip().lower().startswith("y")
        lines = lines[:-1]
    return "\n".join(lines).strip(), needs


def queue_append(lab, entry):
    with open(os.path.join(lab, "deputy_queue.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def write_handoff(lab, entry):
    """Append an outcome for every action, including failed/retryable Codex calls."""
    with open(os.path.join(lab, "deputy_handoff.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    with open(os.path.join(lab, "deputy_handoff.md"), "a", encoding="utf-8") as f:
        f.write(f"\n## {entry['message']} — {entry['status']}\n\n"
                f"Role: {entry['role']}; model: {entry['model']}; effort: {entry['effort']}.\n"
                f"Task: {entry['task']}\n\n{entry['answer']}\n\n"
                f"Next: {entry['next_action']}\n")


def handle_message(db, lab, mid, run=subprocess.run, now=None):
    """Act on one message within project rules. Failures are retryable, never Claude-only execution queues."""
    import tempfile
    m, thread = db.take(mid, actor=ACTOR)
    # Only context through this message belongs to its task; a simultaneous follow-up stays pending.
    thread = thread[:next(i for i, item in enumerate(thread) if item["id"] == mid) + 1]
    with open(os.path.join(KIT, "AGENTS.md"), encoding="utf-8") as f:
        agents = f.read()
    prompt = build_prompt(agents, thread)
    routing_error = ""
    try:
        # A newer message in this thread must not replace the selection of the message being handled.
        model, effort = choose_model([m])
    except LabError as e:
        model, effort, routing_error = SOL_MODEL, SOL_EFFORT, str(e)
    label = f"{model} · {effort} · αναπληρωτής"
    task = f"{mid}: {m['body'][:120]}".replace("\n", " ")
    metadata = {"role": ACTOR, "model": model, "effort": effort, "task": task,
                "message": mid, "thread": m["thread_id"],
                "req_model": m.get("req_model"), "req_effort": m.get("req_effort")}
    log_id = agent_log.start(ACTOR, model, effort, task, m["thread_id"])
    db.record_agent_action(ACTOR, "deputy_start", mid, metadata)
    db.set_status(mid, "in_progress", actor=ACTOR)
    fd, out = tempfile.mkstemp(prefix="deputy-", suffix=".txt")
    os.close(fd)
    answer, needs, err = "", False, routing_error
    try:
        if not err:
            r = run(build_command(out, model=model, effort=effort), input=prompt, capture_output=True, text=True,
                    timeout=TIMEOUT, cwd=KIT)
            if r.returncode == 0 and os.path.exists(out):
                with open(out, encoding="utf-8") as f:
                    answer, needs = parse_answer(f.read())
                if answer:
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
    if err or not answer:
        needs = False
        status = "failed"
        answer = (f"Κώστα, ο αναπληρωτής Codex δεν ολοκλήρωσε την εργασία ({err or 'κενή απάντηση'}). "
                  "Η εργασία παραμένει ανολοκλήρωτη· μπορείς να ζητήσεις νέα προσπάθεια από τον Codex "
                  "μετά την αποκατάσταση του CLI/Node ή του ορίου χρήσης. Η παράδοση έχει καταγραφεί.")
    else:
        status = "waiting_approval" if needs else "done"
    db.post("codex", answer, mid, kind="reply", model=label, set_status=status)
    next_action = ("Researcher approval required; review the precise boundary in the reply." if needs else
                   "Retry with Codex after resolving the reported failure." if status == "failed" else
                   "Claude: review the reported changes/checks and continue any stated remaining work.")
    entry = {**metadata, "ts": time.time() if now is None else now, "status": status,
             "reason": err or ("approval required" if needs else "completed"),
             "answer": answer[:2000], "next_action": next_action}
    write_handoff(lab, entry)
    if needs:
        queue_append(lab, entry)
    db.record_agent_action(ACTOR, "deputy_end", mid, entry)
    agent_log._append({"hook_event_name": "SubagentStop", "agent_id": log_id, "agent_type": ACTOR,
                       **metadata, "status": "failed" if status == "failed" else "done", "ts": entry["ts"]})
    return status


def stop_note(db, lab, handled):
    for mid in handled:
        try:
            label = next((m["model"] for m in reversed(db.thread(db.message(mid)["thread_id"]))
                          if m["author"] == "codex" and m.get("model")), MODEL_LABEL)
            db.post("codex", "Ο Claude επέστρεψε· ο αναπληρωτής Codex σταματά. Οι ενέργειες και τα εκκρεμή "
                    "βήματα έχουν καταγραφεί στο ~/qrl-lab/.lab/deputy_handoff.md.",
                    mid, kind="status", model=label)
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
