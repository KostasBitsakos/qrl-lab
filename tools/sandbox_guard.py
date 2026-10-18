"""Checks for the standing sandbox permission (R-20261017-021). Pure functions plus a ledger; used by launch_run.py.

A sandbox approval freezes the PARENT spec (kind 'sandbox'); child specs are not approved one by one, so every
child is verified here against the parent's `sandbox` block: scope sim, no real/qpu/kubectl/IBM, cwd inside the
tuning worktree on the right branch, seeds known and inside the allowed ranges, CPU-hour budget, parallelism,
expiry. Anything not understood is refused.
"""
import datetime as dt
import json
import os
import re
import subprocess

from labdb import LabError, lab_dir, lab_root

# repo name in the sandbox block -> worktree directory (relative to the lab root)
WORKTREES = {"code": "code-tuning"}
FORBIDDEN_WORDS = ("kubectl", "qiskit_ibm", "ibm_quantum", "ibmq", "qiskit-ibm", "helm", "kube")
FORBIDDEN_KEYS = {"real", "qpu", "kube_context", "backend_name", "ibm"}
SEED_FLAG = re.compile(r"^--?(?:[\w-]*[-_])?seeds?(?:=(.*))?$")


def merge(ranges):
    out = []
    for lo, hi in sorted((int(a), int(b)) for a, b in ranges):
        if out and lo <= out[-1][1] + 1:
            out[-1][1] = max(out[-1][1], hi)
        else:
            out.append([lo, hi])
    return out


def seed_ok(lo, hi, allowed, forbidden):
    """[lo, hi] must lie inside one merged allowed range and touch no forbidden range."""
    if lo > hi:
        return False
    if any(not (hi < a or lo > b) for a, b in forbidden):
        return False
    return any(a <= lo and hi <= b for a, b in merge(allowed))


def _parse_values(tokens):
    """['1000', '1001,1002', '3-5', '7:9'] -> [(lo, hi), ...]; ValueError if anything is not a number or range."""
    out = []
    for tok in tokens:
        for part in re.split(r"[,\s]+", tok.strip()):
            if not part:
                continue
            m = re.fullmatch(r"(\d+)(?:(?:-|:|\.\.)(\d+))?", part)
            if not m:
                raise ValueError(part)
            out.append((int(m.group(1)), int(m.group(2) or m.group(1))))
    return out


def entry_seeds(entry):
    """All seed intervals an entry will use: its 'seed' field plus --seed/--seeds/--eval-seeds... args.
    Raises LabError if none can be determined or a value cannot be parsed."""
    found = []
    try:
        if "seed" in entry:
            if isinstance(entry["seed"], bool) or not isinstance(entry["seed"], int):
                raise ValueError(entry["seed"])
            found.append((entry["seed"], entry["seed"]))
        cmd = entry["cmd"]
        i = 0
        while i < len(cmd):
            m = SEED_FLAG.match(cmd[i])
            if m:
                vals = []
                if m.group(1) is not None:
                    vals = [m.group(1)]
                else:
                    j = i + 1
                    while j < len(cmd) and not cmd[j].startswith("-"):
                        vals.append(cmd[j]); j += 1
                    i = j - 1
                if not vals:
                    raise ValueError(cmd[i])
                found += _parse_values(vals)
            i += 1
    except ValueError as e:
        raise LabError(f"Cannot parse the seeds of entry {entry.get('name')!r} ({e}); refused.")
    if not found:
        raise LabError(f"Seeds of entry {entry.get('name')!r} cannot be determined "
                       "(need an integer 'seed' field and/or --seed/--seeds args); refused.")
    return found


def _walk_keys(o):
    if isinstance(o, dict):
        for k, v in o.items():
            yield str(k).lower()
            yield from _walk_keys(v)
    elif isinstance(o, list):
        for v in o:
            yield from _walk_keys(v)


def worktree_path(sb, root=None):
    root = root or lab_root()
    rel = WORKTREES.get(sb.get("repo"))
    if not rel:
        raise LabError(f"Sandbox repo {sb.get('repo')!r} has no tuning worktree.")
    return os.path.realpath(os.path.join(root, rel))


def worktree_branch(path):
    out = subprocess.run(["git", "-C", path, "symbolic-ref", "--short", "-q", "HEAD"], capture_output=True, text=True,
                         timeout=10)
    return out.stdout.strip()


def resolve_cwd(child_cwd, sb, root=None):
    """Map the child's cwd ('code' or 'code/x') onto the tuning worktree and require it to stay inside."""
    wt = worktree_path(sb, root)
    if not os.path.isdir(wt):
        raise LabError(f"Tuning worktree {wt} does not exist.")
    if worktree_branch(wt) != sb["branch"]:
        raise LabError(f"Worktree {wt} is not on branch {sb['branch']!r}.")
    parts = os.path.normpath(str(child_cwd)).split(os.sep)
    if os.path.isabs(str(child_cwd)) or parts[0] == "..":
        raise LabError(f"Child cwd {child_cwd!r} must be relative to the repo.")
    if parts[0] in (sb["repo"], WORKTREES[sb["repo"]]):
        parts = parts[1:]
    cwd = os.path.realpath(os.path.join(wt, *parts))
    if cwd != wt and not cwd.startswith(wt + os.sep):
        raise LabError(f"Child cwd {child_cwd!r} resolves outside the {sb['branch']} worktree.")
    if not os.path.isdir(cwd):
        raise LabError(f"Working directory {cwd} does not exist.")
    return cwd


def parse_ts(s):
    d = dt.datetime.fromisoformat(s)
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def check_child(child, parent, root=None, now=None):
    """Validate a child spec against the parent sandbox block. Returns (cwd, plan) with plan = list of per-entry
    dicts {entry, seeds, cpus, wall_hours, reserve_cpu_h}. Raises LabError on the first violation."""
    sb = parent.get("sandbox")
    if parent.get("kind") != "sandbox" or not isinstance(sb, dict):
        raise LabError("The request is not a sandbox approval (spec kind != 'sandbox').")
    now = now or dt.datetime.now(dt.timezone.utc)
    if now >= parse_ts(sb["expires"]):
        raise LabError(f"The sandbox expired at {sb['expires']}.")
    if not isinstance(child, dict) or child.get("scope") != "sim":
        raise LabError("Child scope must be 'sim'.")
    for k in ("name", "cwd", "entries"):
        if k not in child:
            raise LabError(f"Child spec is missing '{k}'.")
    bad = FORBIDDEN_KEYS & set(_walk_keys(child))
    if bad:
        raise LabError(f"Child spec has forbidden field(s) {sorted(bad)}.")
    if not isinstance(child["entries"], list) or not child["entries"]:
        raise LabError("Child needs a non-empty 'entries' list.")
    mp = child.get("max_parallel", 1)
    if not isinstance(mp, int) or mp < 1 or mp > int(sb["max_parallel"]):
        raise LabError(f"max_parallel must be 1..{sb['max_parallel']}.")
    want = child.get("cpu_affinity")
    if want is not None:
        from launch_run import parse_cpus
        if not set(parse_cpus(want)) <= set(parse_cpus(sb["cpu_affinity"])):
            raise LabError(f"cpu_affinity must stay inside {sb['cpu_affinity']}.")
    cwd = resolve_cwd(child["cwd"], sb, root)
    cap = float(sb["per_run_wall_clock_hours"])
    default_h = (child.get("limits") or {}).get("wall_clock_hours", cap)
    left_h = (parse_ts(sb["expires"]) - now).total_seconds() / 3600
    est_total = child.get("estimate_cpu_hours")
    plan = []
    for i, e in enumerate(child["entries"]):
        if not isinstance(e, dict) or not isinstance(e.get("cmd"), list) or not e["cmd"] or \
                not all(isinstance(x, str) for x in e["cmd"]):
            raise LabError(f"Entry {i} needs 'cmd' as a non-empty list of strings.")
        for tok in e["cmd"]:
            if any(w in tok.lower() for w in FORBIDDEN_WORDS):
                raise LabError(f"Entry {i} mentions {tok!r}: kubectl/IBM/cluster commands are not allowed.")
        seeds = entry_seeds(e)
        for lo, hi in seeds:
            if not seed_ok(lo, hi, sb["seed_ranges_allowed"], sb["seed_ranges_forbidden"]):
                raise LabError(f"Entry {i}: seed(s) {lo}..{hi} are outside the allowed ranges or in a forbidden range.")
        hours = e.get("wall_clock_hours", default_h)
        cpus = e.get("cpus", 1)
        if not isinstance(hours, (int, float)) or hours <= 0 or hours > cap:
            raise LabError(f"Entry {i}: wall_clock_hours must be in (0, {cap}].")
        if not isinstance(cpus, int) or cpus < 1 or cpus > int(sb["max_parallel"]):
            raise LabError(f"Entry {i}: cpus must be a positive integer.")
        reserve = hours * cpus
        if est_total is not None:
            if not isinstance(est_total, (int, float)) or est_total <= 0:
                raise LabError("estimate_cpu_hours must be a positive number.")
            reserve = min(reserve, est_total / len(child["entries"]))
        eff_h = min(hours, reserve / cpus, left_h)   # enforced wall clock: never exceeds the reservation or expiry
        plan.append({"entry": i, "seeds": seeds, "cpus": cpus, "wall_hours": eff_h, "reserve_cpu_h": eff_h * cpus})
    return cwd, plan


def sandbox_dir(root=None):
    return os.path.join(lab_dir(root), "sandbox")


def used_cpu_hours(db, rid, now=None):
    """Actual CPU-hours of finished runs + reserved worst case of runs still starting/running (parent rid)."""
    total = 0.0
    for r in db.runs(limit=100000):
        if r["request_id"] != rid:
            continue
        try:
            with open(os.path.join(r["run_dir"], "spec_entry.json"), encoding="utf-8") as f:
                sbm = json.load(f).get("sandbox") or {}
        except (OSError, ValueError):
            sbm = {}
        cpus, reserved = sbm.get("cpus", 1), sbm.get("reserve_cpu_h", 0.0)
        if r["status"] in ("starting", "running"):
            total += reserved
        elif r["started"] and r["ended"]:
            total += (parse_ts(r["ended"]) - parse_ts(r["started"])).total_seconds() / 3600 * cpus
    return total


def active_runs(db, rid):
    return sum(1 for r in db.runs(limit=100000) if r["request_id"] == rid and r["status"] in ("starting", "running"))


def log_ledger(rid, record, root=None):
    d = sandbox_dir(root)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, f"{rid}.ledger.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
