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
from unittest.mock import patch

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
# Hermetic knowledge sources: convo_context.relevant() reads these; the real docs must not leak into prompts.
os.makedirs(os.path.join(LAB, "docs"), exist_ok=True)
for _f, _txt in (("DECISIONS.md", "# Decisions (test fixture)\n"), ("researcher_requirements.md", "# Requirements (test fixture)\n"),
                 ("index.json", "[]")):
    with open(os.path.join(LAB, "docs", _f), "w", encoding="utf-8") as _fh:
        _fh.write(_txt)
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
import work as W  # noqa: E402
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
    d.dd.set("governor_enabled", "0")  # mechanics tests run without usage data; the governor has its own tests
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
    assert bodies[-1].startswith("Κώστα,\n\nΌλα καλά.") and "— Claude · opus" in bodies[-1] and "STATUS:" not in bodies[-1]
    assert bodies[-1].count("— Πάρις") == 1
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
    assert bodies[-1].startswith("Κώστα,\n\nΑνάλυση από Codex.") and "— Codex" in bodies[-1]
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
    assert f"labq.py show {m2}" not in p  # regression: the current message is never its own «memory» pointer
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
    assert bodies[-2].startswith("Κώστα,\n\nΑπάντηση (με credits)") and bodies[-1].startswith("Κώστα,\n\nℹ️") and "Codex" in bodies[-1]
    assert "όχι γνωστό reset" in bodies[-1] and bodies[-1].count("— Πάρις") == 1
    assert d.dd.provider("claude")["state"] == "exhausted"
    d.dd.clear("claude")
    d.dd.set("allow_paid_credits", "1")
    db.researcher_send("Κι άλλη")
    queue("claude", {"mode": "paid", "text": "οκ"})
    assert d.once() == "done" and d.dd.provider("claude")["state"] == "ok"
    # without rate-limit events the error text alone still triggers failover (older CLI versions)
    d.dd.set("allow_paid_credits", "0")
    m3 = db.researcher_send("Τρίτη")
    queue("claude", {"mode": "quota", "no_limits": True, "text": "You've hit your weekly limit. Try again in 2 hours 5 minutes."})
    queue("codex", {"mode": "ok", "text": "από Codex"})
    assert d.once() == "done" and thread_bodies(db, m3)[-1].startswith("Κώστα,\n\nαπό Codex")
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
    n_claude = len(calls("claude"))
    assert d.once() is None, "a clean batch is summarised by a script: no coordinator task"   # B3
    assert len(calls("claude")) == n_claude
    body = open(os.path.join(d.root, ".lab", "technical.log"), encoding="utf-8").read()   # F3: technical log
    assert "new-1" in body and "old-1" not in body and "[run-summary " in body
    assert d.once() is None and open(os.path.join(d.root, ".lab", "technical.log"), encoding="utf-8").read() == body
    add_run("new-2", rid, "failed")                      # a failed batch still wakes the coordinator, once
    db.conn.execute("UPDATE runs SET exit_code=1 WHERE run_id='new-2'")
    queue("claude", {"mode": "ok", "text": "Τα αποτελέσματα: ..."})
    assert d.once() == "done"
    p = prompt_of(calls("claude")[-1])
    assert "new-2" in p and "old-1" not in p and "have ended" in p
    assert d.once() is None
    ok("decisions wake the coordinator once; clean batches get a script summary, failed ones wake the coordinator once")


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
    db.set_status(m2, "done")  # the lab db is shared with later tests
    ok("edit freeze: skipped while editing, note on save, running reply discarded")


def test_headless_permission_roundtrip():
    import perm_store
    d = fresh_dispatcher()
    db = LabDB()
    for f in os.listdir(perm_store.perm_dir(LAB)):
        os.remove(os.path.join(perm_store.perm_dir(LAB), f))
    mid = db.researcher_send("Τρέξε κάτι")
    queue("claude", {"mode": "ok", "text": "μπλοκαρίστηκα", "denials": [{"tool_name": "Bash", "tool_input": {"command": "ls /etc"}}]})
    assert d.once() == "done"
    pend = perm_store.pending(LAB)
    assert len(pend) == 1 and pend[0]["source"] == "headless" and pend[0]["detail"] == "ls /etc"
    assert d.once() is None  # still unanswered: nothing to deliver
    perm_store.decide(pend[0]["id"], True, root=LAB)
    queue("claude", {"mode": "ok", "text": "ξαναδοκιμάζω"})
    assert d.once() == "done"
    p = prompt_of(calls("claude")[-1])
    assert "ls /etc" in p and "APPROVED" in p
    assert d.once() is None and not perm_store.undelivered_answers(LAB)
    ok("headless permission denial -> pending entry -> answer delivered once with the next task")



# ---------------------------------------------------------------- v0.4: parallel work

WORK = f"{sys.executable} {os.path.join(LAB, 'tools', 'work.py')}"


def wait_until(cond, timeout=20.0, what="condition"):
    t_end = time.time() + timeout
    while time.time() < t_end:
        if cond():
            return
        time.sleep(0.1)
    raise AssertionError(f"timeout waiting for {what}")


def live(d):
    """A dispatcher prepared for tick() (the non-blocking step of run_forever), without the infinite loop."""
    d._busy, d._busy_lock = {}, threading.Lock()
    return d


def alive_lanes(d):
    with d._busy_lock:
        return sorted(lane for lane, t in d._busy.values() if t.is_alive())


def drain(d, timeout=30.0):
    t_end = time.time() + timeout
    while time.time() < t_end:
        d.tick()
        if not alive_lanes(d) and d.find_work() is None:
            return
        time.sleep(0.1)
    raise AssertionError("work did not drain")


def test_work_board():
    d = fresh_dispatcher()
    w = d.work
    a = w.create("worker", "spawn", "A: plots", "make figure 3", reply_to="M-x", status="running")
    b = w.create("worker", "spawn", "B: text", "rewrite section 2", reply_to="M-x", status="running")
    assert a.startswith("J") and b.startswith("J") and a != b
    assert w.claim(a, ["paper/sec2.tex", "tools/"]) == []
    conflicts = w.claim(b, ["paper/fig3.py", "paper/sec2.tex"])  # all or nothing
    assert [c["job"] for c in conflicts] == [a] and not w.claims(b)
    assert w.claim(b, ["tools/plot.py"])[0]["path"] == "tools"  # a directory claim covers its files
    assert w.claim(b, ["paper/fig3.py"]) == []
    try:
        w.claim(b, ["../outside.txt"])
        raise AssertionError("a path outside the lab was accepted")
    except LabError:
        pass
    # negotiation: messages, read once; unread messages of a finished job go back to the sender
    w.say(b, a, "I need sec2.tex lines 10-20")
    assert [m["body"] for m in w.inbox(a)] == ["I need sec2.tex lines 10-20"] and w.inbox(a) == []
    w.say(a, b, "ok after my commit")
    w.set_status(b, "done")
    w.finish(b)
    assert not w.claims(b)
    back = w.inbox(a)
    assert back and back[0]["from_job"] == "dispatcher" and "without reading" in back[0]["body"]
    # a finished job's claims never block: B's paths are free for A
    assert w.claim(a, ["paper/fig3.py"]) == []
    # the CLI: workers cannot spawn; the chat coordinator can; conflicts exit 2 and show the holder's goal
    env = dict(os.environ, QRL_JOB=b)
    out = subprocess.run(WORK.split() + ["spawn", "--title", "x", "--brief", "y"], capture_output=True, text=True,
                         env=env)
    assert out.returncode != 0 and "Only the chat coordinator" in out.stderr
    c = w.create("chat", "message", "chat", reply_to="M-x", status="running")
    assert c.startswith("C")
    out = subprocess.run(WORK.split() + ["spawn", "--title", "Fig 4", "--brief", "plot fig 4", "--to", "codex"],
                         capture_output=True, text=True, env=dict(os.environ, QRL_JOB=c))
    assert out.returncode == 0, out.stderr
    spawned = w.queued_spawns()
    assert len(spawned) == 1 and spawned[0]["provider"] == "codex" and spawned[0]["reply_to"] == "M-x"
    d2 = w.create("worker", "spawn", "D", "edit fig 3 colours", reply_to="M-x", status="running")
    out = subprocess.run(WORK.split() + ["claim", "paper/fig3.py"], capture_output=True, text=True,
                         env=dict(os.environ, QRL_JOB=d2))
    assert out.returncode == 2 and "CONFLICT" in out.stdout and a in out.stdout and "make figure 3" in out.stdout
    # commit: only the claimed files of this job, never the other job's uncommitted work
    w.release(a, ["tools"])
    subprocess.run(["git", "init", "-q"], cwd=LAB, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "0"],
                   cwd=LAB, check=True)
    os.makedirs(os.path.join(LAB, "paper"), exist_ok=True)
    for fn in ("fig3.py", "other.py"):
        with open(os.path.join(LAB, "paper", fn), "w") as f:
            f.write("x = 1\n")
    out = subprocess.run(WORK.split() + ["commit", "-m", "fig 3 (J)"], capture_output=True, text=True,
                         env=dict(os.environ, QRL_JOB=a, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                                  GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t"))
    assert out.returncode == 0, out.stdout + out.stderr
    files = subprocess.run(["git", "show", "--name-only", "--format=", "HEAD"], cwd=LAB, capture_output=True,
                           text=True).stdout.split()
    assert files == ["paper/fig3.py"], files
    status = subprocess.run(["git", "status", "--porcelain", "paper"], cwd=LAB, capture_output=True, text=True).stdout
    assert "other.py" in status
    shutil.rmtree(os.path.join(LAB, ".git"))
    shutil.rmtree(os.path.join(LAB, "paper"))
    ok("work board: atomic claims, directory overlap, negotiation inbox, spawn rights, conflict exit 2, own-file commits")


def test_parallel_lanes():
    d = live(fresh_dispatcher())
    db = LabDB()
    d.dd.set("max_workers", "2")
    root = db.researcher_send("Ξεκίνα το section 2")
    queue("claude", {"mode": "ok", "text": "Το ξεκίνησα."})
    d.once()  # the first chat reply (no parallel work yet)
    rid = db.ask("approval", "long job", "σώμα", scope="research", thread_id=root)
    db.decide(rid, "approve", "οκ")
    # a long worker (the decision) claims a file, then runs for a while
    queue("claude", {"mode": "ok", "match": rid, "sleep": 4, "text": "Section 2 έτοιμο.",
                     "sh": f"{WORK} claim docs/sec2.md --note 'section 2'"})
    d.tick()
    wait_until(lambda: alive_lanes(d) == ["worker"], what="worker started")
    wait_until(lambda: d.work.claims() != [], what="worker claim")
    # the researcher keeps talking: the chat coordinator answers while the worker is still running
    m2 = db.researcher_send("Τι κάνει τώρα ο worker;", thread_id=root)
    queue("claude", {"mode": "ok", "match": "Τι κάνει τώρα", "text": "Δουλεύει στο section 2.",
                     "sh": f"{WORK} spawn --title 'Figure 3' --brief 'make figure 3 for section 2'"})
    t0 = time.time()
    d.tick()
    assert time.time() - t0 < 2, "tick must not block on running work"
    wait_until(lambda: any(b.startswith("Κώστα,\n\nΔουλεύει στο section 2.") for b in thread_bodies(db, root)), what="chat reply")
    assert any(j["lane"] == "worker" and j["status"] == "running" and j["origin"] == "decision"
               for j in d.work.active()), "the worker should still be running while the chat answered"
    chat_prompt = next(prompt_of(c) for c in calls("claude") if "Τι κάνει τώρα" in prompt_of(c))
    assert "you are the chat coordinator" in chat_prompt and "## Parallel work now" in chat_prompt
    assert "docs/sec2.md" in chat_prompt, "the chat coordinator must see what the workers hold"
    assert db.message(m2)["status"] == "in_progress"  # its spawned job is still open
    # the spawned job starts as the second worker; it negotiates for the held file and gets a conflict
    queue("claude", {"mode": "ok", "match": "Figure 3", "text": "Figure 3 έτοιμο.", "sh": f"{WORK} claim docs/sec2.md"})
    d.tick()
    wait_until(lambda: alive_lanes(d).count("worker") == 2 or not d.work.queued_spawns(), what="second worker")
    drain(d)
    assert d.work.claims() == [], "claims are released when runs end"
    jobs = {j["origin"]: j for j in [dict(r) for r in d.dd.conn.execute("SELECT * FROM jobs")]}
    assert jobs["spawn"]["status"] == "done" and jobs["decision"]["status"] == "done"
    fig = next(c for c in calls("claude") if "Figure 3" in prompt_of(c) and "parallel worker" in prompt_of(c))
    assert "--resume" not in fig["argv"], "workers never resume the thread's session"
    bodies = thread_bodies(db, root)
    fig_reply = next(b for b in bodies if b.startswith("Κώστα,\n\nFigure 3 έτοιμο."))
    assert "CONFLICT" in fig_reply and "J" in fig_reply.split("—")[-1], "the conflict is reported; footer names the job"
    assert db.message(m2)["status"] == "done", "the last parallel job closes the researcher's request"
    ok("two lanes: chat answers while workers run; spawned jobs; claims visible, released; request closed by last job")


def test_max_workers_cancel_heartbeat():
    d = live(fresh_dispatcher())
    db = LabDB()
    d.dd.set("max_workers", "2")
    root = db.researcher_send("τρία πράγματα")
    queue("claude", {"mode": "ok", "text": "οκ"})
    d.once()
    c = d.work.create("chat", "message", "chat", reply_to=root, thread_id=root, parent_msgs=[root], status="running")
    for i in range(3):
        subprocess.run(WORK.split() + ["spawn", "--title", f"job{i}", "--brief", f"task number {i}"], check=True,
                       capture_output=True, env=dict(os.environ, QRL_JOB=c))
    d.work.set_status(c, "done")
    for i in range(3):
        queue("claude", {"mode": "ok", "match": f"): job{i}\n", "sleep": 30 if i == 0 else 3, "text": f"done {i}"})
    d.tick()
    wait_until(lambda: sum(j["status"] == "running" for j in d.work.active()) == 2, what="two workers")
    d.tick()
    assert alive_lanes(d) == ["worker", "worker"], alive_lanes(d)
    assert len(d.work.queued_spawns()) == 1, [(j["id"], j["status"]) for j in d.work.active()]
    # cancel the long one: its process is stopped, the thread is told
    j0 = next(j["id"] for j in d.work.active() if j["title"] == "job0")
    subprocess.run(WORK.split() + ["cancel", j0], check=True, capture_output=True, env=dict(os.environ, QRL_JOB=c))
    t0 = time.time()
    drain(d, timeout=25)
    assert time.time() - t0 < 20, "the cancelled run must stop at once"
    assert d.work.job(j0)["status"] == "cancelled"
    assert any("ακυρώθηκε" in b for b in thread_bodies(db, root))
    assert {d.work.job(j["id"])["status"] for j in [dict(r) for r in d.dd.conn.execute(
        "SELECT id FROM jobs WHERE title IN ('job1','job2')")]} == {"done"}
    # heartbeat: written by its own thread, independent of runs
    hb = os.path.join(LAB, ".lab", "bridge_heartbeat")
    os.utime(hb, (time.time() - 3600, time.time() - 3600)) if os.path.exists(hb) else None
    threading.Thread(target=d._heartbeat_loop, args=(0.2,), daemon=True).start()
    wait_until(lambda: time.time() - os.path.getmtime(hb) < 2, what="heartbeat")
    # restart: a spawned job that was running is queued again with a note; claims are cleared
    j = d.work.create("worker", "spawn", "interrupted one", "do it", reply_to=root, thread_id=root, status="running")
    d.work.claim(j, ["docs/x.md"])
    d.recover()
    assert d.work.job(j)["status"] == "queued" and not d.work.claims()
    item = d.find_work("worker")
    assert item["job_id"] == j and "interrupted" in item["text"]
    ok("max_workers cap, cancel stops the run, heartbeat thread, restart re-queues spawned jobs")


def test_related_kb_pointers_and_refresh_and_state_limit():
    d = fresh_dispatcher()
    s = d.dd.settings()
    kb = os.path.join(d.root, ".lab", "kb")
    shutil.rmtree(kb, ignore_errors=True)
    long_text = "Πού ορίζεται ο governor και πώς αποφασίζει για προαιρετικές εκτελέσεις; " * 3
    assert d.kb_related(long_text, s) == "" and d.kb_related("σύντομο", s) == "", "no index / short text: nothing"
    os.makedirs(kb)
    seen = []

    def fake_run(cmd, **kw):
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "WARNING: old\ndocs/a.md:3 [doc] governor\n", "")
    with patch.object(D.subprocess, "run", fake_run):
        assert d.kb_related("κοντό", s) == "", "messages up to kb_related_min_chars skip the query"
        out = d.kb_related(long_text, s)
    assert out == "docs/a.md:3 [doc] governor" and len(seen) == 1 and "query" in seen[0]
    popen = []
    with patch.object(D.subprocess, "Popen", lambda cmd, **kw: popen.append(cmd)):
        d.kb_refresh_soon(s); d.kb_refresh_soon(s)
    assert len(popen) == 1 and popen[0][:3] == ["taskset", "-c", "4-7"], "one refresh per window, on cores 4-7"
    d.dd.set("kb_refresh_min", "0")
    d.dd.conn.execute("DELETE FROM settings WHERE key='kb_refresh_last'")
    with patch.object(D.subprocess, "Popen", lambda cmd, **kw: popen.append(cmd)):
        d.kb_refresh_soon(d.dd.settings())
    assert len(popen) == 1, "kb_refresh_min=0 never refreshes"
    d.dd.set("kb_refresh_min", "10")
    shutil.rmtree(kb, ignore_errors=True)
    # STATE size note
    os.makedirs(os.path.join(d.root, "docs"), exist_ok=True)
    keep = d._read("docs/STATE.md")
    open(os.path.join(d.root, "docs", "STATE.md"), "w").write("x" * 9000)
    notes = []
    d.build_prompt("claude", {"kind": "message", "thread_id": "T", "msg_ids": [], "reply_to": "M", "text": "hi",
                             "req_ids": []}, True, notes)
    open(os.path.join(d.root, "docs", "STATE.md"), "w").write(keep or "")
    assert any("9000 bytes" in n for n in notes), notes
    ok("B6: kb pointers for long messages only, one refresh per window on cores 4-7, STATE byte limit note")


def test_roles_commit_claimed_and_solo_review():
    d = fresh_dispatcher()
    db = LabDB()
    d.dd.set("claude_model", "sonnet")
    root = db.researcher_send("δουλειά")
    db.conn.execute("UPDATE messages SET status='done' WHERE id=?", (root,))
    # role: a research worker runs on the role's model, an unroled one keeps claude_model
    d.work.create("worker", "spawn", "R job", "x", reply_to=root, thread_id=root, status="queued", role="research")
    queue("claude", {"mode": "ok", "text": "ok"})
    assert d.once() == "done"
    argv = calls("claude")[-1]["argv"]
    assert "opus" in argv and "sonnet" not in argv, argv
    d.work.create("worker", "spawn", "plain", "x", reply_to=root, thread_id=root, status="queued")
    queue("claude", {"mode": "ok", "text": "ok"})
    assert d.once() == "done" and "sonnet" in calls("claude")[-1]["argv"]
    # commit_claimed: only the claimed file, blobs verified; an unclaimed modified file stays out
    repo = tempfile.mkdtemp(prefix="b5repo-")
    os.makedirs(os.path.join(repo, ".lab"))
    run = lambda *a: subprocess.run(["git", *a], cwd=repo, capture_output=True, text=True, check=True)
    run("init", "-q"); run("config", "user.email", "t@t"); run("config", "user.name", "t")
    open(os.path.join(repo, "seed.txt"), "w").write("0"); run("add", "-A"); run("commit", "-qm", "seed")
    open(os.path.join(repo, "mine.py"), "w").write("print(1)\n")
    open(os.path.join(repo, "other.py"), "w").write("print(2)\n")
    r = W.commit_claimed(repo, ["mine.py"], "J1: test")
    assert r["files"] == ["mine.py"] and r["mismatch"] == [], r
    assert "other.py" in run("status", "--porcelain").stdout and "mine.py" not in run("status", "--porcelain").stdout
    assert W.commit_claimed(repo, ["mine.py"], "J1: again")["files"] == [], "nothing new: no empty commit"
    shutil.rmtree(repo, ignore_errors=True)
    # solo: Claude at its limit -> the job runs on Codex only; when Claude is back, one read-only review is requested
    j = d.work.create("worker", "spawn", "Solo job", "x", reply_to=root, thread_id=root, status="queued")
    queue("claude", {"mode": "quota"})
    queue("codex", {"mode": "ok", "text": "έτοιμο"})
    assert d.once() == "done"
    row = d.dd.conn.execute("SELECT * FROM solo_jobs WHERE job=?", (j,)).fetchone()
    assert row and row["ran_on"] == "codex" and row["review_peer"] is None
    d._solo_reviews()
    assert d.dd.conn.execute("SELECT review_peer FROM solo_jobs WHERE job=?", (j,)).fetchone()[0] is None, "Claude still out"
    d.dd.clear("claude")
    d._solo_reviews(); d._solo_reviews()
    pid = d.dd.conn.execute("SELECT review_peer FROM solo_jobs WHERE job=?", (j,)).fetchone()[0]
    reqs = d.dd.conn.execute("SELECT * FROM peer_requests WHERE key=?", (f"solo-{j}",)).fetchall()
    assert pid and len(reqs) == 1 and reqs[0]["to_provider"] == "claude", "exactly one joint review"
    d.dd.conn.execute("UPDATE peer_requests SET status='done' WHERE key=?", (f"solo-{j}",))
    # Claude already marked unavailable before the job starts (nothing "tried"): still solo
    d.dd.mark_exhausted("claude", time.time() + 3600, "drill")
    j3 = d.work.create("worker", "spawn", "Pre-exhausted", "x", reply_to=root, thread_id=root, status="queued")
    queue("codex", {"mode": "ok", "text": "ok"})
    assert d.once() == "done" and d.dd.conn.execute("SELECT 1 FROM solo_jobs WHERE job=?", (j3,)).fetchone()
    d.dd.clear("claude")
    # a job pinned to a provider is not solo
    j2 = d.work.create("worker", "spawn", "Pinned", "x", reply_to=root, thread_id=root, provider="codex", status="queued")
    queue("codex", {"mode": "ok", "text": "ok"})
    assert d.once() == "done" and not d.dd.conn.execute("SELECT 1 FROM solo_jobs WHERE job=?", (j2,)).fetchone()
    ok("B5: role models for workers, dispatcher commit of claimed files only (blob check), solo jobs get one joint review")


def test_config_card_applies_on_approval_by_script():
    d = fresh_dispatcher()
    d.lab.close()
    d.lab = LabDB(os.path.join(LAB, ".lab", "lab.db"))
    n0 = len(calls("claude")) + len(calls("codex"))
    d.dd.set("max_retries", "1")
    rid = D.propose_config(d.lab, d.dd, "max_retries", "2", "δοκιμή", author="J9")
    assert d.dd.get("max_retries") == "1", "a proposal changes nothing"
    for bad in (("max_retries", "99"), ("max_retries", "x"), ("nope", "1"), ("max_retries", "1")):
        try:
            D.propose_config(d.lab, d.dd, *bad, "r")
            raise AssertionError(bad)
        except D.LabError:
            pass
    d.lab.decide(rid, "approve", "ok")
    list(d._candidates())
    assert d.dd.get("max_retries") == "2" and d.lab.request(rid)["decision_delivered"] == 1
    assert all(x["kind"] != "decision" for x in d._candidates())
    assert d.dd.conn.execute("SELECT COUNT(*) FROM audit WHERE detail LIKE 'max_retries: %'").fetchone()[0] == 1
    rid2 = D.propose_config(d.lab, d.dd, "max_retries", "0", "r2", author="J9")
    d.lab.decide(rid2, "reject", "όχι")
    list(d._candidates())
    assert d.dd.get("max_retries") == "2" and d.lab.request(rid2)["decision_delivered"] == 1
    d.dd.change("max_retries", "3")                      # a replayed, already-applied card must not re-apply
    d.lab.conn.execute("UPDATE requests SET decision_delivered=0 WHERE id=?", (rid,))
    list(d._candidates())
    assert d.dd.get("max_retries") == "3", "applied flag: replay changes nothing"
    assert len(calls("claude")) + len(calls("codex")) == n0, "config cards cost no model call"
    # a stale approval never overwrites a newer choice
    rid3 = D.propose_config(d.lab, d.dd, "max_retries", "4", "r3", author="J9")
    d.dd.change("max_retries", "2")
    d.lab.decide(rid3, "approve", "ok")
    list(d._candidates())
    assert d.dd.get("max_retries") == "2" and d.lab.request(rid3)["decision_delivered"] == 1, "conflict: nothing written"
    d.dd.set("max_retries", "1")
    ok("config card: validated proposal, applied on approval by script (audited, once), rejected = no change, 0 model calls")


def test_approved_sim_spec_is_launched_by_script():
    d = fresh_dispatcher()
    d.lab.close()
    d.lab = LabDB(os.path.join(LAB, ".lab", "lab.db"))
    db = d.lab
    root = db.researcher_send("Τρέξε τρία seeds")
    db.conn.execute("UPDATE messages SET status='done' WHERE id=?", (root,))
    cmd = [sys.executable, "-c", "import time; time.sleep(2)"]
    spec = {"name": "tri", "scope": "sim", "cwd": ".", "max_attempts": 1, "max_parallel": 2,
            "entries": [{"name": f"seed{i}", "seed": i, "cmd": cmd} for i in range(3)],
            "limits": {"wall_clock_hours": 1.0}}
    rid = db.ask("approval", "tri", "σώμα", scope="sim", spec=spec, thread_id=root)
    n0 = len(calls("claude")) + len(calls("codex"))
    db.decide(rid, "approve", "οκ")
    assert d.once() is None, "approved sim spec: launched by script, no coordinator task"
    assert len(calls("claude")) + len(calls("codex")) == n0
    runs = lambda: [dict(r) for r in db.conn.execute("SELECT entry, status FROM runs WHERE request_id=?", (rid,))]
    assert sorted(r["entry"] for r in runs()) == [0, 1], runs()           # max_parallel 2
    assert db.request(rid)["decision_delivered"] == 1
    assert not any("ξεκίνησε" in b for b in thread_bodies(db, root)), "F3: no auto-message in the researcher thread"
    tl = open(os.path.join(d.root, ".lab", "technical.log"), encoding="utf-8").read()
    assert "started 2/3" in tl
    d.once()
    assert len(runs()) == 2, "no duplicate start while both slots are busy"
    db.conn.execute("UPDATE runs SET status='done', exit_code=0 WHERE request_id=? AND entry=0", (rid,))  # a slot frees up
    list(d._candidates())
    assert sorted(r["entry"] for r in runs()) == [0, 1, 2], runs()          # slot freed -> entry 2 started once
    time.sleep(0.5); list(d._candidates())
    assert len(runs()) == 3
    # a real-scope approval is never launched by script
    rid2 = db.ask("approval", "real", "σώμα", scope="real", thread_id=root,
                  spec={"name": "r", "scope": "real", "cwd": ".", "max_attempts": 1,
                        "entries": [{"name": "e", "cmd": cmd}], "limits": {"wall_clock_hours": 1.0},
                        "real": {"kube_context": "x", "namespace": "n", "rollback": "r"}})
    db.decide(rid2, "approve", "οκ")
    items = [x for x in d._candidates() if x["kind"] == "decision"]
    assert items and rid2 in items[0]["req_ids"] and not db.conn.execute(
        "SELECT 1 FROM runs WHERE request_id=?", (rid2,)).fetchone()
    db.mark_delivered(req_ids=[rid2])   # leave no pending decision for the next test
    ok("approved sim spec -> launched by script (max_parallel, once, no model); real scope stays with the coordinator")


def test_clean_batch_summary_by_script_exactly_once():
    d = fresh_dispatcher()
    d.lab.close()
    d.lab = LabDB(os.path.join(LAB, ".lab", f"script-ev-{time.time_ns()}.db"))
    d.dd.conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES ('events_initialized','1')")
    n0 = len(calls("claude")) + len(calls("codex"))

    def add(ident, rid, status, code):
        d.lab.conn.execute(
            "INSERT INTO runs(run_id,request_id,spec_hash,entry,attempt,scope,cmd,cwd,run_dir,status,exit_code,created)"
            " VALUES (?,?, 'h',0,1,'sim','[]','.','fx',?,?,?)", (ident, rid, status, code, D.now_iso()))
    add("ok-a", "R-script-ok", "done", 0)
    add("ok-b", "R-script-ok", "done", 0)
    assert not [x for x in d._candidates() if x.get("event_ref", "").startswith("R-script-ok:")], "clean batch: no model"
    tl = lambda: open(os.path.join(d.root, ".lab", "technical.log"), encoding="utf-8").read()
    assert tl().count("[run-summary R-script-ok:") == 1 and "ok-a" in tl() and "ok-b" in tl()   # F3: technical log, not the thread
    assert not d.lab.conn.execute("SELECT 1 FROM messages WHERE body LIKE '%[run-summary R-script-ok:%'").fetchone()
    assert not [x for x in d._candidates() if x.get("event_ref", "").startswith("R-script-ok:")]
    d.dd.conn.execute("DELETE FROM notified")   # restart that lost the notified mark: the marker in the thread still holds
    d._candidates()
    assert tl().count("[run-summary R-script-ok:") == 1
    add("bad-a", "R-script-bad", "done", 0)
    add("bad-b", "R-script-bad", "failed", 1)
    assert len([x for x in d._candidates() if x.get("event_ref", "").startswith("R-script-bad:")]) == 1, "failure -> model"
    assert len(calls("claude")) + len(calls("codex")) == n0


def test_run_events_full_request_set():
    d = fresh_dispatcher()
    # This window fixture must own its run set, independent of earlier test batches.
    d.lab.close()
    d.lab = LabDB(os.path.join(LAB, ".lab", f"rolling-{time.time_ns()}.db"))
    d.dd.conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES ('events_initialized','1')")
    rid = "R-rolling-regression"

    def add(ident, request, created, status="failed"):
        d.lab.conn.execute(
            "INSERT INTO runs(run_id,request_id,spec_hash,entry,attempt,scope,cmd,cwd,run_dir,status,created)"
            " VALUES (?,?, 'h',0,1,'sim','[]','.','fixture',?,?)", (ident, request, status, created))

    def events():
        return [x for x in d._candidates() if x.get("event_ref", "").startswith(rid + ":")]

    add("rolling-a", rid, "0000", "running")
    add("rolling-b", rid, "0001")
    for n in range(499):
        add(f"rolling-noise-{n}", "R-noise", f"1000-{n:04}")
    assert "rolling-a" not in {r["run_id"] for r in d.lab.runs(limit=500)}
    assert not events(), "active run outside the window still blocks completion"
    d.lab.conn.execute("UPDATE runs SET status='done' WHERE run_id='rolling-a'")
    found = events()
    assert len(found) == 1, (d.dd.get("events_initialized"),
        [dict(r) for r in d.dd.conn.execute("SELECT * FROM notified")],
        [dict(r) for r in d.lab.conn.execute("SELECT run_id,status FROM runs WHERE request_id=?", (rid,))])
    first, = found
    assert first["event_ref"] == rid + ":rolling-a,rolling-b"
    d._consume(first)
    assert not events(), "identical set dedups"
    add("rolling-new-noise", "R-noise", "2000")
    assert not events(), "eviction of rolling-b must not change the batch identity"
    add("rolling-c", rid, "3000", "running")
    assert not events()
    d.lab.conn.execute("UPDATE runs SET status='done' WHERE run_id='rolling-c'")
    second, = events()
    assert second["event_ref"] == rid + ":rolling-a,rolling-b,rolling-c"
    d._consume(second)
    assert not events()
    # Legacy truncated refs backfill only genuinely old sets, never new waves.
    legacy_rid = "R-legacy-regression"
    add("legacy-a", legacy_rid, "2020-01-01T00:00:00+00:00")
    add("legacy-b", legacy_rid, "2020-01-02T00:00:00+00:00")
    d.dd.mark_notified("runs", legacy_rid + ":legacy-b")
    assert not [x for x in d._candidates() if x.get("event_ref", "").startswith(legacy_rid + ":")]
    assert d.dd.is_notified("runs", legacy_rid + ":legacy-a,legacy-b")
    add("legacy-c", legacy_rid, D.now_iso())
    fresh = [x for x in d._candidates() if x.get("event_ref", "").startswith(legacy_rid + ":")]
    assert len(fresh) == 1 and fresh[0]["event_ref"].endswith("legacy-a,legacy-b,legacy-c")
    # Same-second creation is ambiguous: deliver rather than suppress a new wave.
    d._consume(fresh[0])
    add("legacy-d", legacy_rid, D.now_iso())
    assert len([x for x in d._candidates() if x.get("event_ref", "").startswith(legacy_rid + ":")]) == 1
    ok("F1 rolling window and legacy refs dedup; active old runs and genuine new waves preserved")


def test_retry_attempt_accounting_and_resume_policy():
    d = fresh_dispatcher()
    item = {"kind": "message", "thread_id": "retry-fixture", "msg_ids": [], "req_ids": []}
    first = dict(D._empty_result(), transient=True, error="temporary", model="first-model",
                 usage={"input": 17, "output": 2, "cached": 3, "cache_write": 4}, cost=0.1)
    second = dict(D._empty_result(), ok=True, model="second-model",
                  usage={"input": 23, "output": 5, "cached": 6, "cache_write": 7}, cost=0.2)
    with patch.object(d, "_run_provider", side_effect=[first, second]) as run:
        result = d._attempt("codex", item, [], None)
    rows = [dict(r) for r in d.dd.conn.execute("SELECT * FROM tasks ORDER BY id")]
    assert result["ok"] and run.call_count == 2
    assert [r["status"] for r in rows] == ["retry_transient", "done"]
    assert sum(r["input_tokens"] for r in rows) == 40
    assert sum(r["output_tokens"] for r in rows) == 7
    assert sum(r["cached_tokens"] for r in rows) == 9
    assert sum(r["cache_write_tokens"] for r in rows) == 11
    assert abs(sum(r["cost_usd"] for r in rows) - 0.3) < 1e-9
    assert [r["model"] for r in rows] == ["first-model", "second-model"]
    assert all(r["ended"] and not r["resumed"] for r in rows)
    # Unknown, quota, and transient resumed failures must never replay fresh.
    for failed in (dict(D._empty_result(), error="sandbox failed"),
                   dict(first), dict(D._empty_result(), quota=True, error="limit")):
        with patch.object(d, "_run_provider", return_value=failed) as run:
            assert not d._attempt("codex", item, [], "old-session")["ok"]
            assert run.call_count == 1
    rejected = dict(D._empty_result(), error="session id old not found", resume_rejected=True)
    with patch.object(d, "_run_provider", side_effect=[rejected, second]) as run:
        assert d._attempt("codex", item, [], "old-session")["ok"]
        assert [c.args[-1] for c in run.call_args_list] == ["old-session", None]
    rows = [dict(r) for r in d.dd.conn.execute("SELECT * FROM tasks ORDER BY id")]
    assert [r["status"] for r in rows[-2:]] == ["retry_fresh", "done"]
    assert [r["resumed"] for r in rows[-2:]] == [1, 0]
    ok("F2 every attempt preserves usage/cost (17+23=40); F3 only rejected resume replays")


def test_resume_rejection_before_work_only():
    for provider in ("claude", "codex"):
        run = D.run_claude if provider == "claude" else D.run_codex
        error = "No conversation found with session ID: old" if provider == "claude" else "thread id old not found"
        event = {"type": "assistant"} if provider == "claude" else {"type": "turn.started"}
        kwargs = {"session_id": "old"}
        args = ("fixture", LAB, "fake", "medium")
        for started in (False, True):
            stdout = json.dumps(event) + "\n" if started else ""
            proc = subprocess.CompletedProcess([], 1, stdout=stdout, stderr=error)
            with patch.object(D, "_exec", return_value=proc):
                result = run(*args, **kwargs)
            assert result.get("resume_rejected") is (not started), (provider, result)
        proc = subprocess.CompletedProcess([], 1, stdout="", stderr="sandbox failed")
        with patch.object(D, "_exec", return_value=proc):
            assert not run(*args, **kwargs).get("resume_rejected")
    assert not D._resume_rejected("session id old not found", True)
    assert not D._resume_rejected("your session has expired", False)
    assert not D._resume_rejected("invalid session cookie", False)
    assert D._event_time("invalid") is None
    assert D._event_time(None) is None
    assert D._event_time("2020-01-01T00:00:00") is None
    ok("F3 provider parsers distinguish explicit pre-work resume rejection from started/unknown failures")


def test_peer_context_and_ttl_limits():
    d = fresh_dispatcher()
    d.dd.set("resume_max_tokens", "1000")
    d.dd.set("codex_resume_window_s", "900")
    for provider in ("claude", "codex"):
        key = "peer-limit-" + provider
        for context, age, expected in ((1000, 0, "warm"), (1001, 0, None), (1000, 901, None)):
            d.dd.save_session("peer:" + key, provider, "warm", 900, context)
            d.dd.conn.execute("UPDATE sessions SET last_used=? WHERE thread_id=? AND provider=?",
                              (time.time() - age, "peer:" + key, provider))
            pid = d.dd.peer_submit(provider, "fixture", key=key)
            req = d.dd.peer_claim()
            assert req["id"] == pid
            result = dict(D._empty_result(), ok=True, session_id="next", context_tokens=1)
            with patch.object(D, "run_" + provider, return_value=result) as run:
                D._serve_peer(LAB, req, d.dd)
            assert run.call_args.kwargs["session_id"] == expected
    ok("F4 peer resumes obey the context ceiling and provider TTL, including boundary")

def test_escalation_debounce():
    d = fresh_dispatcher()
    w = d.work
    a = w.create("worker", "spawn", "A", "long job", reply_to="M-x", status="running")
    n0 = len(calls("claude")) + len(calls("codex"))
    esc = lambda: [i for i in d._candidates() if i["kind"] == "escalation"]
    reqs = lambda: d.lab.conn.execute("SELECT * FROM requests WHERE author='dispatcher' AND title LIKE ?",
                                      ("Χρειάζεται η απόφασή σου%",)).fetchall()
    def notes():   # J449: routine worker notes go to the technical log, one line per note
        return [{"body": l} for l in d._tech_log_text().splitlines() if "worker note" in l]
    assert not d.lab.conn.execute("SELECT 1 FROM messages WHERE body LIKE '%Σημείωση από%'").fetchone()
    w.say(a, "coordinator", "progress 1")
    assert esc() == [] and len(notes()) == 1, "routine note: a status line by script, no coordinator task"
    w.say(a, "coordinator", "progress 2")
    w.say(a, "coordinator", "progress 3")
    esc()
    assert len(notes()) == 1, "routine notes inside the debounce window are batched"
    d.dd.conn.execute("UPDATE settings SET value=? WHERE key='escalation_last_wake'", (str(time.time() - 1201),))
    esc()
    nb = notes()
    assert len(nb) == 3 and "progress 2" in nb[1]["body"] and "progress 3" in nb[2]["body"], "one line per note, once each"
    esc()
    assert len(notes()) == 3, "a second scan reposts nothing"
    w.say(a, "coordinator", "blocked: need a choice", kind="urgent")
    esc()
    r = reqs()
    assert len(r) == 1 and r[0]["kind"] == "question" and "blocked: need a choice" in r[0]["body"], "urgent -> a card at once"
    esc()
    assert len(reqs()) == 1, "exactly one card per note"
    w.say(a, "coordinator", "final note")
    w.set_status(a, "done")
    esc()
    assert len(notes()) == 4 and w.escalations() == [], "a note from a job that already ended is posted at once"
    assert len(calls("claude")) + len(calls("codex")) == n0, "escalations cost no model call"
    d.lab.conn.execute("UPDATE requests SET state='withdrawn', decision_delivered=1 WHERE author='dispatcher'")
    ok("escalations: routine notes batched into a status line, urgent ones a card, no model call, once each")


def n_tasks(d, provider):
    return d.dd.conn.execute("SELECT COUNT(*) FROM tasks WHERE provider=?", (provider,)).fetchone()[0]


def write_codex_rollout(primary, secondary, secondary_reset_in=6 * 86400):
    """A Codex rollout record as the real CLI writes it (token_count with rate_limits), under the test HOME."""
    d = os.path.join(HOME, ".codex", "sessions", "2026", "11")
    os.makedirs(d, exist_ok=True)
    now = time.time()
    rec = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(now)),
           "payload": {"type": "token_count", "rate_limits": {
               "primary": {"used_percent": primary, "window_minutes": 300, "resets_at": now + 3600},
               "secondary": {"used_percent": secondary, "window_minutes": 10080, "resets_at": now + secondary_reset_in},
               "plan_type": "pro"}}}
    with open(os.path.join(d, "rollout-test.jsonl"), "w", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    D.governor.CODEX_GLOB = os.path.join(HOME, ".codex", "sessions", "**", "rollout-*.jsonl")  # not the real ~/.codex, whatever imported usage_limits first
    D.governor._codex_memo.clear()


def test_governor_and_parallelism_with_reported_usage():
    """A rate_limit_event with a percentage (fake Claude CLI) drives the governor; with unknown Codex usage only one
    optional job runs at a time; fresh Codex rollout usage releases the second worker (governor + max_workers together)."""
    d = live(fresh_dispatcher())
    d.dd.set("governor_enabled", "1")
    d.dd.set("max_workers", "2")
    db = LabDB(os.path.join(LAB, ".lab", "lab.db"))   # explicit: other modules overwrite QRL_LAB_DIR at import
    shutil.rmtree(os.path.join(HOME, ".codex"), ignore_errors=True)
    D.governor.CODEX_GLOB = os.path.join(HOME, ".codex", "sessions", "**", "rollout-*.jsonl")  # not the real ~/.codex, whatever imported usage_limits first
    D.governor._codex_memo.clear()
    root = db.researcher_send("Δύο δουλειές")
    # Claude reports 80 % weekly use with 6 days to reset (pace ~14 %): over pace + 10. The chat answer is never held back.
    queue("claude", {"mode": "ok", "text": "Ξεκινώ.", "window": "seven_day", "util": 0.8, "reset_in": 6 * 86400,
                     "sh": f"{WORK} spawn --title 'Alpha job' --brief 'alpha' && {WORK} spawn --title 'Beta job' --brief 'beta'"})
    d.tick()
    wait_until(lambda: any(b.startswith("Κώστα,\n\nΞεκινώ.") for b in thread_bodies(db, root)), what="chat reply")
    wait_until(lambda: alive_lanes(d) == [] and len(d.work.queued_spawns()) == 2, what="two queued spawns")
    saved = {r["window"]: r for r in d.dd.limits("claude")}
    assert abs(saved["seven_day"]["utilization"] - 0.8) < 1e-9                       # the reported percentage was stored
    wins = D.governor.windows("claude", D.dispatch_db_path(LAB), os.path.join(LAB, ".lab", "usage", "claude.json"))
    assert abs(wins["seven_day"]["pct"] - 80) < 1e-9
    # Codex usage unknown -> conservative: exactly one of the two jobs runs (on Codex, Claude is over pace)
    queue("codex", {"mode": "ok", "match": "Alpha job", "sleep": 4, "text": "alpha ok"},
          {"mode": "ok", "match": "Beta job", "sleep": 1, "text": "beta ok"})
    d.tick()
    wait_until(lambda: alive_lanes(d) == ["worker"] and n_tasks(d, "codex") == 1, what="one worker on Codex")
    d.tick()
    time.sleep(0.5)
    assert alive_lanes(d) == ["worker"] and len(d.work.queued_spawns()) == 1, "unknown Codex usage: one optional job"
    assert n_tasks(d, "claude") == 1, "no job went to the over-pace Claude"
    assert n_tasks(d, "codex") == 1
    # fresh low Codex usage (5 h 5 %, weekly 10 % at 14 % pace) -> the second worker may start in parallel
    write_codex_rollout(5.0, 10.0)
    d.tick()
    wait_until(lambda: n_tasks(d, "codex") == 2, what="second worker on Codex")
    assert alive_lanes(d).count("worker") == 2 and n_tasks(d, "claude") == 1
    drain(d)
    D.governor.CODEX_GLOB = None
    ok("governor + parallelism: reported usage drives provider choice; unknown usage -> one job; fresh usage -> two")




def test_held_job_does_not_block_the_queue_and_peer_requeues():
    """A job pinned to an over-pace provider stays queued (nothing posted, provider state untouched) while the next
    job, for the other provider, still starts in the same tick; a peer that loses the last slot goes back to queued."""
    d = live(fresh_dispatcher())
    d.dd.set("governor_enabled", "1")
    d.dd.set("max_workers", "2")
    shutil.rmtree(os.path.join(HOME, ".codex"), ignore_errors=True)
    D.governor.CODEX_GLOB = os.path.join(HOME, ".codex", "sessions", "**", "rollout-*.jsonl")  # not the real ~/.codex, whatever imported usage_limits first
    D.governor._codex_memo.clear()
    d.dd.save_limits("claude", [{"rateLimitType": "seven_day", "utilization": 0.8, "status": "allowed",
                                 "resetsAt": int(time.time()) + 6 * 86400},
                                {"rateLimitType": "five_hour", "utilization": 0.1, "status": "allowed",
                                 "resetsAt": int(time.time()) + 3600}])
    tid = LabDB(os.path.join(LAB, ".lab", "lab.db")).researcher_send("δουλειές")
    held = d.work.create("worker", "spawn", "Pinned Claude job", "x", thread_id=tid, reply_to=tid, provider="claude",
                         status="queued")
    free = d.work.create("worker", "spawn", "Codex job", "y", thread_id=tid, reply_to=tid, provider="codex",
                         status="queued")
    queue("codex", {"mode": "ok", "match": "Codex job", "sleep": 3, "text": "codex ok"})
    d.tick()
    wait_until(lambda: n_tasks(d, "codex") == 1, what="the second job starts although the first is held")
    assert d.work.job(held)["status"] == "queued" and n_tasks(d, "claude") == 0 and not calls("claude")
    assert d.dd.available("claude"), "the governor never marks a provider exhausted"
    # a peer asks for codex while a worker holds its only slot (unknown usage -> cap 1): it is re-queued, not failed
    d.dd.conn.execute("INSERT INTO peer_requests(id, ts, from_provider, to_provider, key, major, prompt, status)"
                      " VALUES ('P-T','2026-11-05T00:00:00','claude','codex',NULL,0,'q','queued')")
    req = d.dd.peer_claim()
    assert req and d.dd.reserve("peer", "peer:x", [req["id"]], "codex", "peer", cap=1) is None
    d.dd.peer_requeue(req["id"])
    assert d.dd.conn.execute("SELECT status FROM peer_requests WHERE id='P-T'").fetchone()[0] == "queued"
    d.dd.conn.execute("UPDATE jobs SET status='cancelled' WHERE id=?", (held,))
    drain(d)
    D.governor.CODEX_GLOB = None
    ok("a governor-held job stays queued and does not block later jobs; provider state untouched; peer re-queued")




TESTS = [test_related_kb_pointers_and_refresh_and_state_limit, test_roles_commit_claimed_and_solo_review, test_config_card_applies_on_approval_by_script, test_approved_sim_spec_is_launched_by_script, test_clean_batch_summary_by_script_exactly_once, test_run_events_full_request_set, test_retry_attempt_accounting_and_resume_policy,
         test_resume_rejection_before_work_only, test_peer_context_and_ttl_limits, test_claude_reply_and_resume, test_failover_on_quota, test_both_exhausted_then_resume,
         test_choice_mention_status_and_errors, test_paid_credits_guard, test_decisions_and_run_events, test_peers,
         test_md_index, test_parse_reset, test_panel_and_installer, test_edit_freeze, test_headless_permission_roundtrip,
         test_work_board, test_parallel_lanes, test_max_workers_cancel_heartbeat, test_escalation_debounce,
         test_governor_and_parallelism_with_reported_usage, test_held_job_does_not_block_the_queue_and_peer_requeues]

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
