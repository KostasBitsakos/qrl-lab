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
for sub in ("tools", "dashboard", "docs", ".streamlit"):
    shutil.copytree(os.path.join(KIT, sub), os.path.join(TMP, sub))
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


def test_uploads():
    import datetime
    import uploads
    root = tempfile.mkdtemp(prefix="up-", dir=TMP)
    day = datetime.date(2026, 10, 16)
    ups = os.path.realpath(os.path.join(root, "docs", "uploads"))
    saved = uploads.save_uploads([("../../x.txt", b"a"), ("/etc/passwd", b"b"), ("..", b"c"),
                                  ("a\\..\\y.pdf", b"d"), ("x.txt", b"e"), ("x.txt", b"f"), ("ε.pdf", b"g")], root, day)
    paths = [p for p, _ in saved]
    for p in paths:
        assert os.path.realpath(os.path.join(root, p)).startswith(ups + os.sep), p
    assert paths[0] == "docs/uploads/2026-10-16/x.txt" and paths[4] == "docs/uploads/2026-10-16/x-1.txt"
    assert paths[5] == "docs/uploads/2026-10-16/x-2.txt" and paths[1].endswith("/passwd")
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
    blk = uploads.attachments_block([("docs/uploads/2026-10-16/foo.pdf", 123 * 1024)])
    assert blk == "Συνημμένα:\n- docs/uploads/2026-10-16/foo.pdf (123 KB)", blk
    assert uploads.body_with_attachments("", [("p", 2048)]) == "Συνημμένα:\n- p (2 KB)"
    assert uploads.body_with_attachments("hi", [("p", 2048)]).startswith("hi\n\nΣυνημμένα:")
    ok("uploads: traversal, collisions, size cap, body block")


def test_dashboard():
    from streamlit.testing.v1 import AppTest
    db = LabDB()
    at = AppTest.from_file(os.path.join(TMP, "dashboard", "app.py"), default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    # send a new message from the composer
    at.text_area(key="composer_text").input("hello dashboard από το AppTest")
    at.button[[b.label for b in at.button].index("Αποστολή")].click()
    at.run()
    assert not at.exception, at.exception
    sent = [m for m in db.thread(db.threads(1)[0]["thread_id"]) if "AppTest" in m["body"]]
    assert sent and sent[0]["status"] == "new" and sent[0]["author"] == "researcher", sent
    # coordinator replies; the thread shows it
    db.post("coordinator", "Απάντηση συντονιστή στο AppTest", sent[0]["id"], set_status="done")
    at.run()
    assert not at.exception, at.exception
    assert any("Απάντηση συντονιστή στο AppTest" in md.value for md in at.markdown), "reply not rendered"
    # approve one request and reject another from the Decisions tab
    a = db.ask("approval", "AppTest approve me", "σώμα", scope="research")
    b = db.ask("approval", "AppTest reject me", "σώμα", scope="research")
    at.run()
    labels = [x.label for x in at.button]
    # forms render in ts order; find the buttons of each request by their form key
    def click(req_id, label):
        for btn in at.button:
            if btn.label == label and req_id in str(btn.form_id):
                btn.click()
                return
        raise AssertionError(f"button {label} for {req_id} not found in {labels}")
    click(a, "✅ Έγκριση"); at.run()
    assert not at.exception, at.exception
    assert db.request(a)["state"] == "approved"
    click(b, "⛔ Απόρριψη"); at.run()
    assert db.request(b)["state"] == "rejected"
    # changes without text must be refused with a visible error, state unchanged
    c = db.ask("proposal", "AppTest changes", "σώμα", scope="research")
    at.run()
    click(c, "✏️ Ζητώ αλλαγές"); at.run()
    assert db.request(c)["state"] == "open" and any("Γράψε" in e.value for e in at.error)
    ok("dashboard: send message, render reply, approve, reject, refuse changes without text")


if __name__ == "__main__":
    print(f"QRL-Lab tests in {TMP}")
    try:
        test_message_round_trip()
        test_redelivery_after_restart()
        test_decisions()
        test_hook()
        test_launcher()
        test_uploads()
        try:
            import streamlit  # noqa: F401
            test_dashboard()
        except ImportError:
            print("  --  dashboard test skipped (streamlit not installed in this interpreter)")
        print(f"ALL PASSED ({len(PASSED)})")
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
