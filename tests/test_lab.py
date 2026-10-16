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
    at.run()
    assert not at.exception, at.exception
    assert len(at.tabs) >= 9 and any("Kubernetes" in tb.label for tb in at.tabs), [tb.label for tb in at.tabs]
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


if __name__ == "__main__":
    print(f"QRL-Lab tests in {TMP}")
    try:
        test_message_round_trip()
        test_model_label()
        test_redelivery_after_restart()
        test_decisions()
        test_hook()
        test_launcher()
        test_uploads()
        test_k8s_view()
        test_file_view()
        try:
            import streamlit  # noqa: F401
            test_dashboard()
        except ImportError:
            print("  --  dashboard test skipped (streamlit not installed in this interpreter)")
        print(f"ALL PASSED ({len(PASSED)})")
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
