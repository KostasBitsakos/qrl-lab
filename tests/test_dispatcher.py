#!/usr/bin/env python3
"""Tests of QRL-Lab v0.3 (dispatcher, failover, peers, index, panel, installer) with fake claude/codex CLIs.

Run from ~/qrl-lab:  .venv/bin/python tests/test_dispatcher.py
No model is called and no token is spent. Everything happens in a temporary directory with a temporary HOME.
"""
import faulthandler
import hashlib
import json
import os
import platform
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
import time
import traceback

KIT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TMP = tempfile.mkdtemp(prefix="qrl-v03-test-")
LAB = os.path.join(TMP, "lab")
FAKE = os.path.join(TMP, "fake")
HOME = os.path.join(TMP, "home")
for sub in ("tools", "dashboard", "docs", ".streamlit", "prompts", "deploy", ".claude"):
    if os.path.exists(os.path.join(KIT, sub)):
        shutil.copytree(os.path.join(KIT, sub), os.path.join(LAB, sub))
for f in ("CLAUDE.md", "AGENTS.md"):
    shutil.copy(os.path.join(KIT, f), os.path.join(LAB, f))
os.makedirs(FAKE)
os.makedirs(HOME)
for cli in ("claude", "codex"):
    w = os.path.join(FAKE, cli)
    with open(w, "w") as fh:
        fh.write(f"#!/bin/sh\nexec {sys.executable} {os.path.join(KIT, 'tests', 'fakes', 'fake_cli.py')} {cli} \"$@\"\n")
    os.chmod(w, os.stat(w).st_mode | stat.S_IEXEC)
os.environ.update(QRL_LAB_DIR=LAB, FAKE_DIR=FAKE, HOME=HOME, QRL_TRANSIENT_WAIT="0",
                  QRL_CLAUDE_BIN=os.path.join(FAKE, "claude"), QRL_CODEX_BIN=os.path.join(FAKE, "codex"))
os.chdir(LAB)
sys.path.insert(0, os.path.join(LAB, "tools"))

from labdb import LabDB, LabError  # noqa: E402
import dispatcher as D  # noqa: E402
import build_md_index  # noqa: E402

PASSED = []
FAILED = []


def ok(name):
    PASSED.append(name)
    print(f"  ok  {name}")


def queue(cli, *steps):
    with open(os.path.join(FAKE, f"{cli}.queue"), "a", encoding="utf-8") as f:
        for s in steps:
            f.write(json.dumps(s) + "\n")


def calls(cli):
    p = os.path.join(FAKE, f"{cli}.calls")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def reset_fakes():
    for fn in os.listdir(FAKE):
        if fn.endswith((".queue", ".calls")):
            os.remove(os.path.join(FAKE, fn))


_OPEN = []


def fresh_dispatcher():
    """A new dispatcher with its own new database file (database files are never deleted while open)."""
    while _OPEN:
        _OPEN.pop().close()
    os.environ["QRL_DISPATCH_DB"] = os.path.join(LAB, ".lab", f"dispatch-{len(PASSED) + len(FAILED)}-"
                                                              f"{time.time_ns()}.db")
    reset_fakes()
    d = D.Dispatcher(LAB)
    _OPEN.append(d)
    return d


def holders(base):
    """Processes that have files under `base` open (Linux /proc), to explain a lock wait."""
    out = []
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            fds = os.listdir(f"/proc/{pid}/fd")
        except OSError:
            continue
        hits = set()
        for fd in fds:
            try:
                target = os.readlink(f"/proc/{pid}/fd/{fd}")
            except OSError:
                continue
            if target.startswith(base):
                hits.add(os.path.basename(target))
        if hits:
            try:
                cmd = open(f"/proc/{pid}/cmdline", "rb").read().replace(b"\0", b" ").decode()[:160]
            except OSError:
                cmd = "?"
            out.append(f"pid {pid} ({'this test' if int(pid) == os.getpid() else cmd}): {sorted(hits)}")
    return out


def watchdog(name, seconds=90):
    """If a test hangs, print every thread's stack and who holds the test files, then stop (no Ctrl+C needed)."""
    def fire():
        print(f"\n!! {name}: no progress for {seconds} s. Diagnostics:", flush=True)
        try:
            for line in holders(TMP):
                print("   open:", line, flush=True)
        except Exception as e:
            print("   (cannot scan /proc:", e, ")", flush=True)
        faulthandler.dump_traceback(all_threads=True)
        os._exit(3)
    t = threading.Timer(seconds, fire)
    t.daemon = True
    t.start()
    return t


def environment():
    def sha(p):
        try:
            return hashlib.sha256(open(p, "rb").read()).hexdigest()
        except OSError:
            return "missing"
    labdb = sha(os.path.join(KIT, "tools", "labdb.py"))
    con = sqlite3.connect(os.path.join(TMP, "probe.db"))
    mode = con.execute("PRAGMA journal_mode=WAL").fetchone()[0]
    con.close()
    print(f"python {platform.python_version()} · sqlite {sqlite3.sqlite_version} · journal_mode on this disk: {mode}"
          f" · labdb.py {'as in v0.2' if labdb == LABDB_V02 else 'CHANGED since v0.2 (' + labdb[:12] + ')'}")


LABDB_V02 = "c6664b7ff8e05d012c589a977c2686a4b0841dd9e9e7b11f9f2654912ff49030"


def prompt_of(call):
    argv = call["argv"]
    if "-p" in argv:
        return argv[argv.index("-p") + 1]
    return argv[-1]


def thread_bodies(db, tid):
    return [m["body"] for m in db.thread(tid)]


# ---------------------------------------------------------------- tests

def test_claude_reply_and_resume():
    d = fresh_dispatcher()
    db = LabDB()
    with open(os.path.join(LAB, "docs", "STATE.md"), "w") as f:
        f.write("# STATE\n## 1. Goal now\n- test goal G-42\n")
    mid = db.researcher_send("Πες μου την κατάσταση.")
    queue("claude", {"mode": "ok", "text": "Όλα καλά.\nSTATUS: done", "session": "sess-1"})
    assert d.once() == "done"
    c = calls("claude")[0]
    argv, p = c["argv"], prompt_of(c)
    assert argv[argv.index("--model") + 1] == "opus" and "--append-system-prompt" in argv
    assert argv[argv.index("--permission-prompts") + 1] == "none" and "--max-budget-usd" in argv
    assert argv[argv.index("--permission-mode") + 1] == "auto" and "--resume" not in argv
    assert argv[argv.index("--output-format") + 1] == "stream-json" and "--verbose" in argv
    lim = d.dd.limits("claude")
    assert lim and lim[0]["window"] == "five_hour" and abs(lim[0]["utilization"] - 0.42) < 1e-9
    assert "5ω 42%" in D.limits_text(d.dd, "claude")
    assert c["env_coord"] == "claude"
    assert "G-42" in p and "## docs/STATE.md" in p and mid in p and p.startswith("[QRL-Lab task")
    bodies = thread_bodies(db, mid)
    assert bodies[-1].startswith("Όλα καλά.") and "— Claude · opus" in bodies[-1] and "STATUS:" not in bodies[-1]
    assert db.message(mid)["status"] == "done"
    t = d.dd.recent_tasks(1)[0]
    assert t["status"] == "done" and abs(t["cost_usd"] - 0.42) < 1e-9 and t["provider"] == "claude"
    journal = open(os.path.join(LAB, "docs", "journal", time.strftime("%Y-%m-%d") + ".md")).read()
    assert mid in journal and "[claude/opus] done" in journal
    # a follow-up in the same thread within the cache TTL resumes the session with a short prompt
    m2 = db.researcher_send("Και τι μένει;", thread_id=mid)
    queue("claude", {"mode": "ok", "text": "Μένει το Χ."})
    assert d.once() == "done"
    c2 = calls("claude")[1]
    assert c2["argv"][c2["argv"].index("--resume") + 1] == "sess-1"
    assert "## docs/STATE.md" not in prompt_of(c2) and m2 in prompt_of(c2)
    # a session whose context grew too large is not resumed
    d.dd.set("resume_max_tokens", "1000")
    db.researcher_send("Τρίτο μήνυμα", thread_id=mid)
    queue("claude", {"mode": "ok", "text": "οκ"})
    assert d.once() == "done"
    assert "--resume" not in calls("claude")[2]["argv"]
    assert d.once() is None  # nothing left: no call
    assert len(calls("claude")) == 3
    ok("Claude answers from STATE.md + thread; resumes while warm; fresh when the context is too big")


def test_failover_on_quota():
    d = fresh_dispatcher()
    db = LabDB()
    mid = db.researcher_send("Ανάλυσε το run R-1.")
    queue("claude", {"mode": "quota"})
    queue("codex", {"mode": "ok", "text": "Ανάλυση από Codex.", "session": "th-9"})
    assert d.once() == "done"
    cx = calls("codex")[0]
    argv, p = cx["argv"], prompt_of(cx)
    assert 'sandbox_mode="workspace-write"' in argv and 'approval_policy="never"' in argv and "-o" in argv
    assert p.startswith("# QRL-Lab coordinator") and "Claude stopped on this task" in p and cx["env_coord"] == "codex"
    st = d.dd.provider("claude")
    assert st["state"] == "exhausted" and 7000 < st["until_ts"] - time.time() < 7300  # resetsAt from the event
    bodies = thread_bodies(db, mid)
    assert any("⚠️ Ο Claude έφτασε το όριο" in b and "Αναλαμβάνει ο Codex" in b for b in bodies)
    assert bodies[-1].startswith("Ανάλυση από Codex.") and "— Codex" in bodies[-1]
    assert db.message(mid)["status"] == "done"
    assert d.dd.session(mid, "codex")["session_id"] == "th-9"
    # while Claude is exhausted, new work goes straight to Codex
    m2 = db.researcher_send("Νέο θέμα")
    queue("codex", {"mode": "ok", "text": "οκ"})
    assert d.once() == "done" and len(calls("claude")) == 1 and len(calls("codex")) == 2
    assert db.message(m2)["status"] == "done"
    ok("Claude usage limit -> same task re-run by Codex, Claude marked exhausted, later work goes to Codex")


def test_both_exhausted_then_resume():
    d = fresh_dispatcher()
    db = LabDB()
    mid = db.researcher_send("Κάτι επείγον")
    queue("claude", {"mode": "quota"})
    queue("codex", {"mode": "quota"})
    assert d.once() == "deferred"
    assert db.message(mid)["status"] == "acknowledged"
    assert sum("⏸" in b for b in thread_bodies(db, mid)) == 1
    assert d.once() is None and d.once() is None  # no repeated calls, no repeated notices
    assert len(calls("claude")) == 1 and len(calls("codex")) == 1
    assert sum("⏸" in b for b in thread_bodies(db, mid)) == 1
    drill = subprocess.run([sys.executable, os.path.join(LAB, "tools", "dispatcher.py"), "exhaust", "claude", "5"],
                           capture_output=True, text=True)
    assert drill.returncode == 0 and "drill" in drill.stdout, drill.stderr
    until = d.dd.provider("codex")["until_ts"]
    assert 7000 < until - time.time() < 7600, until - time.time()  # "in 2 hours 5 minutes"
    d.dd.clear("claude")
    queue("claude", {"mode": "ok", "text": "Έγινε."})
    assert d.once() == "done" and db.message(mid)["status"] == "done"
    ok("both at their limit -> message waits once, no spending; continues when a model is available again")


def test_choice_mention_status_and_errors():
    d = fresh_dispatcher()
    db = LabDB()
    d.dd.set("coordinator", "codex")
    mid = db.researcher_send("Γεια")
    queue("codex", {"mode": "ok", "text": "Γεια από Codex"})
    assert d.once() == "done" and not calls("claude")
    # per-message choice
    m2 = db.researcher_send("@claude: ρώτα τον scholar για CCGrid")
    queue("claude", {"mode": "ok", "text": "Ζήτησα έγκριση.\nSTATUS: waiting_approval"})
    assert d.once() == "done"
    p = prompt_of(calls("claude")[0])
    assert "ρώτα τον scholar" in p and "@claude" not in p and "asked for Claude" in p
    assert db.message(m2)["status"] == "waiting_approval"
    assert "STATUS" not in thread_bodies(db, m2)[-1]
    # a non-quota failure is reported and does not spend the other model's quota
    d.dd.set("coordinator", "claude")
    m3 = db.researcher_send("Σπάσε")
    queue("claude", {"mode": "error", "text": "API Error: 400 bad request"})
    n_codex = len(calls("codex"))
    assert d.once() == "failed" and len(calls("codex")) == n_codex
    assert db.message(m3)["status"] == "failed" and any("❌" in b for b in thread_bodies(db, m3))
    try:
        d.dd.set("coordinator", "gemini")
        raise AssertionError("bad value accepted")
    except LabError:
        pass
    ok("dashboard choice and @mention choose the model; STATUS line sets the status; errors do not fail over")


def test_paid_credits_guard():
    d = fresh_dispatcher()
    db = LabDB()
    mid = db.researcher_send("Μικρή ερώτηση")
    queue("claude", {"mode": "paid", "text": "Απάντηση (με credits)"})
    assert d.once() == "done"
    bodies = thread_bodies(db, mid)
    assert bodies[-2].startswith("Απάντηση (με credits)") and bodies[-1].startswith("ℹ️") and "Codex" in bodies[-1]
    assert d.dd.provider("claude")["state"] == "exhausted"
    d.dd.clear("claude")
    d.dd.set("allow_paid_credits", "1")
    db.researcher_send("Κι άλλη")
    queue("claude", {"mode": "paid", "text": "οκ"})
    assert d.once() == "done" and d.dd.provider("claude")["state"] == "ok"
    # without rate-limit events the error text alone still triggers failover (older CLI versions)
    d.dd.set("allow_paid_credits", "0")
    m3 = db.researcher_send("Τρίτη")
    queue("claude", {"mode": "quota", "no_limits": True, "text": "You've hit your weekly limit · resets Oct 29, 9am (UTC)"})
    queue("codex", {"mode": "ok", "text": "από Codex"})
    assert d.once() == "done" and thread_bodies(db, m3)[-1].startswith("από Codex")
    assert d.dd.provider("claude")["until_ts"] - time.time() > 3600
    ok("paid credits (isUsingOverage) -> later work goes to Codex unless allowed; text-only limit errors detected")


def test_decisions_and_run_events():
    d = fresh_dispatcher()
    db = LabDB()

    def add_run(run_id, req, status):
        db.conn.execute("INSERT INTO runs(run_id, request_id, spec_hash, entry, attempt, name, scope, cmd, cwd, run_dir,"
                        " status, exit_code, created, ended) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (run_id, req, "h", 0, 1, "toy", "sim", "[]", ".", "runs/" + run_id, status, 0,
                         D.now_iso(), D.now_iso()))
    add_run("old-1", "R-old", "done")  # finished before the dispatcher was installed
    root = db.researcher_send("Τρέξε το toy")
    queue("claude", {"mode": "ok", "text": "Κατέθεσα αίτημα."})
    d.once()
    rid = db.ask("approval", "toy run", "σώμα", scope="research", thread_id=root)
    db.decide(rid, "approve", "οκ")
    queue("claude", {"mode": "ok", "text": "Ξεκίνησα."})
    assert d.once() == "done"
    p = prompt_of(calls("claude")[-1])
    assert rid in p and "approved" in p
    assert db.request(rid)["decision_delivered"] == 1 and d.once() is None  # also initializes run events
    # experiment batches: runs that had finished before the first start are not reported; new ones once
    assert d.dd.get("events_initialized") == "1"
    add_run("new-1", rid, "running")
    assert d.once() is None
    db.conn.execute("UPDATE runs SET status='done' WHERE run_id='new-1'")
    queue("claude", {"mode": "ok", "text": "Τα αποτελέσματα: ..."})
    assert d.once() == "done"
    p = prompt_of(calls("claude")[-1])
    assert "new-1" in p and "old-1" not in p and "have ended" in p
    assert d.once() is None
    assert thread_bodies(db, root)[-1].startswith("Τα αποτελέσματα")
    ok("decisions and finished experiment batches wake the coordinator once each (no LLM polling)")


def test_peers():
    d = fresh_dispatcher()
    pid = d.dd.peer_submit("codex", "Κριτική στο σχέδιο Sim v2", key="council-sim", from_provider="claude")
    queue("codex", {"mode": "ok", "text": "Codex critique", "session": "peer-th"})
    req = d.dd.peer_claim()
    assert req["id"] == pid
    D.serve_peer(LAB, req)
    r = d.dd.peer(pid)
    assert r["status"] == "done" and r["answer"] == "Codex critique"
    argv = calls("codex")[0]["argv"]
    assert 'sandbox_mode="read-only"' in argv and "resume" not in argv
    assert prompt_of(calls("codex")[0]).startswith("# QRL-Lab co-researcher request")
    # second round on the same key continues the peer's thread
    pid2 = d.dd.peer_submit("codex", "Και η απάντηση του Claude;", key="council-sim")
    queue("codex", {"mode": "ok", "text": "revised"})
    D.serve_peer(LAB, d.dd.peer_claim())
    assert calls("codex")[1]["argv"][1:3] == ["resume", "peer-th"] and d.dd.peer(pid2)["answer"] == "revised"
    # Codex asks Claude: read-only tools only
    pid3 = d.dd.peer_submit("claude", "Δεύτερη γνώμη", from_provider="codex")
    queue("claude", {"mode": "ok", "text": "Claude view"})
    D.serve_peer(LAB, d.dd.peer_claim())
    a = calls("claude")[0]["argv"]
    assert a[a.index("--tools") + 1] == "Read,Grep,Glob,WebSearch,WebFetch" and "dontAsk" in a
    assert a[a.index("--model") + 1] == "sonnet" and d.dd.peer(pid3)["answer"] == "Claude view"
    # the CLI used by the agents (dispatcher not running -> served inline)
    queue("codex", {"mode": "ok", "text": "inline answer"})
    hb = os.path.join(LAB, ".lab", "bridge_heartbeat")
    if os.path.exists(hb):
        os.utime(hb, (time.time() - 3600, time.time() - 3600))
    out = subprocess.run([sys.executable, os.path.join(LAB, "tools", "ask_peer.py"), "ask", "--prompt", "Γνώμη;"],
                         capture_output=True, text=True, env=dict(os.environ, QRL_COORDINATOR="claude"))
    assert out.returncode == 0 and "inline answer" in out.stdout, (out.stdout, out.stderr)
    ok("ask_peer: Claude<->Codex read-only, topic threads resume, works inline without the dispatcher")


def test_md_index():
    root = os.path.join(TMP, "idx")
    os.makedirs(os.path.join(root, "docs"))
    os.makedirs(os.path.join(root, "exp", "a"))
    os.makedirs(os.path.join(root, ".venv", "lib"))
    open(os.path.join(root, "README.md"), "w").write("# Project\n\nThe main readme of the project.\n")
    open(os.path.join(root, "exp", "a", "notes.md"), "w").write(
        "---\nname: run-notes\ndescription: Notes on run A with reward weights\n---\n# A\nbody\n")
    open(os.path.join(root, "exp", "b.md"), "w").write("```\ncode\n```\n<!-- c -->\n- first bullet line\n")
    open(os.path.join(root, ".venv", "lib", "x.md"), "w").write("# should be skipped\n")
    mem = os.path.join(HOME, ".claude", "projects", os.path.abspath(root).replace(os.sep, "-"), "memory")
    os.makedirs(mem)
    open(os.path.join(mem, "fact.md"), "w").write("# Fact\nClaude remembered this.\n")
    n = build_md_index.build(root)
    idx = open(os.path.join(root, "docs", "INDEX.md")).read()
    assert n == 4, n  # README, notes, b, claude-memory/fact
    assert "Notes on run A with reward weights" in idx and "**run-notes**" in idx
    assert "first bullet line" in idx and ".venv" not in idx and "docs/claude-memory/fact.md" in idx
    assert not build_md_index.is_stale(root)
    time.sleep(0.05)
    open(os.path.join(root, "exp", "c.md"), "w").write("# new\n")
    assert build_md_index.is_stale(root) and build_md_index.build_if_stale(root) == 5
    ok("INDEX.md: one line per .md (front matter or first prose line), skips .venv, mirrors Claude memory")


def test_parse_reset():
    base = time.mktime((2026, 10, 26, 12, 0, 0, 0, 0, -1))
    t = D.parse_reset("You've hit your session limit · resets 3:50pm (Europe/Athens)", base)
    assert t > base
    t2 = D.parse_reset("Try again in 2 hours 5 minutes.", base)
    assert abs(t2 - base - 7500) < 1
    t3 = D.parse_reset("nothing useful", base)
    assert abs(t3 - base - 3600) < 1
    t4 = D.parse_reset("You've hit your weekly limit · resets Oct 29, 9am (UTC)", base)
    assert 2 * 86400 < t4 - base < 4 * 86400, (t4 - base) / 3600
    ok("reset times parsed from Claude and Codex limit messages (fallback: 1 hour)")


def test_panel_and_installer():
    # installer: dry run writes nothing; apply merges and appends once; second apply changes nothing
    inst = [sys.executable, os.path.join(LAB, "tools", "install_v03.py")]
    settings_before = open(os.path.join(LAB, ".claude", "settings.json")).read()
    out = subprocess.run(inst, capture_output=True, text=True, env=dict(os.environ, PATH=FAKE + ":" + os.environ["PATH"]))
    assert out.returncode == 0 and "--apply" in out.stdout, out.stderr
    assert open(os.path.join(LAB, ".claude", "settings.json")).read() == settings_before
    out = subprocess.run(inst + ["--apply"], capture_output=True, text=True,
                         env=dict(os.environ, PATH=FAKE + ":" + os.environ["PATH"]))
    assert out.returncode == 0, out.stderr
    s = json.load(open(os.path.join(LAB, ".claude", "settings.json")))
    before = json.loads(settings_before)
    assert all(e in s["permissions"]["deny"] for e in before["permissions"]["deny"])
    assert "Bash(python3 tools/dispatcher.py set *)" in s["permissions"]["deny"] and s["hooks"] == before["hooks"]
    assert open(os.path.join(LAB, "CLAUDE.md")).read().count("qrl-v0.3 dispatcher") == 1
    assert os.path.exists(os.path.join(HOME, ".codex", "rules", "qrl-lab.rules"))
    unit = open(os.path.join(HOME, ".config", "systemd", "user", "qrl-dispatcher.service")).read()
    assert f"{LAB}/tools/dispatcher.py run" in unit and "{ROOT}" not in unit
    assert os.path.exists(os.path.join(LAB, "docs", "INDEX.md")) and os.path.exists(os.path.join(LAB, "docs", "STATE.md"))
    out = subprocess.run(inst + ["--apply"], capture_output=True, text=True,
                         env=dict(os.environ, PATH=FAKE + ":" + os.environ["PATH"]))
    assert "Τίποτα να αλλάξει" in out.stdout or "docs/INDEX.md" in out.stdout, out.stdout
    assert open(os.path.join(LAB, "dashboard", "app.py")).read().count("qrl-v0.3 coordinator panel") == 1
    try:
        import streamlit.logger
        streamlit.logger.set_log_level("error")  # the dashboard's own warnings are not what this test checks
        from streamlit.testing.v1 import AppTest
    except ImportError:
        ok("installer: dry run, merge-only apply, idempotent (dashboard test skipped: no streamlit)")
        return
    fresh_dispatcher()
    at = AppTest.from_file(os.path.join(LAB, "dashboard", "app.py"), default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    radios = [r for r in at.radio if r.key == "coord_choice"]
    assert radios and radios[0].value == "claude", [r.key for r in at.radio]
    radios[0].set_value("codex").run()
    assert not at.exception, at.exception
    with D.DispatchDB(D.dispatch_db_path(LAB)) as dd:
        assert dd.get("coordinator") == "codex"
    tog = [t for t in at.toggle if t.key == "coord_paused"][0]
    tog.set_value(True).run()
    with D.DispatchDB(D.dispatch_db_path(LAB)) as dd:
        assert dd.get("paused") == "1"
    assert not any("Πάνελ συντονιστή" in w.value for w in at.sidebar.warning)
    ok("installer: dry run, merge-only apply, idempotent; dashboard panel switches coordinator and pause")


def test_edit_freeze():
    d = fresh_dispatcher()
    db = LabDB()
    mid = db.researcher_send("Πρώτο κείμενο")
    db.begin_edit(mid)
    assert db.message(mid)["status"] == "editing"
    assert d.once() is None and not calls("claude")  # skipped while editing
    assert db.save_edit(mid, "Δεύτερο κείμενο") is True
    assert db.message(mid)["status"] == "new"
    queue("claude", {"mode": "ok", "text": "οκ"})
    assert d.once() == "done"
    p = prompt_of(calls("claude")[0])
    assert LabDB.EDIT_NOTE in p and "Δεύτερο κείμενο" in p
    # edit begun while the task runs: the reply is discarded and the message re-queued after the edit
    m2 = db.researcher_send("Τρίτο")
    real = d._run_provider

    def run_and_edit(*a, **k):
        db.begin_edit(m2)
        return real(*a, **k)
    d._run_provider = run_and_edit
    queue("claude", {"mode": "ok", "text": "παλιά απάντηση"})
    d.once()
    d._run_provider = real
    assert db.message(m2)["status"] == "editing"
    assert not any("παλιά απάντηση" in b for b in thread_bodies(db, m2))
    db.cancel_edit(m2)
    assert db.message(m2)["status"] == "new"
    ok("edit freeze: skipped while editing, note on save, running reply discarded")


TESTS = [test_claude_reply_and_resume, test_failover_on_quota, test_both_exhausted_then_resume,
         test_choice_mention_status_and_errors, test_paid_credits_guard, test_decisions_and_run_events, test_peers,
         test_md_index, test_parse_reset, test_panel_and_installer, test_edit_freeze]

if __name__ == "__main__":
    print(f"QRL-Lab v0.3 tests in {TMP}")
    environment()
    try:
        for test in TESTS:
            dog = watchdog(test.__name__)
            try:
                test()
            except Exception:
                FAILED.append(test.__name__)
                print(f"  FAIL {test.__name__}")
                traceback.print_exc()
            finally:
                dog.cancel()
        if FAILED:
            print(f"FAILED {len(FAILED)} of {len(TESTS)}: {', '.join(FAILED)}")
            sys.exit(1)
        print(f"ALL PASSED ({len(PASSED)})")
    finally:
        while _OPEN:
            _OPEN.pop().close()
        shutil.rmtree(TMP, ignore_errors=True)
        sys.stdout.flush()
        # a background thread of the dashboard (AppTest) must not keep the process alive after the verdict
        os._exit(1 if FAILED else 0)
