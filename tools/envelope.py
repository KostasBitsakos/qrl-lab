#!/usr/bin/env python3
"""Cycle envelope (F1/F2, J427): ONE researcher approval covers a CPU-h budget, an end date and a set of worktrees.
Inside it, launches / reruns / retries need no approval card. Nothing here posts to the researcher thread (F3).

  envelope.py status  --envelope cycle3
  envelope.py run     --envelope cycle3 --spec child.json    smoke -> all entries -> auto-retry (<=2x); no LLM; detach it
  envelope.py check   --envelope cycle3 --spec child.json    validate only

The approval is a researcher message (envelope.approved_by) that must exist in the lab DB with author 'researcher'.
Child spec = normal run spec (validate_spec) + optional entry keys: cpus (default 1), est_cpu_h, smoke (bool).
Refuses: unknown/expired envelope, scope != sim, cwd outside envelope.worktrees, budget exceeded, entry with cmd not
starting with an allowed interpreter. Runs are recorded as request_id 'ENV-<name>'.
"""
import argparse, datetime as dt, json, math, os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import launch_run as L
from labdb import LabDB, LabError, canonical_hash, lab_dir, lab_root, now, validate_spec

POLL = 20


def load_envelope(db, name):
    p = os.path.join(lab_root(), "docs", "envelopes", f"{name}.json")
    try:
        env = json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise LabError(f"Unknown envelope {name}: {e}")
    for k in ("approved_by", "cpu_hours_budget", "expires", "worktrees", "max_parallel", "max_retries", "interpreters"):
        if k not in env:
            raise LabError(f"Envelope {name} missing '{k}'.")
    m = db.message(env["approved_by"])
    if not m or m["author"] != "researcher":
        raise LabError(f"Envelope {name}: approval message {env['approved_by']} is not a researcher message.")
    if time.time() >= L.parse_ts_epoch(env["expires"]):
        raise LabError(f"Envelope {name} expired at {env['expires']}.")
    return env


def rid_of(name):
    return f"ENV-{name}"


def used_cpu_h(db, name):
    tot = 0.0
    for r in db.runs(limit=100000):
        if r["request_id"] != rid_of(name):
            continue
        cpus, lim = 1, 0.0
        try:
            with open(os.path.join(r["run_dir"], "spec_entry.json"), encoding="utf-8") as f:
                m = json.load(f)
            cpus, lim = int(m["entry_spec"].get("cpus", 1)), float(m["limits"]["wall_clock_hours"])
        except (OSError, ValueError, KeyError):
            if r["status"] in ("starting", "running"):
                raise LabError(f"Unreadable accounting for live run {r['run_id']}; refusing (fail closed).")
        if r["status"] in ("starting", "running"):
            tot += cpus * lim          # reserved at the worst case until it ends
        elif r["started"]:
            end = L.parse_ts_epoch(r["ended"]) if r["ended"] else time.time()
            tot += max(0.0, end - L.parse_ts_epoch(r["started"])) / 3600 * cpus
    return tot


def check_spec(env, spec):
    validate_spec(spec)
    if spec["scope"] != "sim":
        raise LabError("Envelope covers scope 'sim' only.")
    wts = [os.path.realpath(os.path.join(lab_root(), x)) for x in env["worktrees"]]
    cwd = os.path.realpath(os.path.join(lab_root(), spec["cwd"]))
    if not any(cwd == w or cwd.startswith(w + "/") for w in wts):
        raise LabError(f"cwd {cwd} is outside the envelope worktrees {env['worktrees']}.")
    if not os.path.isdir(cwd):
        raise LabError(f"cwd {cwd} does not exist.")
    pins = {os.path.realpath(x) for x in env["interpreters"] if os.path.isabs(x)}
    for i, e in enumerate(spec["entries"]):
        cmd = e["cmd"]
        # J427/Codex: the exact pinned interpreter (not a basename), running a script inside the worktree; no -c/-m
        if os.path.realpath(cmd[0]) not in pins:
            raise LabError(f"Entry {i}: interpreter {cmd[0]} is not one of the pinned {sorted(pins)}.")
        if len(cmd) < 2 or cmd[1].startswith("-"):
            raise LabError(f"Entry {i}: cmd[1] must be a script path (no -c/-m options).")
        sc = os.path.realpath(os.path.join(cwd, cmd[1]))
        if not os.path.isfile(sc) or not any(sc.startswith(w + "/") for w in wts):
            raise LabError(f"Entry {i}: script {cmd[1]} must be a file inside the envelope worktrees.")
        c = e.get("cpus", 1)
        if not isinstance(c, int) or isinstance(c, bool) or not 1 <= c <= 8:
            raise LabError(f"Entry {i}: cpus must be an int 1..8.")
        est = e.get("est_cpu_h")
        if est is not None and (not isinstance(est, (int, float)) or not 0 < est < 1e4):
            raise LabError(f"Entry {i}: bad est_cpu_h.")
    if not any(e.get("smoke") for e in spec["entries"]):
        raise LabError("Spec needs one entry with smoke=true (F2: smoke run before every batch).")
    if spec.get("cpu_affinity") and any(c not in set(L.parse_cpus(env["cpu_affinity"])) for c in L.parse_cpus(spec["cpu_affinity"])):
        raise LabError("cpu_affinity outside the envelope pool.")
    w = spec["limits"]["wall_clock_hours"]
    if isinstance(w, bool) or not math.isfinite(w) or w <= 0:
        raise LabError("wall_clock_hours must be a finite number > 0.")
    if w > env.get("max_wall_hours", 48):
        raise LabError("wall_clock_hours exceeds envelope max_wall_hours.")
    return cwd


def entry_cost(spec, e):
    """Worst case = cpus x wall-clock limit (the supervisor kills at the limit); est_cpu_h may only lower it for planning,
    never for admission."""
    return float(e.get("cpus", 1)) * float(spec["limits"]["wall_clock_hours"])


def need_cpu_h(spec):
    return sum(entry_cost(spec, e) for e in spec["entries"])


def start_entry(db, name, spec, entry, env):
    cwd = check_spec(env, spec)
    rid, sh = rid_of(name), canonical_hash(spec)
    e = spec["entries"][entry]
    with db.tx() as c:
        rows = c.execute("SELECT status, name FROM runs WHERE request_id=?", (rid,)).fetchall()
        tag = f"{spec['name']}/{e.get('name') or entry}"
        mine = [x for x in rows if x["name"] == tag]
        if any(x["status"] in ("starting", "running") for x in mine):
            raise LabError(f"{tag} already running.")
        if len(mine) > env["max_retries"]:
            raise LabError(f"{tag} used 1+{env['max_retries']} attempts.")
        if sum(1 for x in rows if x["status"] in ("starting", "running")) >= env["max_parallel"]:
            raise LabError("max_parallel reached.")
        if used_cpu_h(db, name) + entry_cost(spec, e) \
                > float(env["cpu_hours_budget"]):
            raise LabError("Envelope CPU-h budget would be exceeded.")
        busy = set()
        for x in c.execute("SELECT run_dir FROM runs WHERE status IN ('starting','running')").fetchall():
            try:
                m = json.load(open(os.path.join(x["run_dir"], "spec_entry.json"), encoding="utf-8"))
                busy |= set((m.get("sandbox") or {}).get("cores") or []) | (
                    set(L.parse_cpus(m["cpu_affinity"])) if m.get("cpu_affinity") and
                    str(m.get("request_id", "")).startswith("ENV-") else set())
            except (OSError, ValueError, KeyError):
                raise LabError("Unreadable core accounting of a live run; refusing (fail closed).")
        pool = [k for k in sorted(set(L.parse_cpus(spec.get("cpu_affinity") or env["cpu_affinity"])) &
                                  set(os.sched_getaffinity(0))) if k not in busy]
        ncpu = int(e.get("cpus", 1))
        if len(pool) < ncpu:
            raise LabError("no free cores (max_parallel).")
        cores = pool[:ncpu]                       # Codex: the entry gets exactly the cores it is charged for
        left_h = (L.parse_ts_epoch(env["expires"]) - time.time()) / 3600
        if left_h <= 0:
            raise LabError("Envelope expired.")
        limits = dict(spec["limits"], wall_clock_hours=min(float(spec["limits"]["wall_clock_hours"]), left_h))
        idx, attempt = len(rows), len(mine) + 1
        run_id = f"{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}-{rid}-n{idx}-a{attempt}"
        run_dir = os.path.join(lab_dir(), "runs", run_id)
        os.makedirs(run_dir, exist_ok=False)
        sha = L.git_sha(cwd)
        json.dump({"request_id": rid, "spec_hash": sh, "spec_name": spec["name"], "scope": "sim", "entry": idx,
                   "attempt": attempt, "entry_spec": e, "limits": limits, "real": None,
                   "cpu_affinity": ",".join(map(str, cores)), "envelope_expires": env["expires"], "env_threads": spec.get("env_threads"),
                   "code_sha": sha, "cwd": cwd}, open(os.path.join(run_dir, "spec_entry.json"), "w", encoding="utf-8"),
                  indent=2, ensure_ascii=False)   # written BEFORE the row: a reader never sees a row without accounting data
        c.execute("INSERT INTO runs(run_id, request_id, spec_hash, entry, attempt, name, scope, cmd, cwd, run_dir,"
                  " code_sha, status, created) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (run_id, rid, sh, idx, attempt, tag, "sim", json.dumps(e["cmd"]), cwd, run_dir, sha, "starting", now()))
        c.execute("INSERT INTO audit(ts, actor, action, target, detail) VALUES (?,?,?,?,?)",
                  (now(), "envelope", "start", run_id, f"{rid} {tag} attempt {attempt}"))
    subprocess.Popen([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "launch_run.py"),
                      "_supervise", run_id], cwd=lab_root(), start_new_session=True, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=open(os.path.join(run_dir, "supervisor.log"), "a"))
    return run_id


def tlog(msg):
    with open(os.path.join(lab_root(), ".lab", "technical.log"), "a", encoding="utf-8") as f:
        f.write(f"[{now()}] envelope: {msg}\n")


def status_of(db, rid_run):
    r = db.run(rid_run)
    return r["status"] if r else "missing"


def run_spec(db, name, spec, poll=POLL):
    env = load_envelope(db, name)
    check_spec(env, spec)
    n = len(spec["entries"])
    if need_cpu_h(spec) + used_cpu_h(db, name) > float(env["cpu_hours_budget"]):
        raise LabError("Spec worst case exceeds remaining envelope budget.")
    smoke = next(i for i, e in enumerate(spec["entries"]) if e.get("smoke"))
    result = {"spec": spec["name"], "entries": {}, "smoke": None}
    if True:   # F2: 1-unit smoke first; a failing smoke is retried like any unit, then the batch is abandoned
        for _ in range(1 + env["max_retries"]):
            env = load_envelope(db, name)
            rid_ = start_entry(db, name, spec, smoke, env)
            while status_of(db, rid_) in ("starting", "running"):
                time.sleep(poll)
            result["smoke"] = status_of(db, rid_)
            if result["smoke"] in ("done", "stopped"):
                break
        if result["smoke"] != "done":
            tlog(f"{spec['name']}: smoke FAILED, batch not started")
            return result
    todo = [i for i in range(n) if i != smoke]
    live, tries = {}, {i: 0 for i in todo}
    while todo or live:
        for i, rid_ in list(live.items()):
            s = status_of(db, rid_)
            if s in ("starting", "running"):
                continue
            del live[i]
            result["entries"][i] = s
            if s not in ("done", "stopped") and tries[i] < 1 + env["max_retries"]:
                todo.append(i)
                tlog(f"{spec['name']} entry {i} {s}; retry {tries[i]}")
        env = load_envelope(db, name)
        for i in list(todo):
            if len(live) >= env["max_parallel"]:
                break
            try:
                live[i] = start_entry(db, name, spec, i, env)
            except LabError as e:
                if "max_parallel" in str(e) or "already running" in str(e):
                    break
                tlog(f"{spec['name']} entry {i} cannot start: {e}")
                result["entries"][i] = f"refused: {e}"
                todo.remove(i)
                continue
            tries[i] += 1
            todo.remove(i)
        time.sleep(poll)
    ok = sum(1 for v in result["entries"].values() if v == "done")
    result["done"], result["total"] = ok + (1 if result["smoke"] == "done" else 0), n
    od = os.path.join(lab_root(), ".lab", "envelope", name)
    os.makedirs(od, exist_ok=True)
    json.dump(result, open(os.path.join(od, f"{spec['name']}.result.json"), "w"), indent=1)
    tlog(f"{spec['name']}: {result['done']}/{n} done")
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("cmd", choices=("status", "run", "check"))
    p.add_argument("--envelope", required=True)
    p.add_argument("--spec")
    p.add_argument("--poll", type=float, default=POLL)
    a = p.parse_args()
    db = LabDB()
    try:
        env = load_envelope(db, a.envelope)
        if a.cmd == "status":
            u = used_cpu_h(db, a.envelope)
            print(f"{a.envelope}: {u:.1f}/{env['cpu_hours_budget']} CPU-h used, expires {env['expires']}")
            return
        spec = json.load(open(a.spec, encoding="utf-8"))
        if a.cmd == "check":
            check_spec(env, spec)
            print(f"OK need {need_cpu_h(spec):.1f} CPU-h worst case; used {used_cpu_h(db, a.envelope):.1f}/{env['cpu_hours_budget']}")
            return
        print(json.dumps(run_spec(db, a.envelope, spec, a.poll)))
    except LabError as e:
        sys.exit(f"refused: {e}")


if __name__ == "__main__":
    main()
