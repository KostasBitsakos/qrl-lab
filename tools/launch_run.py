#!/usr/bin/env python3
"""Approval-enforced experiment launcher for QRL-Lab. Run from ~/qrl-lab.

  launch_run.py start --request R-... --entry 0     start one entry of an approved run spec
  launch_run.py start --request R-... --all         start the next entries not yet run, up to spec.max_parallel
                                                    (default 1); call again when a run finishes
  launch_run.py list                                runs and their status

It refuses unless ALL hold:
  - the request exists, is an 'approval' and its state is 'approved' (decided by the researcher in the dashboard);
  - the stored spec still hashes to the approved hash (any edit after approval invalidates it);
  - the entry exists and has attempts left (spec.max_attempts, default 1);
  - for scope 'real': the current kubectl context equals spec.real.kube_context.
Each run gets .lab/runs/<run_id>/ with the spec entry, the code commit, output.log and launcher.json.
A detached supervisor enforces limits.wall_clock_hours and honours stop requests from the dashboard.
This is a guard against mistakes, not an OS security boundary: see docs/PLAN.md §6.
"""
import argparse
import datetime as dt
import json
import os
import signal
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from labdb import LabDB, LabError, canonical_hash, lab_dir, lab_root, now, validate_spec  # noqa: E402

POLL = 5
# Core pinning for scope 'sim' runs (R-20261017-017). One place for the default: env QRL_SIM_CPUS (e.g. "8-39" or
# "8-15,20") overrides the constant; the spec key "cpu_affinity" (same syntax, or a list of ints) overrides both.
# Cores 0-7 stay free for the system (dashboard, kube-apiserver, kubelet, ...). Scope 'real' is never pinned.
DEFAULT_SIM_CPUS = "8-39"
THREAD_ENV = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS")


def parse_cpus(v):
    """'8-39', '0,2-3' or [0, 1] -> sorted list of ints."""
    if isinstance(v, (list, tuple)):
        return sorted({int(x) for x in v})
    out = set()
    for part in str(v).split(","):
        part = part.strip()
        if not part:
            continue
        a, _, b = part.partition("-")
        out.update(range(int(a), int(b or a) + 1))
    return sorted(out)


def pin_plan(scope, spec_affinity=None, spec_env=None, environ=None, available=None):
    """(cores or None, env_updates). Pinning only for scope 'sim'; cores are intersected with the machine's
    allowed set and skipped (None) if that leaves nothing or all of them (fewer cores than the request).
    Threads default to 1 (spec 'env_threads' dict may override)."""
    environ = os.environ if environ is None else environ
    if scope != "sim":
        return None, {}
    want = parse_cpus(spec_affinity if spec_affinity is not None else environ.get("QRL_SIM_CPUS", DEFAULT_SIM_CPUS))
    if available is None:
        available = os.sched_getaffinity(0) if hasattr(os, "sched_getaffinity") else set()
    cores = sorted(set(want) & set(available))
    if not cores or len(cores) == len(available):
        cores = None
    upd = {k: "1" for k in THREAD_ENV}
    upd.update({k: str(v) for k, v in (spec_env or {}).items()})
    return cores, upd


def git_sha(path):
    try:
        out = subprocess.run(["git", "-C", path, "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10)
        sha = out.stdout.strip()
        if not sha:
            return None
        dirty = subprocess.run(["git", "-C", path, "status", "--porcelain"], capture_output=True, text=True,
                               timeout=10).stdout.strip()
        return sha + ("+dirty" if dirty else "")
    except (OSError, subprocess.SubprocessError):
        return None


def kube_context():
    try:
        out = subprocess.run(["kubectl", "config", "current-context"], capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def load_approved_spec(db, rid):
    r = db.request(rid)
    if r is None:
        raise LabError(f"Unknown request {rid}.")
    if r["kind"] != "approval":
        raise LabError(f"{rid} is a {r['kind']}, not an approval.")
    if r["state"] != "approved":
        raise LabError(f"{rid} is '{r['state']}', not approved. Nothing was started.")
    if not r["spec_path"] or not r["spec_hash"]:
        raise LabError(f"{rid} has no run spec attached.")
    with open(r["spec_path"], encoding="utf-8") as f:
        spec = json.load(f)
    if canonical_hash(spec) != r["spec_hash"]:
        raise LabError(f"The spec of {rid} changed after approval. Nothing was started.")
    validate_spec(spec)
    if spec["scope"] != r["scope"]:
        raise LabError("Spec scope differs from the approved scope.")
    return r, spec


def start_entry(db, rid, entry):
    r, spec = load_approved_spec(db, rid)
    if entry < 0 or entry >= len(spec["entries"]):
        raise LabError(f"Entry {entry} does not exist (spec has {len(spec['entries'])}).")
    if spec["scope"] == "real":
        ctx = kube_context()
        want = spec["real"]["kube_context"]
        if ctx != want:
            raise LabError(f"kubectl context is {ctx!r}, the approval is for {want!r}. Nothing was started.")
    e = spec["entries"][entry]
    root = lab_root()
    cwd = os.path.normpath(os.path.join(root, spec["cwd"]))
    if not os.path.isdir(cwd):
        raise LabError(f"Working directory {cwd} does not exist.")
    max_attempts = spec.get("max_attempts", 1)
    with db.tx() as c:
        rows = c.execute("SELECT status FROM runs WHERE request_id=? AND entry=?", (rid, entry)).fetchall()
        if any(x["status"] in ("starting", "running") for x in rows):
            raise LabError(f"Entry {entry} of {rid} is already running.")
        if len(rows) >= max_attempts:
            raise LabError(f"Entry {entry} of {rid} used its {max_attempts} attempt(s). A new approval is needed.")
        attempt = len(rows) + 1
        run_id = f"{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}-{rid}-e{entry}-a{attempt}"
        run_dir = os.path.join(lab_dir(), "runs", run_id)
        os.makedirs(run_dir, exist_ok=False)
        sha = git_sha(os.path.join(root, "code")) or git_sha(cwd)
        c.execute("INSERT INTO runs(run_id, request_id, spec_hash, entry, attempt, name, scope, cmd, cwd, run_dir,"
                  " code_sha, status, created) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (run_id, rid, r["spec_hash"], entry, attempt, e.get("name") or f"entry{entry}", spec["scope"],
                   json.dumps(e["cmd"]), cwd, run_dir, sha, "starting", now()))
        c.execute("INSERT INTO audit(ts, actor, action, target, detail) VALUES (?,?,?,?,?)",
                  (now(), "launcher", "start", run_id, f"{rid} entry {entry} attempt {attempt}"))
    with open(os.path.join(run_dir, "spec_entry.json"), "w", encoding="utf-8") as f:
        json.dump({"request_id": rid, "spec_hash": r["spec_hash"], "spec_name": spec["name"], "scope": spec["scope"],
                   "entry": entry, "attempt": attempt, "entry_spec": e, "limits": spec["limits"],
                   "real": spec.get("real"), "cpu_affinity": spec.get("cpu_affinity"),
                   "env_threads": spec.get("env_threads"), "code_sha": sha, "cwd": cwd}, f, indent=2, ensure_ascii=False)
    subprocess.Popen([sys.executable, os.path.abspath(__file__), "_supervise", run_id],
                     cwd=root, start_new_session=True, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=open(os.path.join(run_dir, "supervisor.log"), "a"))
    return run_id


def supervise(run_id):
    db = LabDB()
    run = db.run(run_id)
    with open(os.path.join(run["run_dir"], "spec_entry.json"), encoding="utf-8") as f:
        meta = json.load(f)
    limit_s = float(meta["limits"]["wall_clock_hours"]) * 3600
    env = dict(os.environ, QRL_RUN_ID=run_id, QRL_RUN_DIR=run["run_dir"], QRL_LAB_DIR=lab_root(),
               QRL_RUN_SEED=str(meta["entry_spec"].get("seed", "")))
    log = open(os.path.join(run["run_dir"], "output.log"), "ab")
    cores, upd = pin_plan(meta.get("scope"), meta.get("cpu_affinity"), meta.get("env_threads"))
    env.update(upd)
    if cores:
        log.write(f"[launcher] cpu affinity {cores[0]}-{cores[-1]} ({len(cores)} cores), threads={upd.get('OMP_NUM_THREADS')}\n".encode())
    t0 = time.time()
    try:
        proc = subprocess.Popen(json.loads(run["cmd"]), cwd=run["cwd"], env=env, stdout=log,
                                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True,
                                preexec_fn=(lambda: os.sched_setaffinity(0, cores)) if cores else None)
    except OSError as e:
        with db.tx() as c:
            c.execute("UPDATE runs SET status='failed', ended=?, exit_code=-1 WHERE run_id=?", (now(), run_id))
        log.write(f"\n[launcher] could not start: {e}\n".encode())
        return
    with db.tx() as c:
        c.execute("UPDATE runs SET status='running', pid=?, started=? WHERE run_id=?", (proc.pid, now(), run_id))
    reason = None
    while proc.poll() is None:
        time.sleep(POLL)
        if db.run(run_id)["stop_requested"]:
            reason = "stopped by the researcher"
        elif time.time() - t0 > limit_s:
            reason = f"wall-clock limit {meta['limits']['wall_clock_hours']} h reached"
        if reason:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
                for _ in range(30):
                    if proc.poll() is not None:
                        break
                    time.sleep(1)
                if proc.poll() is None:
                    os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
            break
    code = proc.returncode
    status = "stopped" if reason else ("done" if code == 0 else "failed")
    with db.tx() as c:
        c.execute("UPDATE runs SET status=?, exit_code=?, ended=? WHERE run_id=?", (status, code, now(), run_id))
        c.execute("INSERT INTO audit(ts, actor, action, target, detail) VALUES (?,?,?,?,?)",
                  (now(), "launcher", status, run_id, reason or f"exit {code}"))
    with open(os.path.join(run["run_dir"], "launcher.json"), "w", encoding="utf-8") as f:
        json.dump({"status": status, "exit_code": code, "reason": reason, "seconds": round(time.time() - t0, 1)}, f)
    log.close()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start")
    s.add_argument("--request", required=True)
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--entry", type=int)
    g.add_argument("--all", action="store_true")
    sub.add_parser("list")
    s = sub.add_parser("_supervise")
    s.add_argument("run_id")
    a = p.parse_args()

    if a.cmd == "_supervise":
        supervise(a.run_id)
        return
    db = LabDB()
    try:
        if a.cmd == "list":
            for r in db.runs():
                print(f"{r['run_id']}  {r['status']:8s} exit={r['exit_code']}  {r['scope']}  {r['name']}")
        elif a.all:
            _, spec = load_approved_spec(db, a.request)
            max_parallel = int(spec.get("max_parallel", 1))
            runs = [r for r in db.runs(limit=10000) if r["request_id"] == a.request]
            running = sum(1 for r in runs if r["status"] in ("starting", "running"))
            started_entries = {r["entry"] for r in runs}
            todo = [i for i in range(len(spec["entries"])) if i not in started_entries]
            if not todo:
                print("every entry has been started at least once")
            for i in todo:
                if running >= max_parallel:
                    print(f"{running} running = max_parallel {max_parallel}; call --all again when one finishes")
                    break
                print(start_entry(db, a.request, i))
                running += 1
        else:
            print(start_entry(db, a.request, a.entry))
    except LabError as e:
        sys.exit(f"refused: {e}")


if __name__ == "__main__":
    main()
