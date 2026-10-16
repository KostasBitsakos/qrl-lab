#!/usr/bin/env python3
"""End-to-end tests of the QRL-Lab plumbing, without Claude: message round trip, decisions, launcher, hook, dashboard.

Run from ~/qrl-lab:  .venv/bin/python tests/test_lab.py
Everything happens in a temporary directory; the real .lab/ is not touched.
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

KIT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TMP = tempfile.mkdtemp(prefix="qrl-test-")
for sub in ("tools", "dashboard", "docs", ".streamlit", "paper"):
    shutil.copytree(os.path.join(KIT, sub), os.path.join(TMP, sub), ignore=shutil.ignore_patterns("build"))
os.environ["QRL_LAB_DIR"] = TMP
os.chdir(TMP)
sys.path.insert(0, os.path.join(TMP, "tools"))

from labdb import LabDB, LabError  # noqa: E402
import lab_bridge_watch  # noqa: E402

PASSED = []


def ok(name):
    PASSED.append(name)
    print(f"  ok  {name}")


def expect_error(fn, contains=""):
    try:
        fn()
    except LabError as e:
        assert contains in str(e), f"wrong error: {e}"
        return str(e)
    raise AssertionError("expected LabError")


def watch_cycle(db, first=False):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        lab_bridge_watch.cycle(db, first)
    return buf.getvalue().strip().splitlines()


def test_message_round_trip():
    db = LabDB()
    mid = db.researcher_send("hello dashboard", kind="message")
    lines = watch_cycle(db)
    assert len(lines) == 1 and lines[0].startswith(f"QRL-INBOX message {mid}") and "hello dashboard" in lines[0], lines
    assert db.message(mid)["status"] == "delivered"
    assert watch_cycle(db) == [], "must not deliver twice"
    m, thread = db.take(mid)
    assert db.message(mid)["status"] == "acknowledged" and len(thread) == 1
    rid = db.post("codex", "Codex view: X", mid, kind="contribution")
    db.post("coordinator", "Γεια σου! Η απάντηση.", mid, set_status="done")
    th = db.thread(mid)
    assert [x["author"] for x in th] == ["researcher", "codex", "coordinator"], th
    assert db.message(mid)["status"] == "done"
    expect_error(lambda: db.post("researcher", "spoof", mid), "cannot post as the researcher")
    expect_error(lambda: db.researcher_send("   "), "κενό")
    # follow-up in the same thread
    mid2 = db.researcher_send("και κάτι ακόμη", thread_id=mid)
    assert db.message(mid2)["thread_id"] == mid
    ok("dashboard message -> bridge line -> take -> codex + coordinator replies -> done")


def test_model_label():
    import sqlite3
    db = LabDB()
    mid = db.researcher_send("model label test")
    a = db.post("codex", "with model", mid, kind="contribution", model="gpt-6-sol")
    b = db.post("coordinator", "without model", mid)
    assert db.message(a)["model"] == "gpt-6-sol" and db.message(b)["model"] is None
    # CLI path
    body = os.path.join(TMP, "model_body.md")
    open(body, "w").write("via cli")
    r = subprocess.run([sys.executable, os.path.join(TMP, "tools", "labq.py"), "post", "--reply-to", mid,
                        "--body-file", body, "--model", "Opus 5.5"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert db.message(r.stdout.strip())["model"] == "Opus 5.5", r.stdout
    # migration: old DB without the column, run twice
    old = os.path.join(TMP, "old.db")
    c = sqlite3.connect(old)
    c.executescript("CREATE TABLE messages (id TEXT PRIMARY KEY, ts TEXT NOT NULL, thread_id TEXT NOT NULL,"
                    " reply_to TEXT, author TEXT NOT NULL, kind TEXT NOT NULL, title TEXT, body TEXT NOT NULL,"
                    " status TEXT, updated_at TEXT NOT NULL, delivered_count INTEGER NOT NULL DEFAULT 0);"
                    " INSERT INTO messages(id,ts,thread_id,author,kind,body,updated_at)"
                    " VALUES ('M-old','t','M-old','researcher','message','old','t');")
    c.close()
    for _ in range(2):
        d = LabDB(old)
        d.close()
    d = LabDB(old)
    assert d.message("M-old")["model"] is None
    nid = d.post("codex", "x", "M-old", model="m1")
    assert d.message(nid)["model"] == "m1"
    d.close()
    ok("model stored via API and CLI; migration of a DB without the column is idempotent")


def test_routing_tags():
    db = LabDB()
    m1 = db.researcher_send("plain routing", kind="message")
    m2 = db.researcher_send("fast one", req_model="haiku", req_effort="low")
    expect_error(lambda: db.researcher_send("x", req_model="gpt"), "μοντέλο")
    expect_error(lambda: db.researcher_send("x", req_effort="max"), "ένταση")
    assert db.message(m2)["req_model"] == "haiku" and db.message(m2)["req_effort"] == "low"
    assert db.message(m1)["req_model"] is None
    lines = watch_cycle(db)
    l1 = [l for l in lines if m1 in l][0]
    l2 = [l for l in lines if m2 in l][0]
    assert "[model=" not in l1 and f"thread={m2}: " not in l2 and "[model=haiku effort=low]" in l2, lines
    ok("routing tags stored on the message and included in the QRL-INBOX line")


def test_paper_selections():
    import sqlite3
    path = os.path.join(TMP, "old-paper-sel.db")
    c = sqlite3.connect(path)
    c.executescript("CREATE TABLE messages (id TEXT PRIMARY KEY, ts TEXT NOT NULL, thread_id TEXT NOT NULL, reply_to TEXT,"
                    " author TEXT NOT NULL, kind TEXT NOT NULL, title TEXT, body TEXT NOT NULL, status TEXT,"
                    " updated_at TEXT NOT NULL, delivered_count INTEGER NOT NULL DEFAULT 0);")
    c.commit()
    c.close()
    for _ in range(2):  # idempotent
        old = LabDB(path)
        cols = {r[1] for r in old.conn.execute("PRAGMA table_info(messages)")}
        assert {"req_writers", "req_reviewers"} <= cols, cols
        old.close()
    db = LabDB()
    tid = db.ensure_thread("Paper — συγγραφή", "root")
    assert db.ensure_thread("Paper — συγγραφή", "root") == tid
    m = db.researcher_send("γράψε το intro", thread_id=tid, reply_to=tid, req_writers=["writer-sonnet"],
                           req_reviewers=["codex-reviewer", "scholar"])
    plain = db.researcher_send("no selections")
    assert json.loads(db.message(m)["req_writers"]) == ["writer-sonnet"] and db.message(plain)["req_writers"] is None
    expect_error(lambda: db.researcher_send("x", req_writers=["nobody"]), "συγγραφέας")
    expect_error(lambda: db.researcher_send("x", req_reviewers=["writer-sonnet"]), "reviewer")
    lines = watch_cycle(db)
    assert not any(tid + ":" in l and "root" in l for l in lines), "root note must not be delivered"
    lm = [l for l in lines if m in l][0]
    assert "[paper writers=writer-sonnet reviewers=codex-reviewer,scholar]" in lm, lm
    assert "[paper" not in [l for l in lines if plain in l][0]
    ok("paper selections: idempotent migration, validation, stored on the message, in the QRL-INBOX line")


def test_redelivery_after_restart():
    db = LabDB()
    mid = db.researcher_send("μήνυμα πριν από restart", kind="proposal")
    assert any(mid in l for l in watch_cycle(db))
    lines = watch_cycle(db, first=True)  # a new session's watcher starts
    assert any(mid in l and "re-delivery" in l for l in lines), lines
    db.take(mid)
    assert not any(mid in l for l in watch_cycle(db, first=True))
    ok("undelivered or untaken messages are re-delivered when the coordinator restarts")


def test_decisions():
    db = LabDB()
    rid = db.ask("approval", "Batch S1", "σώμα", scope="research", blocking=True)
    expect_error(lambda: db.decide(rid, "answer", "x"), "δεν επιτρέπεται")
    expect_error(lambda: db.decide(rid, "changes", ""), "Γράψε")
    expect_error(lambda: db.decide(rid, "approve", actor="coordinator"), "Only the researcher")
    assert db.decide(rid, "reject", "όχι τώρα") == "rejected"
    expect_error(lambda: db.decide(rid, "approve"), "έχει ήδη κλείσει")
    lines = watch_cycle(db)
    assert any(l.startswith(f"QRL-DECISION {rid}") and "rejected" in l for l in lines), lines
    assert not any(rid in l for l in watch_cycle(db)), "decision delivered once"
    q = db.ask("question", "Ποιο namespace;", "σώμα")
    expect_error(lambda: db.decide(q, "answer", ""), "Γράψε")
    assert db.decide(q, "answer", "redis-exp") == "answered"
    expect_error(lambda: db.ask("approval", "x", "y", options=["answer"]), "not valid")
    # proposals stored, validated, mapped
    import labdb
    pr = db.ask("question", "Ποιο;", "σώμα", proposals=["x", "y", "z"], recommended=3)
    r = db.request(pr)
    assert json.loads(r["proposals"]) == ["x", "y", "z"] and r["recommended"] == 3
    expect_error(lambda: db.ask("question", "t", "b", proposals=list("abcd")), "At most 3")
    expect_error(lambda: db.ask("question", "t", "b", proposals=["a"], recommended=2), "recommended")
    expect_error(lambda: db.ask("question", "t", "b", recommended=1), "recommended")
    assert labdb.map_choice(r, "p3") == ("answer", "Επιλέχθηκε η Πρόταση 3: z")
    assert labdb.map_choice(r, "own", "κάτι")[0] == "answer"
    expect_error(lambda: labdb.map_choice(r, "yes"), "δεν επιτρέπεται")
    expect_error(lambda: labdb.map_choice(r, "own", ""), "Γράψε")
    ap = db.request(db.ask("approval", "t", "b", proposals=["a"]))
    assert labdb.map_choice(ap, "p1")[0] == "approve" and labdb.map_choice(ap, "no")[0] == "reject"
    assert labdb.map_choice(ap, "own", "t")[0] == "changes"
    expect_error(lambda: db.decide(pr, "answer", "x", actor="coordinator"), "Only the researcher")
    ok("decisions validated (allowed options, required text, researcher only, once) and delivered once")


SPEC_SCRIPT = """
import json, os, sys, time
d = os.environ['QRL_RUN_DIR']; n = int(sys.argv[1]); delay = float(sys.argv[2])
with open(os.path.join(d, 'metrics.jsonl'), 'a') as f:
    for s in range(n):
        f.write(json.dumps({'step': s, 'reward': s * 1.5}) + '\\n'); f.flush()
        json.dump({'step': s + 1, 'total': n}, open(os.path.join(d, 'progress.json'), 'w'))
        time.sleep(delay)
"""


def make_spec(name, steps, delay, hours=1.0, scope="sim", attempts=1):
    os.makedirs(os.path.join(TMP, "work"), exist_ok=True)
    with open(os.path.join(TMP, "work", "toy.py"), "w") as f:
        f.write(SPEC_SCRIPT)
    return {"name": name, "scope": scope, "cwd": "work", "max_attempts": attempts,
            "entries": [{"name": "seed0", "seed": 0, "cmd": [sys.executable, "toy.py", str(steps), str(delay)]}],
            "limits": {"wall_clock_hours": hours}}


def launch(*args):
    return subprocess.run([sys.executable, "tools/launch_run.py", *args], capture_output=True, text=True, timeout=60)


def wait_status(db, run_id, want, timeout=40):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = db.run(run_id)
        if r and r["status"] in want:
            return r
        time.sleep(0.5)
    raise AssertionError(f"{run_id} did not reach {want}: {db.run(run_id)}")


def test_launcher():
    db = LabDB()
    spec = make_spec("toy", 5, 0.05)
    rid = db.ask("approval", "toy run", "σώμα", scope="sim", spec=spec)
    out = launch("start", "--request", rid, "--entry", "0")
    assert out.returncode != 0 and "not approved" in out.stderr, out
    db.decide(rid, "reject", "όχι")
    out = launch("start", "--request", rid, "--entry", "0")
    assert out.returncode != 0 and "'rejected'" in out.stderr, out
    assert db.runs() == [], "a rejected request must start nothing"

    rid2 = db.ask("approval", "toy run 2", "σώμα", scope="sim", spec=spec)
    db.decide(rid2, "approve", "")
    out = launch("start", "--request", rid2, "--entry", "0")
    assert out.returncode == 0, out
    run_id = out.stdout.strip()
    r = wait_status(db, run_id, ("done", "failed"))
    assert r["status"] == "done" and r["exit_code"] == 0, r
    with open(os.path.join(r["run_dir"], "metrics.jsonl")) as f:
        assert len(f.read().splitlines()) == 5
    out = launch("start", "--request", rid2, "--entry", "0")
    assert out.returncode != 0 and "attempt" in out.stderr, out

    # tampering with the frozen spec invalidates the approval
    rid3 = db.ask("approval", "toy run 3", "σώμα", scope="sim", spec=spec)
    db.decide(rid3, "approve")
    p = db.request(rid3)["spec_path"]
    os.chmod(p, 0o644)
    s = json.load(open(p)); s["entries"][0]["cmd"].append("--evil"); json.dump(s, open(p, "w"))
    out = launch("start", "--request", rid3, "--entry", "0")
    assert out.returncode != 0 and "changed after approval" in out.stderr, out

    # stop request from the dashboard
    rid4 = db.ask("approval", "long", "σώμα", scope="sim", spec=make_spec("long", 1000, 0.1))
    db.decide(rid4, "approve")
    run4 = launch("start", "--request", rid4, "--all").stdout.strip().splitlines()[0]
    wait_status(db, run4, ("running",))
    db.request_stop(run4)
    r4 = wait_status(db, run4, ("stopped", "done", "failed"))
    assert r4["status"] == "stopped", r4

    # wall-clock limit
    rid5 = db.ask("approval", "limit", "σώμα", scope="sim", spec=make_spec("limit", 1000, 0.1, hours=0.0015))
    db.decide(rid5, "approve")
    run5 = launch("start", "--request", rid5, "--entry", "0").stdout.strip()
    r5 = wait_status(db, run5, ("stopped", "done", "failed"), timeout=60)
    assert r5["status"] == "stopped", r5

    # real-environment specs need context/namespace/rollback, and the current kube context must match
    bad = make_spec("real", 1, 0, scope="real")
    expect_error(lambda: db.ask("approval", "real", "σώμα", scope="real", spec=bad), "real.kube_context")
    good = dict(bad, real={"kube_context": "nonexistent-ctx", "namespace": "qrl", "rollback": "scale back to 3"})
    rid6 = db.ask("approval", "real", "σώμα", scope="real", spec=good)
    db.decide(rid6, "approve")
    out = launch("start", "--request", rid6, "--entry", "0")
    assert out.returncode != 0 and "kubectl context" in out.stderr, out
    ok("launcher: refuses unapproved/rejected/tampered/used/wrong-context; runs approved; stop and time limit work")


def test_hook():
    env = dict(os.environ, CLAUDE_PROJECT_DIR=TMP)
    for payload in (
        {"hook_event_name": "Notification", "message": "Claude needs your permission to use Bash"},
        {"hook_event_name": "PreToolUse", "agent_type": "codex:codex-rescue", "tool_name": "Bash",
         "tool_input": {"command": "node x task", "description": "Forward to Codex"}, "tool_response": "SECRET"},
    ):
        subprocess.run([sys.executable, "tools/lab_event_hook.py"], input=json.dumps(payload), text=True, env=env,
                       check=True)
    lines = open(os.path.join(TMP, ".lab", "events.jsonl")).read()
    assert "needs your permission" in lines and "Forward to Codex" in lines and "SECRET" not in lines
    ok("hook records permission waits and Codex activity, never tool outputs")


def test_agent_log():
    import agent_log
    path = os.path.join(TMP, ".lab", "events.jsonl")
    n0 = len(open(path).read().splitlines()) if os.path.exists(path) else 0
    aid = agent_log.start("codex-reviewer", "gpt-6.1-sol", "medium", "review sim v2", "M-1")
    agent_log.end(aid, "failed")
    recs = [json.loads(x) for x in open(path).read().splitlines()[n0:]]
    assert [r["hook_event_name"] for r in recs] == ["SubagentStart", "SubagentStop"], recs
    assert recs[0]["agent_type"] == "codex-reviewer" and recs[0]["model"] == "gpt-6.1-sol" and recs[0]["agent_id"] == aid
    assert recs[1]["status"] == "failed" and recs[0]["thread"] == "M-1"
    out = subprocess.run([sys.executable, "tools/agent_log.py", "start", "--agent", "codex-quick", "--task", "x"],
                         capture_output=True, text=True, check=True).stdout.strip()
    subprocess.run([sys.executable, "tools/agent_log.py", "end", out], check=True)
    assert out.startswith("log-") and json.loads(open(path).read().splitlines()[-1])["agent_id"] == out
    ok("agent_log start/end round trip (API and CLI)")


def test_agents_tab_roles():
    from streamlit.testing.v1 import AppTest
    now = time.time()
    path = os.path.join(TMP, ".lab", "events.jsonl")
    old = open(path).read() if os.path.exists(path) else ""
    ev = [
        {"hook_event_name": "SubagentStart", "agent_id": "a1", "agent_type": "codex-reviewer", "model": "gpt-6.1-sol",
         "effort": "medium", "summary": "REVIEWTASK", "ts": now - 100},
        {"hook_event_name": "SubagentStop", "agent_id": "a1", "status": "done", "ts": now - 40},
        {"hook_event_name": "SubagentStart", "agent_id": "a2", "agent_type": "codex-architect", "model": "gpt-6-astra",
         "effort": "high", "summary": "ARCHTASK", "ts": now - 30},
        {"hook_event_name": "SubagentStart", "agent_id": "a3", "agent_type": "engineer", "summary": "ENGTASK", "ts": now - 20},
    ]
    with open(path, "w") as f:
        f.write("".join(json.dumps(e) + "\n" for e in ev))
    try:
        at = AppTest.from_file(os.path.join(TMP, "dashboard", "app.py"), default_timeout=60).run()
        assert not at.exception, at.exception
        text = " ".join(m.value for m in at.markdown) + " ".join(c.value for c in at.caption)
        assert "codex-architect · gpt-6-astra · high" in text, text[:2000]
        assert "codex-reviewer · gpt-6.1-sol · medium: 1 εργασίες" in text
        frames = [d.value for d in at.dataframe]
        spans = [d for d in frames if "ρόλος" in d.columns][0]
        assert set(spans["ρόλος"]) >= {"codex-reviewer", "codex-architect", "engineer (Claude Sonnet)"}, spans
        r = spans[spans["ρόλος"] == "codex-reviewer"].iloc[0]
        assert r["μοντέλο"] == "gpt-6.1-sol" and r["κατάσταση"] == "done" and r["διάρκεια"] == "1 λεπτά"
        assert spans[spans["ρόλος"] == "codex-architect"].iloc[0]["κατάσταση"] == "running"
    finally:
        open(path, "w").write(old)
    ok("Agents tab shows each Codex role with model, task, duration, status and per-role count")


def test_uploads():
    import uploads
    root = tempfile.mkdtemp(prefix="up-", dir=TMP)
    day = "M-20261016-001"
    ups = os.path.realpath(os.path.join(root, "docs", "uploads"))
    saved = uploads.save_uploads([("../../x.txt", b"a"), ("/etc/passwd", b"b"), ("..", b"c"),
                                  ("a\\..\\y.pdf", b"d"), ("x.txt", b"e"), ("x.txt", b"f"), ("ε.pdf", b"g")], root, day)
    paths = [p for p, _ in saved]
    for p in paths:
        assert os.path.realpath(os.path.join(root, p)).startswith(ups + os.sep), p
    assert paths[0] == "docs/uploads/M-20261016-001/x.txt" and paths[4] == "docs/uploads/M-20261016-001/x-1.txt"
    assert paths[5] == "docs/uploads/M-20261016-001/x-2.txt" and paths[1].endswith("/passwd")
    assert open(os.path.join(root, paths[0]), "rb").read() == b"a"  # not overwritten
    assert not os.path.exists(os.path.join(root, "x.txt"))
    assert uploads.sanitize_filename("a\x00b\n.txt") == "ab.txt"
    big = None
    try:
        uploads.MAX_BYTES, old = 3, uploads.MAX_BYTES
        uploads.save_uploads([("big", b"1234")], root, day)
    except uploads.UploadError as e:
        big = e
    finally:
        uploads.MAX_BYTES = old
    assert big is not None
    blk = uploads.attachments_block([("docs/uploads/M-20261016-001/foo.pdf", 123 * 1024)])
    assert blk == "Συνημμένα:\n- docs/uploads/M-20261016-001/foo.pdf (123 KB)", blk
    assert uploads.body_with_attachments("", [("p", 2048)]) == "Συνημμένα:\n- p (2 KB)"
    assert uploads.body_with_attachments("hi", [("p", 2048)]).startswith("hi\n\nΣυνημμένα:")
    assert uploads.MAX_BYTES == 200 * 2**20
    assert "maxUploadSize = 200 " in open(os.path.join(TMP, ".streamlit", "config.toml")).read()
    assert uploads.attachment_paths(blk) == ["docs/uploads/M-20261016-001/foo.pdf"]
    assert uploads.attachment_paths("no block docs/uploads/x/y.pdf (1 KB)") == []
    # saved under the new message id, listed in the body, delivered in the QRL-INBOX line, never executable
    db = LabDB()
    mid = db.researcher_send("δες αυτά", attachments=[("λογος.pdf", b"%PDF"), ("run.sh", b"#!/bin/sh\nexit 1")], root=TMP)
    m = db.message(mid)
    paths = uploads.attachment_paths(m["body"])
    assert paths == [f"docs/uploads/{mid}/λογος.pdf", f"docs/uploads/{mid}/run.sh"], paths
    assert open(os.path.join(TMP, paths[0]), "rb").read() == b"%PDF"
    assert not os.access(os.path.join(TMP, paths[1]), os.X_OK)
    line = [l for l in watch_cycle(db) if mid in l][0]
    assert f"attachments=[{paths[0]}, {paths[1]}]" in line, line
    only = db.researcher_send("", attachments=[("a.txt", b"x")], root=TMP)  # attachment-only message
    assert uploads.attachment_paths(db.message(only)["body"]) == [f"docs/uploads/{only}/a.txt"]
    expect_error(lambda: db.researcher_send("", attachments=None), "κενό")
    uploads.MAX_BYTES, old = 3, uploads.MAX_BYTES
    try:
        n0 = len(db.threads(1000))
        try:
            db.researcher_send("x", attachments=[("big", b"1234")], root=TMP)
            raise AssertionError("cap not enforced")
        except uploads.UploadError:
            pass
        assert len(db.threads(1000)) == n0, "failed upload must not create a message"
    finally:
        uploads.MAX_BYTES = old
    ok("uploads: traversal, collisions, size cap, per-message dir, body block, bridge line")


def test_health_watch():
    import health_watch as hw
    d = hw.detect
    assert d("hello\n> working", True, "claude")["state"] == "ok"
    r = d("blah\nClaude usage limit reached ∙ resets 2:45am\n> ", True, "claude")
    assert r["state"] == "limit" and r["detail"] == "2:45am" and "2:45am" in r["line"], r
    r = d("5-hour limit reached ∙ resets at 11pm (UTC) │\n", True, "node")
    assert r["state"] == "limit" and r["detail"] == "11pm (UTC)", r
    assert d("Your usage limit has been reached", True)["state"] == "limit"
    assert d("Do you want to proceed?\n❯ 1. Yes\n  2. No", True)["state"] == "permission"
    assert d("Claude needs your permission to use Bash", True)["state"] == "permission"
    assert d("│ ❯ 1. Yes, and don't ask again", True)["state"] == "permission"
    assert d("API Error: 529 overloaded_error", True)["state"] == "api_error"
    # tool output that merely mentions these words must not raise a banner (seen live 2026-10-16)
    for t in ("6b6b034 health_watch: exact banner (usage limit, permission prompt, API error)",
              "request failed: rate limit exceeded", "Overloaded", "see the API Error docs"):
        assert d(t, True)["state"] == "ok", t
    assert d("anything", False)["state"] == "down"
    assert d("user@vm:~$ ", True, "bash")["state"] == "down"
    assert d("limit reached resets 1am\n" + "\n".join(f"line {i}" for i in range(40)), True)["state"] == "ok", "old text"
    assert len(d("API Error " + "x" * 1000, True)["line"]) == 300
    # state file: since is kept while the state is unchanged; event only on change; no pane text stored
    lab = tempfile.mkdtemp(prefix="hl-", dir=TMP)
    c1 = hw.step(d("API Error: x", True, "claude"), lab, now=100.0)
    c2 = hw.step(d("API Error: x", True, "claude"), lab, now=150.0)
    assert c1["since"] == c2["since"] == 100.0 and c2["checked"] == 150.0
    c3 = hw.step(d("fine", True, "claude"), lab, now=200.0)
    assert c3["state"] == "ok" and c3["since"] == 200.0
    evs = [json.loads(l) for l in open(os.path.join(lab, "events.jsonl"))]
    assert [e["state"] for e in evs] == ["api_error", "ok"] and all("ts" in e and "hook_event_name" in e for e in evs), evs
    ok("health_watch: detector table, state file, change events")


def test_k8s_view():
    import k8s_view as kv
    from unittest import mock
    pod_crash = {"kind": "Pod", "metadata": {"name": "w1", "namespace": "dinos", "creationTimestamp": "2026-10-16T00:00:00Z"},
                 "spec": {"nodeName": "n1", "containers": [{"name": "c"}]},
                 "status": {"phase": "Running", "conditions": [{"type": "Ready", "status": "False"}],
                            "containerStatuses": [{"name": "c", "ready": False, "restartCount": 7,
                                                   "state": {"waiting": {"reason": "CrashLoopBackOff"}}}]}}
    pod_pend = {"kind": "Pod", "metadata": {"name": "p2", "namespace": "dinos"}, "spec": {"containers": [{"name": "c"}]},
                "status": {"phase": "Pending", "conditions": [{"type": "PodScheduled", "status": "False",
                                                               "reason": "Unschedulable", "message": "0/1 nodes"}]}}
    pod_ok = {"kind": "Pod", "metadata": {"name": "r", "namespace": "kube-system"}, "spec": {"nodeName": "n1"},
              "status": {"phase": "Running", "conditions": [{"type": "Ready", "status": "True"}],
                         "containerStatuses": [{"name": "c", "ready": True, "restartCount": 0}]}}
    dep = {"kind": "Deployment", "metadata": {"name": "d", "namespace": "dinos"}, "spec": {"replicas": 2},
           "status": {"readyReplicas": 1, "availableReplicas": 1, "updatedReplicas": 2}}
    node = {"kind": "Node", "metadata": {"name": "n1"}, "status": {"capacity": {"cpu": "4", "memory": "8Gi"},
            "conditions": [{"type": "Ready", "status": "False", "reason": "KubeletNotReady"}]}}
    data = {"items": [pod_crash, pod_pend, pod_ok, dep, node]}
    v = kv.parse_snapshot(data)
    assert v["pods"][0]["health"] == "failing" and "c: CrashLoopBackOff" in v["pods"][0]["reasons"]
    assert v["pods"][0]["restarts"] == 7 and v["pods"][0]["ready"] == "0/1"
    assert v["pods"][1]["reasons"][0].startswith("Pending: Unschedulable")
    assert v["pods"][2]["health"] == "ok"
    assert v["deployments"][0]["ready"] == "1/2" and v["deployments"][0]["health"] == "degraded"
    assert v["nodes"][0]["health"] == "failing" and "NotReady" in v["nodes"][0]["reasons"][0]
    k = kv.kpis(v)
    assert (k["nodes_ready"], k["pods_running"], k["pods_pending"], k["deploys_ok"]) == (0, 2, 1, 0), k
    assert len(kv.failing_items(v)) == 4 and kv.pods_by_phase(v)["dinos"] == {"Running": 1, "Pending": 1}
    assert [p["name"] for p in kv.parse_snapshot(data, "kube-system")["pods"]] == ["r"]
    # allowlist
    for bad in (["apply", "-f", "x"], ["delete", "pod", "x"], ["exec", "x"], ["config", "use-context", "y"], []):
        try:
            kv.run_kubectl(bad)
            raise AssertionError(f"not refused: {bad}")
        except kv.K8sRefused:
            pass
    kv.check_allowed(["get", "pods"]); kv.check_allowed(["version"]); kv.check_allowed(["config", "current-context"])
    # cluster down (mock subprocess)
    refused = "E: dial tcp 127.0.0.1:6443: connect: connection refused\nmore"
    def fake(cmd, **kw):
        if "current-context" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "kind-x\n", "")
        return subprocess.CompletedProcess(cmd, 1, "", refused)
    kv.clear_cache()
    with mock.patch.object(subprocess, "run", fake):
        s = kv.fetch()
    assert not s["up"] and s["context"] == "kind-x" and "connection refused" in s["error"] and "more" not in s["error"]
    kv.clear_cache()
    ok("k8s_view: parsing, allowlist, cluster-down")


def test_file_view():
    import file_view as fv
    base = os.path.realpath(tempfile.mkdtemp(prefix="qrl-fv-"))
    root, outside = os.path.join(base, "root"), os.path.join(base, "outside")
    os.makedirs(os.path.join(root, "sub")); os.makedirs(os.path.join(root, ".ssh")); os.makedirs(outside)
    roots = [root]
    def w(p, s="x\n"):
        with open(p, "w") as f:
            f.write(s)
    w(os.path.join(outside, "secret.txt")); w(os.path.join(root, "a.py"), "print(1)\n")
    w(os.path.join(root, ".env")); w(os.path.join(root, ".ssh", "id_rsa")); w(os.path.join(root, "sub", "my_token.txt"))
    w(os.path.join(root, "kubeconfig")); w(os.path.join(root, "k.pem")); w(os.path.join(root, ".hidden"))
    os.symlink(outside, os.path.join(root, "escape")); os.symlink(os.path.join(outside, "secret.txt"), os.path.join(root, "esc.txt"))
    def err(p):
        try:
            fv.resolve(p, roots)
        except fv.FileViewError as e:
            return str(e)
        return None
    assert err(root + "/../../etc/passwd") == "outside" and err("/etc/passwd") == "outside" and err("relative/x") == "outside"
    assert err(root + "/escape") == "outside" and err(root + "/escape/secret.txt") == "outside" and err(root + "/esc.txt") == "outside"
    for p in (".env", ".ssh/id_rsa", "sub/my_token.txt", "kubeconfig", "k.pem"):
        assert err(os.path.join(root, p)) == "denied", p
    assert fv.is_denied("/home/u/.codex/auth.json") and fv.is_denied("/home/u/.kube/config") and fv.is_denied("/x/.config/gh/hosts.yml")
    assert not fv.is_denied("/x/a.py")
    assert err(os.path.join(root, "a.py")) is None and err(os.path.join(root, "nope")) == "missing"
    # listing: newest first, hidden toggle, denied / escaping entries omitted
    os.utime(os.path.join(root, "a.py"), (1_000_000_000, 1_000_000_000))
    os.utime(os.path.join(root, "sub"), (1_700_000_000, 1_700_000_000))
    names = [r["name"] for r in fv.list_dir(root, False, roots)]
    assert names == ["sub", "a.py"], names
    assert fv.list_dir(root, False, roots)[0]["mtime"].startswith("2023-11-1")
    assert [r["name"] for r in fv.list_dir(root, False, roots, newest_first=False)] == ["a.py", "sub"]
    hid = [r["name"] for r in fv.list_dir(root, True, roots)]
    assert ".hidden" in hid and ".env" not in hid and ".ssh" not in hid and "escape" not in hid and "esc.txt" not in hid, hid
    assert [c[0] for c in fv.breadcrumbs(os.path.join(root, "sub"), roots)] == ["root", "sub"]
    # path -> link transform
    L = lambda s: fv.linkify(s, roots)
    out = L(f"see {root}/a.py:5.")
    assert f"[{root}/a.py:5](?path={root}/a.py&line=5)." in out, out
    out = L(f"open {root}/sub/, then")
    assert f"[{root}/sub/](?path={root}/sub&" not in out and f"?path={root}/sub)" in out and out.endswith(", then"), out
    assert L(f"({root}/a.py)") == f"([{root}/a.py](?path={root}/a.py))", L(f"({root}/a.py)")
    assert L("see /etc/passwd and /home/x") == "see /etc/passwd and /home/x"  # outside roots: untouched
    assert L(f"{root}/.env") == f"{root}/.env"  # denied: no link
    assert L(f"```\n{root}/a.py\n```") == f"```\n{root}/a.py\n```"
    assert fv.split_ref("~/redis/x.py:12:3.") == ("~/redis/x.py", 12) and fv.split_ref("/a/b,") == ("/a/b", None)
    home_root = os.path.realpath(fv.ROOTS[1])
    assert "?path=" + home_root + "/x" in fv.linkify("~/simulations/x"), fv.linkify("~/simulations/x")
    # previews
    rows = "".join(f"{i},{i * i}\n" for i in range(700))
    w(os.path.join(root, "t.csv"), "n,sq\n" + rows)
    h, r, tr = fv.read_csv(os.path.join(root, "t.csv"))
    assert h == ["n", "sq"] and len(r) == 500 and tr and r[3] == ["3", "9"]
    w(os.path.join(root, "big.log"), "".join(f"l{i}\n" for i in range(5000)))
    ln, total, tr = fv.read_text(os.path.join(root, "big.log"))
    assert len(ln) == 2000 and tr and ln[0] == "l0"
    ln, _, _ = fv.read_text(os.path.join(root, "big.log"), tail=True)
    assert len(ln) == 500 and ln[-1] == "l4999"
    with open(os.path.join(root, "m.pth"), "wb") as f:
        f.write(b"\x00\x01binary")
    assert fv.kind_of(os.path.join(root, "m.pth")) == "binary" and len(fv.sha256(os.path.join(root, "m.pth"))) == 64
    shutil.rmtree(base)
    ok("file_view: traversal, symlink, deny list, ordering, links, previews")


def test_paper_build():
    import paper_build as pb
    # todo counter: markers in comments do not count
    assert pb.count_todos("a \\todo{x} b % \\todo{c}\n\\todo[inline]{y} 50\\% \\todo{z}") == 3
    assert pb.tbd_count(TMP) is not None and pb.tbd_count(TMP) >= 1
    assert all(r["todo"] >= 0 for r in pb.todo_counts(TMP)) and pb.todo_counts(TMP)
    # path guard (git repo of its own so nothing touches the real one)
    g = tempfile.mkdtemp(prefix="qrl-paper-")
    os.makedirs(os.path.join(g, "paper", "sections"))
    os.makedirs(os.path.join(g, "paper", "build"))
    with open(os.path.join(g, "paper", "sections", "a.tex"), "w") as f:
        f.write("old\n")
    with open(os.path.join(g, "secret.tex"), "w") as f:
        f.write("x")
    os.symlink(os.path.join(g, "secret.tex"), os.path.join(g, "paper", "link.tex"))
    for bad in ("../secret.tex", "/etc/passwd", "link.tex", "build/x.tex", "sections/a.py", "", "sections/../../secret.tex"):
        try:
            pb.safe_path(g, bad)
            raise AssertionError("accepted " + bad)
        except pb.PaperError:
            pass
    assert pb.safe_path(g, "sections/a.tex").endswith("sections/a.tex")
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    os.environ.update({k: env[k] for k in env if k.startswith("GIT_")})
    subprocess.run(["git", "-C", g, "init", "-q"], check=True)
    subprocess.run(["git", "-C", g, "add", "paper"], check=True)
    subprocess.run(["git", "-C", g, "commit", "-qm", "init"], check=True)
    h = pb.save_file(g, "sections/a.tex", "new\n")
    assert h and open(os.path.join(g, "paper", "sections", "a.tex")).read() == "new\n"
    msg = subprocess.run(["git", "-C", g, "log", "-1", "--format=%s"], capture_output=True, text=True).stdout.strip()
    assert msg == "paper: edit sections/a.tex from dashboard", msg
    shutil.rmtree(g)
    # real latexmk, IEEE variant
    if shutil.which("latexmk"):
        r = pb.compile(TMP, "ieee", timeout=120)
        assert r["ok"] and os.path.getsize(r["pdf"]) > 1000, r["log_tail"]
        assert pb.build_time(TMP, "ieee")
    else:
        print("  --  latexmk not installed, compile test skipped")
    ok("paper_build: todo counter, path guard, save+commit, latexmk IEEE compile")


def test_paper_tab():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(os.path.join(TMP, "dashboard", "app.py"), default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    assert any(b.label == "Μεταγλώττιση" for b in at.button)
    assert any(s.label == "Venue" for s in at.selectbox)
    assert any(t.label == "Επεξεργασία" for t in at.toggle)
    assert any(w.label == "Συγγραφή" and w.value == ["writer-sonnet"] for w in at.multiselect)
    assert any(w.label == "Review" and w.value == ["codex-reviewer"] for w in at.multiselect)
    pci = [c for c in at.chat_input if c.key == "paper_composer"][0]
    at.multiselect(key="paper_reviewers").set_value(["codex-architect", "scholar"])
    pci.set_value("paper hello AppTestP").run()
    assert not at.exception, at.exception
    db = LabDB()
    tid = [t for t in db.threads() if t["title"] == "Paper — συγγραφή"][0]["thread_id"]
    sent = [m for m in db.thread(tid) if "AppTestP" in m["body"]][0]
    assert json.loads(sent["req_writers"]) == ["writer-sonnet"], sent
    assert json.loads(sent["req_reviewers"]) == ["codex-architect", "scholar"], sent
    assert any("AppTestP" in m.value for m in at.markdown), "message not rendered in the paper chat"
    ok("paper tab: renders; chat creates the thread and stores writer/reviewer selections")


def test_dashboard():
    from streamlit.testing.v1 import AppTest
    db = LabDB()
    at = AppTest.from_file(os.path.join(TMP, "dashboard", "app.py"), default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    # send a message through st.chat_input (text path; AppTest cannot attach files to chat_input)
    at.chat_input[0].set_value("hello dashboard από το AppTest").run()
    assert not at.exception, at.exception
    tid = db.threads(1)[0]["thread_id"]
    sent = [m for m in db.thread(tid) if "AppTest" in m["body"]]
    assert sent and sent[0]["status"] == "new" and sent[0]["author"] == "researcher", sent
    # a second message in a row lands in the same thread, replying to the latest message
    at.chat_input[0].set_value("δεύτερο μήνυμα AppTest2").run()
    assert not at.exception, at.exception
    thr = db.thread(tid)
    assert [m["body"] for m in thr if m["author"] == "researcher"][-1] == "δεύτερο μήνυμα AppTest2", thr
    assert thr[-1]["reply_to"] == sent[0]["id"] and thr[-1]["thread_id"] == tid, thr
    assert db.threads(1)[0]["thread_id"] == tid
    at.selectbox(key="req_model_sel").set_value("sonnet"); at.selectbox(key="req_effort_sel").set_value("high")
    at.chat_input[0].set_value("routed AppTestR").run()
    rm = [m for m in db.thread(tid) if "AppTestR" in m["body"]][0]
    assert (rm["req_model"], rm["req_effort"]) == ("sonnet", "high"), rm
    assert any("sonnet/high" in x.value for x in at.caption), "tag not shown"
    at.selectbox(key="req_model_sel").set_value(None); at.selectbox(key="req_effort_sel").set_value("med")
    thr = db.thread(tid)
    n_threads = len(db.threads(100))
    # in_progress shows the live indicator
    with db.tx() as c:
        c.execute("UPDATE messages SET status='in_progress' WHERE id=?", (thr[-1]["id"],))
    at.run()
    assert any("ο συντονιστής δουλεύει" in (i.value or "") for i in at.info), "indicator missing"
    # coordinator replies; the thread shows it
    db.post("coordinator", "Απάντηση συντονιστή στο AppTest", thr[-1]["id"], set_status="done")
    at.run()
    assert not at.exception, at.exception
    assert any("Απάντηση συντονιστή στο AppTest" in md.value for md in at.markdown), "reply not rendered"
    # explicit «Νέο θέμα» opens a new thread
    at.button[[b.label for b in at.button].index("➕ Νέο θέμα")].click().run()
    at.chat_input[0].set_value("νέο θέμα AppTest3").run()
    assert not at.exception, at.exception
    assert len(db.threads(100)) == n_threads + 1 and db.threads(1)[0]["thread_id"] != tid
    # Decisions tab: one request at a time, oldest first, with proposals
    for r in db.requests(state="open"):
        db.withdraw(r["id"], reason="test cleanup")
    a = db.ask("approval", "AppTest approve me", "σώμα", scope="research", proposals=["Α-πρόταση", "Β-πρόταση"],
               recommended=2)
    b = db.ask("approval", "AppTest reject me", "σώμα", scope="research")
    c = db.ask("proposal", "AppTest own", "σώμα", scope="research")
    at.run()
    assert not at.exception, at.exception
    assert any("Αίτημα 1 από 3" in md.value for md in at.markdown), "n of N missing"
    assert [r.key for r in at.radio if str(r.key).startswith("choice_")] == [f"choice_{a}"], "one at a time"
    opts = at.radio(key=f"choice_{a}").options
    assert any("Πρόταση 2: Β-πρόταση" in o and "⭐" in o for o in opts) and not any("Πρόταση 1" in o and "⭐" in o for o in opts), opts
    def submit():
        [x for x in at.button if x.label == "Υποβολή απόφασης"][0].click()
        at.run()
        assert not at.exception, at.exception
    # no choice -> refused
    submit()
    assert db.request(a)["state"] == "open" and any("Διάλεξε" in e.value for e in at.error)
    at.radio(key=f"choice_{a}").set_value("p2"); submit()
    ra = db.request(a)
    assert ra["state"] == "approved" and "Πρόταση 2: Β-πρόταση" in ra["decision_text"], ra
    assert any("Πρόταση 2: Β-πρόταση" in l for l in watch_cycle(db)), "bridge line lacks proposal text"
    # next one shown automatically (b); navigate next/prev
    assert [r.key for r in at.radio if str(r.key).startswith("choice_")] == [f"choice_{b}"]
    at.button(key="dec_next").click().run()
    assert [r.key for r in at.radio if str(r.key).startswith("choice_")] == [f"choice_{c}"]
    at.button(key="dec_prev").click().run()
    at.radio(key=f"choice_{b}").set_value("no"); submit()
    assert db.request(b)["state"] == "rejected"
    # own proposal without text must be refused with a visible error, state unchanged
    at.radio(key=f"choice_{c}").set_value("own"); submit()
    assert db.request(c)["state"] == "open" and any("Γράψε" in e.value for e in at.error)
    at.text_area(key=f"note_{c}").set_value("κάνε το αλλιώς"); submit()
    rc = db.request(c)
    assert rc["state"] == "changes_requested" and "Δική μου πρόταση: κάνε το αλλιώς" in rc["decision_text"], rc
    # old request without proposals, question kind
    q = db.ask("question", "AppTest q", "σώμα", scope="research")
    at.run()
    at.radio(key=f"choice_{q}").set_value("own"); at.text_area(key=f"note_{q}").set_value("redis-exp"); submit()
    assert db.request(q)["state"] == "answered"
    # the author/model label is rendered
    cur = db.threads(1)[0]["thread_id"]
    db.post("codex", "labelled", cur, kind="contribution", model="gpt-6-sol")
    db.post("coordinator", "plain", cur)
    at.run()
    caps = [x.value for x in at.caption]
    assert any("Codex (OpenAI) · gpt-6-sol**" in v for v in caps), caps
    assert any(v.startswith("**Συντονιστής (Claude Opus)** ·") for v in caps), caps  # no model: author only
    ok("dashboard: model label rendered")
    amid = db.researcher_send("με αρχείο", thread_id=cur, attachments=[("n.txt", b"hello")], root=TMP)
    at.run()
    assert not at.exception, at.exception
    assert len(at.get("download_button")) >= 1, "download button missing"
    assert any("?path=" in md.value and "uploads" in md.value for md in at.markdown), "deep link missing"
    at.run()
    assert not at.exception, at.exception
    assert len(at.tabs) >= 9 and any("Kubernetes" in tb.label for tb in at.tabs), [tb.label for tb in at.tabs]
    hp = os.path.join(TMP, ".lab", "health.json")
    json.dump({"state": "limit", "detail": "2:45am", "line": "limit reached ∙ resets 2:45am", "since": time.time() - 125,
               "checked": time.time()}, open(hp, "w"))
    at.run()
    errs = [e.value for e in at.error]
    assert any(v.startswith("Ο συντονιστής σταμάτησε: όριο χρήσης Claude — ξαναρχίζει 2:45am (ώρα VM) · εδώ και 2 λεπτά")
               for v in errs), errs
    json.dump({"state": "permission", "detail": "", "line": "", "since": time.time(), "checked": time.time()}, open(hp, "w"))
    at.run()
    assert any("Περιμένει άδεια στο terminal: tmux attach -t lab" in e.value for e in at.error)
    json.dump({"state": "down", "detail": "", "line": "", "since": time.time(), "checked": time.time()}, open(hp, "w"))
    at.run()
    assert any("Ο συντονιστής δεν τρέχει" in e.value for e in at.error)
    os.remove(hp)
    at.run()
    assert not any("Ο συντονιστής" in e.value and "εδώ και" in e.value for e in at.error), "stale/missing = no banner"
    ok("dashboard: Kubernetes tab renders without exception (cluster down or up)")
    assert any("Αρχεία" in tb.label for tb in at.tabs), [tb.label for tb in at.tabs]
    import file_view
    file_view.ROOTS.append(os.path.realpath(TMP))  # the temp kit is not an allowed root otherwise
    at.query_params["path"] = os.path.join(TMP, "tools", "labq.py")
    at.query_params["line"] = "3"
    at.run()
    assert not at.exception, at.exception
    assert any("labq.py" in (md.value or "") for md in at.markdown), "file preview missing"
    ok("dashboard: Αρχεία tab renders a deep link")
    at = AppTest.from_file(os.path.join(TMP, "dashboard", "app.py"), default_timeout=60)
    at.run()
    assert not at.exception and at.get("audio_input"), "voice recorder widget missing"
    assert any("Φωνητικό" in (w.proto.label or "") for w in at.get("audio_input"))
    ok("dashboard: voice recorder widget renders in the chat")


def test_deputy():
    import deputy
    shutil.copy(os.path.join(KIT, "AGENTS.md"), os.path.join(TMP, "AGENTS.md"))
    lab = os.path.join(TMP, ".lab")
    db = LabDB()
    for r in db.requests(): db.withdraw(r["id"]) if r["state"] == "open" else None
    base = len(deputy.deputy_requests(db))
    lim = {"state": "limit", "detail": "2:45am", "since": 1000.0}
    # trigger: ok / short down / permission file nothing; limit files one; dedup while open and 6 h after answer
    for h in ({"state": "ok"}, {"state": "permission", "since": 0}, {"state": "down", "since": 1000.0}):
        assert deputy.maybe_file_request(db, h, now=1300.0) is None
    rid = deputy.maybe_file_request(db, lim, now=1300.0)
    r = db.request(rid)
    assert r["author"] == "system" and r["kind"] == "proposal" and "2:45am" in r["title"] and r["title"].startswith("Να αναλάβει ο Codex")
    assert deputy.maybe_file_request(db, lim, now=1400.0) is None, "open request"
    db.decide(rid, "reject")
    assert deputy.maybe_file_request(db, lim, now=time.time() + 3600) is None, "answered < 6 h ago"
    assert deputy.maybe_file_request(db, lim, now=time.time() + 7 * 3600) is not None, "after 6 h a new one"
    assert len(deputy.deputy_requests(db)) == base + 2
    assert deputy.maybe_file_request(db, {"state": "down", "since": 0.0}, now=time.time() + 8 * 3600) is None, "dedup also for down"
    ok("deputy: trigger and de-duplication")

    calls = []

    def fake(cmd, **kw):
        calls.append((cmd, kw))
        out = cmd[cmd.index("-o") + 1]
        with open(out, "w", encoding="utf-8") as f:
            f.write(FAKE["text"])
        return subprocess.CompletedProcess(cmd, FAKE.get("rc", 0), "", "")
    FAKE = {"text": "Απάντηση.\nNEEDS_EXECUTION: no"}

    # not approved: nothing runs, nothing is taken
    mid = db.researcher_send("τι κάνουμε;")
    health = {"state": "limit", "detail": "x"}
    assert deputy.cycle(db, lab, health, run=fake) == "stop" and not calls
    assert db.message(mid)["status"] == "new"
    ok("deputy: not approved means nothing runs")

    # approve the newest open deputy request
    open_r = [r for r in deputy.deputy_requests(db) if r["state"] == "open"][0]
    db.decide(open_r["id"], "approve")
    assert deputy.approved_request(db, lab)["id"] == open_r["id"]
    # message selection: new/delivered only, taken or done ones are skipped
    m2 = db.researcher_send("δεύτερο"); m3 = db.researcher_send("τρίτο"); db.take(m3)
    sel = [m["id"] for m in deputy.pick_messages(db)]
    assert mid in sel and m2 in sel and m3 not in sel, sel
    db.set_status(m2, "done")
    sel = [m["id"] for m in deputy.pick_messages(db)]
    assert mid in sel and m2 not in sel and m3 not in sel
    # command construction + answer posting
    assert deputy.cycle(db, lab, health, run=fake) >= 1
    cmd, kw = [c for c in calls if "τι κάνουμε;" in c[1]["input"]][0]
    assert cmd[:4] == ["codex", "exec", "--sandbox", "read-only"] and 'approval_policy="never"' in cmd
    assert "gpt-6-sol" in cmd and 'model_reasoning_effort="medium"' in cmd and cmd[-1] == "-" and "-C" in cmd
    assert kw["timeout"] == 600 and "Never invent numbers" in kw["input"]
    assert "τι κάνουμε;" in kw["input"] and ".env" not in cmd
    th = db.thread(mid)
    assert th[-1]["author"] == "codex" and th[-1]["model"] == "gpt-6-sol · αναπληρωτής" and "NEEDS" not in th[-1]["body"]
    assert db.message(mid)["status"] == "done"
    assert not os.path.exists(os.path.join(lab, "deputy_queue.jsonl"))
    ok("deputy: message selection, command construction, answer")

    # needs execution: waiting_approval + queue line; a failing codex is queued too
    FAKE["text"] = "Χρειάζεται αλλαγή κώδικα.\nNEEDS_EXECUTION: yes"
    m4 = db.researcher_send("άλλαξε τον κώδικα")
    deputy.cycle(db, lab, health, run=fake)
    assert db.message(m4)["status"] == "waiting_approval" and "σε ουρά για τον Claude" in db.thread(m4)[-1]["body"]
    FAKE["rc"] = 1
    m5 = db.researcher_send("ξανά")
    deputy.cycle(db, lab, health, run=fake)
    q = [json.loads(l) for l in open(os.path.join(lab, "deputy_queue.jsonl"))]
    assert [e["message"] for e in q] == [m4, m5] and q[1]["reason"] == "codex exit 1", q
    assert db.message(m5)["status"] == "waiting_approval"
    ok("deputy: queue writing")

    # stop as soon as health is ok: note in the threads, approval consumed, no second run
    n = len(calls)
    assert deputy.cycle(db, lab, {"state": "ok"}, run=fake) == "stop"
    assert "σταματά" in db.thread(m4)[-1]["body"] and len(calls) == n
    assert deputy.approved_request(db, lab) is None
    assert deputy.cycle(db, lab, health, run=fake) == "stop"
    ok("deputy: stops on ok")


def test_voice():
    import voice

    class Seg:
        def __init__(self, t): self.text = t

    class Info:
        def __init__(self, l): self.language = l

    class Fake:
        def __init__(self, by_lang): self.by_lang, self.calls = by_lang, []

        def transcribe(self, audio, language=None, **kw):
            self.calls.append(language)
            return iter([Seg(x) for x in self.by_lang.get(language, [])]), Info(language or "en")
    f = Fake({"el": [" Καλημέρα ", "κόσμε "]})
    assert voice.transcribe(b"RIFFxx", f) == ("Καλημέρα κόσμε", "el") and f.calls == ["el"]
    f = Fake({None: ["hello"]})
    assert voice.transcribe(b"RIFFxx", f) == ("hello", "en") and f.calls == ["el", None], "auto fallback"
    assert voice.transcribe(b"RIFFxx", Fake({})) == ("", None)
    assert voice.transcribe(b"", f) == ("", None)
    os.environ["QRL_WHISPER_MODEL"] = "medium"
    assert voice.model_name() == "medium"
    del os.environ["QRL_WHISPER_MODEL"]
    assert voice.model_name() == "small"
    # the recording is kept as docs/uploads/<M-id>/voice.wav via the normal send path
    db = LabDB()
    mid = db.researcher_send("φωνητικό κείμενο", attachments=[("voice.wav", b"RIFF....")], req_model="sonnet",
                             req_effort="high", root=TMP)
    assert os.path.exists(os.path.join(TMP, "docs", "uploads", mid, "voice.wav"))
    assert "voice.wav" in db.message(mid)["body"] and db.message(mid)["req_model"] == "sonnet"
    ok("voice: transcribe with mocked model, fallback, model env, wav kept as attachment")


def test_web_terminal():
    import web_terminal as wt
    assert wt.HOST == "127.0.0.1" and wt.PORT == 8502
    assert wt.token_ok("abc", "abc") and not wt.token_ok("", "abc") and not wt.token_ok(None, "abc")
    assert not wt.token_ok("abd", "abc") and not wt.token_ok("abc", "")
    # idle logic
    assert not wt.is_idle(1000, 1000 + 1799) and wt.is_idle(1000, 1000 + 1800) and wt.IDLE_LIMIT == 1800
    # command construction
    cmd = wt.start_command("/k", "lab", "terminal")
    assert cmd[:7] == ["tmux", "new-window", "-d", "-t", "lab", "-n", "terminal"], cmd
    assert "/k/.venv/bin/python tools/web_terminal.py" in cmd[-1] and cmd[cmd.index("-c") + 1] == "/k"
    assert wt.stop_command() == ["tmux", "kill-window", "-t", "lab:terminal"]
    # token file mode
    tp = os.path.join(TMP, "tok")
    tok = wt.write_token(tp)
    assert oct(os.stat(tp).st_mode & 0o777) == "0o600" and open(tp).read() == tok and len(tok) >= 32
    # requests without / with a wrong token are rejected; the right token is served (no shell is spawned)
    import tornado.testing
    import unittest

    class T(tornado.testing.AsyncHTTPTestCase):
        def get_app(self):
            return wt.make_app("secret", {"last": 0})[0]

        def test_auth(self):
            assert self.fetch("/").code == 403
            assert self.fetch("/?token=wrong").code == 403
            assert self.fetch("/websocket").code == 403
            r = self.fetch("/?token=secret")
            assert r.code == 200 and b"xterm@5.3.0" in r.body

    res = unittest.TextTestRunner(stream=io.StringIO()).run(unittest.defaultTestLoader.loadTestsFromTestCase(T))
    assert res.wasSuccessful(), res.failures + res.errors
    ok("web terminal: token check, bind address, idle timeout, tmux command, token mode 600, HTTP auth")


def test_paper_plots():
    import summarize_runs as sr
    import paper_plots as pp
    lab = os.path.join(TMP, "fixlab")
    def mk(name, entry, eps, imgs=()):
        d = os.path.join(lab, "runs", name)
        os.makedirs(os.path.join(d, "results", "model_1"), exist_ok=True)
        json.dump({"entry_spec": {"name": entry}}, open(os.path.join(d, "spec_entry.json"), "w"))
        json.dump({"status": "done"}, open(os.path.join(d, "launcher.json"), "w"))
        with open(os.path.join(d, "metrics.jsonl"), "w") as f:
            f.write(json.dumps({"step": 0, "loss": 1.0}) + "\n")  # ignored: no model/reward
            for model, rew, vm in eps:
                f.write(json.dumps({"step": 1, "model": model, "reward": rew, "mean_vms": vm}) + "\n")
        for im in imgs:
            open(os.path.join(d, "results", im), "wb").write(b"x")
        return d
    mk("20260101-000000-R-20260101-001-e0-a1", "fixed-seed0", [(1, 100.0, 2.0), (1, 300.0, 4.0), (2, 10.0, 1.0)],
       ["accumulated_rewards.jpg", "model_1/evaluation_metrics.jpg", "model_1/notes.txt"])
    mk("20260101-000000-R-20260101-001-e1-a1", "fixed-seed1", [(1, 400.0, 3.0), (2, 30.0, 1.0)])
    mk("20260101-000000-R-20260101-001-e2-a1", "legacy-seed0", [(1, 5.0, 9.0)])
    mk("20260101-000000-R-20260101-002-e0-a1", "other-seed0", [(1, 1.0, 1.0)])
    assert sr.request_ids(lab) == ["R-20260101-001", "R-20260101-002"]
    rows = sr.collect("R-20260101-001", lab)
    assert len(rows) == 3
    agg = sr.aggregate_by_seed(rows)
    assert set(agg) == {"fixed", "legacy"} and set(agg["fixed"]) == {1, 2}
    f1 = agg["fixed"][1]  # seed0 mean 200, seed1 mean 400 -> mean 300, sd 141.42
    assert f1["n_seeds"] == 2 and f1["reward_mean"] == 300.0 and abs(f1["reward_sd"] - 141.4213562) < 1e-6
    assert f1["vms_mean"] == 3.0 and f1["vms_sd"] == 0.0, f1  # both seeds average 3.0 VMs
    assert agg["legacy"][1]["reward_sd"] == 0.0
    imgs = pp.find_result_images(rows[0][0] and os.path.join(lab, "runs", rows[0][0]))
    assert [(g, c) for g, c, _ in imgs] == [("(results)", "accumulated_rewards.jpg"),
                                            ("model_1", os.path.join("model_1", "evaluation_metrics.jpg"))], imgs
    for metric in ("reward", "vms"):
        fig = pp.comparison_figure(agg, metric)
        labels = [t.get_text() for ax in fig.axes for t in ax.get_xticklabels()]
        assert "fixed trained for 1k steps" in labels and "legacy trained for 1k steps" in labels, labels
    ok("paper plots: aggregation over seeds, request ids, result images, comparison figure")


if __name__ == "__main__":
    print(f"QRL-Lab tests in {TMP}")
    try:
        test_message_round_trip()
        test_model_label()
        test_routing_tags()
        test_paper_selections()
        test_redelivery_after_restart()
        test_decisions()
        test_hook()
        test_launcher()
        test_agent_log()
        test_uploads()
        test_health_watch()
        test_deputy()
        test_voice()
        test_k8s_view()
        test_file_view()
        test_web_terminal()
        test_paper_plots()
        test_paper_build()
        try:
            import streamlit  # noqa: F401
            test_dashboard()
            test_agents_tab_roles()
            test_paper_tab()
        except ImportError:
            print("  --  dashboard test skipped (streamlit not installed in this interpreter)")
        print(f"ALL PASSED ({len(PASSED)})")
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
