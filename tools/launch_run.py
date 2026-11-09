#!/usr/bin/env python3
"""Approval-enforced experiment launcher for QRL-Lab. Run from ~/qrl-lab.

  launch_run.py start --request R-... --entry 0     start one entry of an approved run spec
  launch_run.py start --request R-... --all         start the next entries not yet run, up to spec.max_parallel
                                                    (default 1); call again when a run finishes
  launch_run.py list                                runs and their status
  launch_run.py sandbox-start --request R-... --spec child.json
                                                    start every entry of a child spec under a standing sandbox approval
                                                    (kind 'sandbox'); the child is verified, not separately approved
  launch_run.py sandbox-status --request R-...      CPU-hours used/left, running runs, expiry
  launch_run.py sandbox-activate-amendment --request R-... --amendment R-...
                                                    activate a separately frozen, approved limits amendment

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
import sqlite3
from pathlib import Path
from contextlib import closing
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from labdb import LabDB, LabError, canonical_hash, db_path, lab_dir, lab_root, now, validate_spec  # noqa: E402

POLL = 5
START_LOCK_WAIT_S = 60  # retry in the supervision loop; fail closed after this deadline
END_LOCK_WAIT_S = 600   # supervisor DB writes retry "database is locked" this long (s59 incident, J169)
# Core pinning for scope 'sim' runs (R-20261017-017). One place for the default: env QRL_SIM_CPUS (e.g. "8-39" or
# "8-15,20") overrides the constant; the spec key "cpu_affinity" (same syntax, or a list of ints) overrides both.
# Cores 0-7 stay free for the system (dashboard, kube-apiserver, kubelet, ...). Scope 'real' is never pinned.
DEFAULT_SIM_CPUS = "8-39"
THREAD_ENV = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS")


G_ENV_THREADS = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS")


def parse_ts_epoch(s):
    d = dt.datetime.fromisoformat(s)
    return (d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)).timestamp()


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
    if spec.get("kind") in ("sandbox", "sandbox-amendment"):
        raise LabError("Sandbox approvals require sandbox-start with a verified child spec.")
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


def load_sandbox(db, rid):
    r, spec = load_approved_spec(db, rid)
    if spec.get("kind") != "sandbox" or not isinstance(spec.get("sandbox"), dict):
        raise LabError(f"{rid} is not a sandbox approval.")
    activation = db.conn.execute("SELECT detail FROM audit WHERE action='sandbox-amendment' AND target=?",
                                 (rid,)).fetchall()
    if len(activation) > 1:
        raise LabError("Multiple sandbox amendment activations; refused.")
    if activation:
        import sandbox_guard as G
        try:
            binding = json.loads(activation[0]["detail"])
            if (not isinstance(binding, dict) or
                    set(binding) != {"request_id", "spec_hash", "parent_spec_hash"} or
                    binding["parent_spec_hash"] != r["spec_hash"] or
                    not all(isinstance(v, str) and v for v in binding.values())):
                raise ValueError("Invalid activation binding")
        except (TypeError, ValueError) as e:
            raise LabError("Invalid sandbox amendment audit binding; refused.") from e
        ar, amendment = load_approved_spec(db, binding["request_id"])
        if ar["spec_hash"] != binding["spec_hash"]:
            raise LabError("Activated amendment hash mismatch.")
        spec = G.apply_amendment(spec, rid, r["spec_hash"], amendment)
        r = dict(r, amendment_request_id=binding["request_id"], amendment_spec_hash=binding["spec_hash"])
    return r, spec


def activate_sandbox_amendment(db, rid, amendment_id):
    """Append-only, one-time activation; serializes with reservations, never changes approvals."""
    import sandbox_guard as G
    with db.tx() as c:
        if c.execute("SELECT 1 FROM audit WHERE action='sandbox-amendment' AND target=?", (rid,)).fetchone():
            raise LabError("Sandbox already has an activated amendment; refused.")
        r, parent = load_sandbox(db, rid)
        ar, amendment = load_approved_spec(db, amendment_id)
        effective = G.apply_amendment(parent, rid, r["spec_hash"], amendment)
        sb = effective["sandbox"]
        if G.active_runs(db, rid):
            raise LabError("Sandbox has starting/running runs; activation refused.")
        if time.time() >= parse_ts_epoch(sb["expires"]):
            raise LabError("Sandbox expired; activation refused.")
        used = G.used_cpu_hours(db, rid, strict=True)
        if used > sb["cpu_hours_budget"]:
            raise LabError("Consumed cost exceeds amended budget; activation refused.")
        for wt in sb["worktrees"]:
            G.verify_sandbox_protected(G.select_worktree(sb, wt), lab_root())
        c.execute("INSERT INTO audit(ts,actor,action,target,detail) VALUES (?,?,?,?,?)",
                  (now(), "launcher", "sandbox-amendment", rid,
                   json.dumps({"request_id": amendment_id, "spec_hash": ar["spec_hash"],
                               "parent_spec_hash": r["spec_hash"]})))


def start_sandbox(db, rid, child):
    """Verify a child spec against the sandbox approval and start all its entries (all or nothing)."""
    import sandbox_guard as G
    run_ids = []
    with db.tx() as c:
        r, parent = load_sandbox(db, rid)
        sb = parent["sandbox"]
        cwd, plan = G.check_child(child, parent)
        selected = G.select_worktree(sb, child)
        root = lab_root()
        G.verify_sandbox_protected(selected, root)
        avail = os.sched_getaffinity(0) if hasattr(os, "sched_getaffinity") else set()
        pool = sorted(set(parse_cpus(child.get("cpu_affinity") or sb["cpu_affinity"])) & set(avail))
        seeds_env = G.seed_env(sb)
        env_threads = G.check_env(child.get("env_threads"), "child")
        need = sum(p["reserve_cpu_h"] for p in plan)
        sha = git_sha(cwd)
        child_hash = canonical_hash(child)
        runs = [x for x in c.execute("SELECT * FROM runs WHERE request_id=?", (rid,)).fetchall()]
        active = sum(1 for x in runs if x["status"] in ("starting", "running"))
        if active + len(plan) > int(sb["max_parallel"]):
            raise LabError(f"{active} running + {len(plan)} new > max_parallel {sb['max_parallel']}. Nothing was started.")
        busy = sandbox_busy_cores(c)
        cores = G.assign_cores(pool, busy, [p["cpus"] for p in plan])
        used = G.used_cpu_hours(db, rid, strict="worktrees" in sb)
        if used + need > float(sb["cpu_hours_budget"]):
            raise LabError(f"Budget: {used:.2f} used + {need:.2f} worst case > {sb['cpu_hours_budget']} CPU-h. "
                           "Nothing was started.")
        base = len(runs)
        for p, pcores in zip(plan, cores):
            e = child["entries"][p["entry"]]
            idx = base + p["entry"]
            run_id = f"{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}-{rid}-s{idx}-a1"
            run_dir = os.path.join(lab_dir(), "runs", run_id)
            os.makedirs(run_dir, exist_ok=False)
            c.execute("INSERT INTO runs(run_id, request_id, spec_hash, entry, attempt, name, scope, cmd, cwd, run_dir,"
                      " code_sha, status, created) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (run_id, rid, child_hash, idx, 1, f"{child['name']}/{e.get('name') or p['entry']}", "sim",
                       json.dumps(e["cmd"]), cwd, run_dir, sha, "starting", now()))
            c.execute("INSERT INTO audit(ts, actor, action, target, detail) VALUES (?,?,?,?,?)",
                      (now(), "launcher", "sandbox-start", run_id, f"{rid} child {child['name']} entry {p['entry']}"))
            with open(os.path.join(run_dir, "spec_entry.json"), "w", encoding="utf-8") as f:
                json.dump({"request_id": rid, "spec_hash": child_hash, "spec_name": child["name"], "scope": "sim",
                           "entry": idx, "attempt": 1, "entry_spec": e, "limits": {"wall_clock_hours": p["wall_hours"]},
                           "real": None, "cpu_affinity": child.get("cpu_affinity") or sb["cpu_affinity"], "env_threads": dict(env_threads, **G.check_env(e.get("env_threads"), "entry")),
                           "code_sha": sha, "cwd": cwd,
                           "sandbox": {"cpus": p["cpus"], "reserve_cpu_h": p["reserve_cpu_h"], "seeds": p["seeds"],
                                       "repo": selected["repo"], "branch": selected["branch"], "cores": pcores, "seed_env": seeds_env,
                                       "expires": sb["expires"], "request_id": rid,
                                       "parent_spec_hash": r["spec_hash"],
                                       "amendment_request_id": r.get("amendment_request_id"),
                                       "amendment_spec_hash": r.get("amendment_spec_hash"),
                                       "effective_sandbox_hash": canonical_hash(sb)}}, f, indent=2, ensure_ascii=False)
            G.log_ledger(rid, {"ts": now(), "run_id": run_id, "name": child["name"], "seeds": p["seeds"],
                               "reserve_cpu_h": p["reserve_cpu_h"], "cpus": p["cpus"], "cores": pcores,
                               "event": "start"}, root)
            run_ids.append(run_id)
    for run_id in run_ids:
        d = db.run(run_id)["run_dir"]
        subprocess.Popen([sys.executable, os.path.abspath(__file__), "_supervise", run_id],
                         cwd=root, start_new_session=True, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=open(os.path.join(d, "supervisor.log"), "a"))
    return run_ids


def sandbox_busy_cores(c):
    """Cores assigned to sandbox runs that are starting/running (any request), read from their spec_entry.json."""
    busy = []
    for x in c.execute("SELECT run_dir FROM runs WHERE status IN ('starting','running')").fetchall():
        try:
            with open(os.path.join(x["run_dir"], "spec_entry.json"), encoding="utf-8") as f:
                busy += (json.load(f).get("sandbox") or {}).get("cores") or []
        except (OSError, ValueError):
            pass
    return busy


def sandbox_status(db, rid):
    import sandbox_guard as G
    _, parent = load_sandbox(db, rid)
    sb = parent["sandbox"]
    used = G.used_cpu_hours(db, rid, strict="worktrees" in sb)
    budget = float(sb["cpu_hours_budget"])
    exp = G.parse_ts(sb["expires"])
    left_h = (exp - dt.datetime.now(dt.timezone.utc)).total_seconds() / 3600
    return {"request": rid, "branch": sb.get("branch") or ",".join(p["branch"] for p in sb["worktrees"]), "cpu_hours_used": round(used, 3),
            "cpu_hours_left": round(budget - used, 3), "budget": budget,
            "running": G.active_runs(db, rid), "max_parallel": sb["max_parallel"],
            "expires": sb["expires"], "expired": left_h <= 0, "hours_to_expiry": round(left_h, 2)}


def finish_run(db, run_id, run_dir, status, code, reason, seconds, cpu_s, ledger_rid=None, cpus=None, ended=None,
               note=None):
    """End-of-run record: runs row + audit, launcher.json, sandbox ledger. `ended`/`note` only for reconciliation
    of a run whose supervisor died after its child exited (J169)."""
    ended = ended or now()
    with db.tx(lock_wait_s=END_LOCK_WAIT_S) as c:   # the child is gone: never lose its end record to a busy DB
        c.execute("UPDATE runs SET status=?, exit_code=?, ended=? WHERE run_id=?", (status, code, ended, run_id))
        c.execute("INSERT INTO audit(ts, actor, action, target, detail) VALUES (?,?,?,?,?)",
                  (now(), "launcher", status, run_id, (reason or f"exit {code}") + (f"; {note}" if note else "")))
    info = {"status": status, "exit_code": code, "reason": reason, "seconds": seconds, "cpu_seconds": cpu_s}
    if note:
        info["reconciled"] = note
    with open(os.path.join(run_dir, "launcher.json"), "w", encoding="utf-8") as f:
        json.dump(info, f)
    if ledger_rid:
        import sandbox_guard as G
        rec = {"ts": now(), "run_id": run_id, "event": status, "wall_s": seconds, "cpus": cpus, "cpu_seconds": cpu_s}
        if note:
            rec["reconciled"] = note
        G.log_ledger(ledger_rid, rec, lab_root())


def supervise(run_id):
    db = LabDB()
    run = db.run(run_id)
    with open(os.path.join(run["run_dir"], "spec_entry.json"), encoding="utf-8") as f:
        meta = json.load(f)
    limit_s = float(meta["limits"]["wall_clock_hours"]) * 3600
    sbm = meta.get("sandbox")
    base_env = os.environ
    if sbm:   # sandbox: no inherited QRL_*/PYTHON* variables; the launcher sets the seed guard and thread counts
        base_env = {k: v for k, v in os.environ.items() if not k.startswith("QRL_") and
                    k not in ("PYTHONPATH", "PYTHONSTARTUP", "PYTHONHOME", "LD_PRELOAD", "LD_LIBRARY_PATH")}
    env = dict(base_env, QRL_RUN_ID=run_id, QRL_RUN_DIR=run["run_dir"], QRL_LAB_DIR=lab_root(),
               QRL_RUN_SEED=str(meta["entry_spec"].get("seed", "")))
    if not env["QRL_RUN_SEED"]:   # J419: an entry without a seed must leave the variable unset ('' crashes int(os.environ...))
        env.pop("QRL_RUN_SEED")
    log = open(os.path.join(run["run_dir"], "output.log"), "ab")
    if sbm:
        cores = [int(c) for c in sbm["cores"]]
        upd = {k: "1" for k in G_ENV_THREADS}
        upd.update({k: str(v) for k, v in (meta.get("env_threads") or {}).items()})
        upd["QRL_SANDBOX_SEEDS"] = sbm["seed_env"]
        expires_ts = parse_ts_epoch(sbm["expires"])
    else:
        cores, upd = pin_plan(meta.get("scope"), meta.get("cpu_affinity"), meta.get("env_threads"))
        expires_ts = None
    env.update(upd)
    if cores:
        log.write(f"[launcher] cpu affinity {cores[0]}-{cores[-1]} ({len(cores)} cores), threads={upd.get('OMP_NUM_THREADS')}\n".encode())
    t0 = time.time()
    try:
        if sbm and sbm.get("repo") in ("code-poisson", "code-poisson-astra"):
            import sandbox_guard as G
            pr, parent = load_sandbox(db, meta["request_id"])
            if sbm.get("parent_spec_hash") and (pr["spec_hash"] != sbm["parent_spec_hash"] or
                    canonical_hash(parent["sandbox"]) != sbm["effective_sandbox_hash"]):
                raise LabError("Sandbox approval changed after reservation.")
            selected = G.select_worktree(parent["sandbox"], {"repo": sbm["repo"]})
            G.verify_sandbox_protected(selected)
            if time.time() >= parse_ts_epoch(parent["sandbox"]["expires"]):
                raise LabError("Sandbox expired before process spawn.")
        proc = subprocess.Popen(json.loads(run["cmd"]), cwd=run["cwd"], env=env, stdout=log,
                                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True,
                                preexec_fn=(lambda: os.sched_setaffinity(0, cores)) if cores else None)
    except (OSError, subprocess.SubprocessError, LabError) as e:
        with db.tx() as c:
            c.execute("UPDATE runs SET status='failed', ended=?, exit_code=-1 WHERE run_id=?", (now(), run_id))
        log.write(f"\n[launcher] could not start: {e}\n".encode())
        return
    reason = None
    started = now()
    recorded = False
    start_deadline = time.monotonic() + START_LOCK_WAIT_S
    last_stop_read = time.monotonic()
    # A live child must never wait behind SQLite's default 10-second busy handler.
    # Retry only the state write, between safety checks, for a bounded interval.
    old_timeout = db.conn.execute("PRAGMA busy_timeout").fetchone()[0]
    db.conn.execute("PRAGMA busy_timeout=0")
    try:
        while True:
            if not recorded:
                try:
                    with db.tx() as c:
                        c.execute("UPDATE runs SET status='running', pid=?, started=? WHERE run_id=?",
                                  (proc.pid, started, run_id))
                    recorded = True
                except sqlite3.Error as e:
                    if not ("locked" in str(e) or "busy" in str(e)):
                        reason = f"startup database write failed: {e}"
                    elif time.monotonic() >= start_deadline:
                        reason = "startup database write deadline exceeded"
            if proc.poll() is not None:
                break
            try:
                if db.run(run_id)["stop_requested"]:
                    reason = "stopped by the researcher"
                last_stop_read = time.monotonic()
            except sqlite3.Error as e:
                if not ("locked" in str(e) or "busy" in str(e)) or (
                        time.monotonic() - last_stop_read >= START_LOCK_WAIT_S):
                    reason = "cannot read stop request; stopping conservatively"
            if expires_ts is not None and time.time() >= expires_ts:
                reason = f"sandbox expired at {sbm['expires']}"
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
            time.sleep(POLL)
    except BaseException:
        # Unexpected supervision failures must not leave the child running unattended.
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
        raise
    finally:
        db.conn.execute(f"PRAGMA busy_timeout={old_timeout}")
    ended = now()
    seconds = round(time.time() - t0, 1)
    if not recorded:
        # The child is gone, so blocking no longer delays safety checks. Preserve identity/time.
        with db.tx(lock_wait_s=END_LOCK_WAIT_S) as c:
            c.execute("UPDATE runs SET pid=?, started=? WHERE run_id=?", (proc.pid, started, run_id))
    code = proc.returncode
    cpu_s = None
    if sbm:   # CPU time of the whole reaped process tree (this supervisor has exactly one child)
        import resource
        ru = resource.getrusage(resource.RUSAGE_CHILDREN)
        cpu_s = round(ru.ru_utime + ru.ru_stime, 2)
    status = "stopped" if reason else ("done" if code == 0 else "failed")
    finish_run(db, run_id, run["run_dir"], status, code, reason, seconds, cpu_s,
               meta["request_id"] if sbm else None, sbm["cpus"] if sbm else None, ended=ended)
    log.close()


def show_run(run_prefix, path=None):
    """Read-only status; no schema creation, migrations, or write transactions."""
    with closing(sqlite3.connect(Path(path or db_path()).resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        cols = "run_id,status,pid,exit_code,started,ended"
        rows = conn.execute(f"SELECT {cols} FROM runs WHERE run_id=?", (run_prefix,)).fetchall()
        if not rows:
            rows = conn.execute(f"SELECT {cols} FROM runs WHERE substr(run_id,1,?)=? ORDER BY run_id",
                                (len(run_prefix), run_prefix)).fetchall()
        if not rows:
            raise LabError(f"Unknown run: {run_prefix}")
        if len(rows) != 1:
            raise LabError(f"Ambiguous run prefix: {run_prefix} ({len(rows)} matches)")
        return dict(rows[0])


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start")
    s.add_argument("--request", required=True)
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--entry", type=int)
    g.add_argument("--all", action="store_true")
    sub.add_parser("list")
    s = sub.add_parser("show", help="read-only run status by exact id or unique prefix")
    s.add_argument("run_id")
    s = sub.add_parser("sandbox-start")
    s.add_argument("--request", required=True)
    s.add_argument("--spec", required=True)
    s = sub.add_parser("sandbox-activate-amendment")
    s.add_argument("--request", required=True)
    s.add_argument("--amendment", required=True)
    s = sub.add_parser("sandbox-status")
    s.add_argument("--request", required=True)
    s = sub.add_parser("_supervise")
    s.add_argument("run_id")
    a = p.parse_args()

    if a.cmd == "_supervise":
        supervise(a.run_id)
        return
    if a.cmd == "show":
        try:
            print(json.dumps(show_run(a.run_id), ensure_ascii=False))
        except (LabError, sqlite3.Error) as e:
            sys.exit(f"refused: {e}")
        return
    db = LabDB()
    try:
        if a.cmd == "list":
            for r in db.runs():
                print(f"{r['run_id']}  {r['status']:8s} exit={r['exit_code']}  {r['scope']}  {r['name']}")
        elif a.cmd == "sandbox-start":
            try:
                import sandbox_guard as G
                with open(a.spec, encoding="utf-8") as f:
                    child = G.loads_strict(f.read())
            except (OSError, ValueError) as e:
                raise LabError(f"Cannot read child spec {a.spec}: {e}")
            for rid_ in start_sandbox(db, a.request, child):
                print(rid_)
        elif a.cmd == "sandbox-activate-amendment":
            activate_sandbox_amendment(db, a.request, a.amendment)
            print(f"{a.amendment} activated; accounting remains {a.request}")
        elif a.cmd == "sandbox-status":
            st = sandbox_status(db, a.request)
            print(f"{st['request']} ({st['branch']}): {st['cpu_hours_used']} / {st['budget']} CPU-h used, "
                  f"{st['cpu_hours_left']} left; {st['running']}/{st['max_parallel']} running; "
                  f"expires {st['expires']} ({'EXPIRED' if st['expired'] else str(st['hours_to_expiry']) + ' h left'})")
        elif a.all:
            _, spec = load_approved_spec(db, a.request)
            if spec.get("kind") in ("sandbox", "sandbox-amendment"):
                raise LabError("Sandbox approvals require sandbox-start with a verified child spec.")
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
