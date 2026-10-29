"""Checks for the standing sandbox permission (R-20261017-021). Pure functions plus a ledger; used by launch_run.py.

A sandbox approval freezes the PARENT spec (kind 'sandbox'); child specs are not approved one by one, so every
child is verified here against the parent's `sandbox` block: scope sim, no real/qpu/kubectl/IBM, cwd inside the
tuning worktree on the right branch, seeds known and inside the allowed ranges, CPU-hour budget, parallelism,
expiry. Anything not understood is refused.
"""
import datetime as dt
import hashlib
import json
import math
import os
import re
import shutil
import subprocess

from labdb import LabError, lab_dir, lab_root

# repo name in the sandbox block -> worktree directory (relative to the lab root)
# (C-20261021-03: a second, parallel tuning worktree for the Codex branch; each sandbox names its repo and branch, and
# the worktree's checked-out branch must equal the sandbox branch)
WORKTREES = {"code": "code-tuning", "code-astra": "code-tuning-astra",
             "code-poisson": "code-poisson", "code-poisson-astra": "code-poisson-astra"}
CYCLE2_BRANCHES = {"code-poisson": "dinos-poisson", "code-poisson-astra": "dinos-poisson-astra"}
# Peeled reviewed cycle2-env-v1 commit, never a movable tag/branch.
CYCLE2_ENV_COMMIT = "238003f58a7ae547c9ff03b05f5484ea5a1c342b"
# Peeled reviewed cycle2-harness-v1 commit (J40, Codex APPROVE r3) and the shared harness files pinned to it.
CYCLE2_HARNESS_COMMIT = "b609b939085ee3e07c334b94d2cd79929938df9b"
# Reviewed launcher wrapper added after the harness freeze (cc83534:tuning/cycle2_entry.py).
# Separate content pin leaves both existing frozen commits intact.
CYCLE2_ENTRY_SHA256 = "1b5a6f2922422e26b15f6729969f5870e994f1922d867cfa7f5ac880117d000e"
CYCLE2_ENTRY_FILE = "tuning/cycle2_entry.py"
CYCLE2_HARNESS_FILES = ("tuning/pms_adapter.py", "tuning/rppo.py", "tuning/pms_reference.py",
                        "tuning/legacy/c5_protocol.py", "tuning/legacy/orig_variants.py",
                        # shared evaluation helpers (greedy_fn, summarize) and the transfer source env (Codex J48 r1)
                        "tuning/legacy/run_legacy.py", "tuning/legacy/env_orig.py")
FORBIDDEN_WORDS = ("kubectl", "qiskit_ibm", "ibm_quantum", "ibmq", "qiskit-ibm", "helm", "kube")
FORBIDDEN_KEYS = {"real", "qpu", "kube_context", "backend_name", "ibm"}
# Files whose bytes on the tuning worktree must equal those on REFERENCE_BRANCH (qrl-dev) before any launch:
# simulator dynamics, workloads, parameters, the DInos reward (constants and adapter). Paths are relative to the repo.
REFERENCE_BRANCH = "qrl-dev"
PROTECTED_FILES = ("sim_v2/env.py", "sim_v2/params.py", "sim_v2/workloads.py", "sim_v2/reward_dinos.json",
                   "experiments/dinos_simv2/adapter.py")
SHELLS = {"sh", "bash", "dash", "zsh", "ksh", "csh", "tcsh", "fish", "env", "busybox", "ash"}
ENV_ALLOWED = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS")
MAX_TOTAL_CPUS = 32
SEED_FLAG = re.compile(r"^--?(?:[\w-]*[-_])?seeds?(?:=(.*))?$")


def _no_constant(name):
    raise LabError(f"Non-finite number {name} in the child spec; refused.")


def check_finite(o):
    """Raise LabError if any float anywhere in o is NaN/inf."""
    if isinstance(o, float) and not math.isfinite(o):
        raise LabError("Non-finite number in the child spec; refused.")
    if isinstance(o, dict):
        for v in o.values():
            check_finite(v)
    elif isinstance(o, list):
        for v in o:
            check_finite(v)


def loads_strict(text):
    """json.loads that refuses NaN/Infinity/-Infinity and overflowing literals such as 1e999."""
    o = json.loads(text, parse_constant=_no_constant)
    check_finite(o)
    return o


def check_env(d, where):
    """Only the thread variables, with a value of 1..4; anything else (QRL_*, PYTHONPATH, ...) is refused."""
    if d is None:
        return {}
    if not isinstance(d, dict):
        raise LabError(f"{where}: env must be an object.")
    out = {}
    for k, v in d.items():
        sv = str(v)
        if k not in ENV_ALLOWED or isinstance(v, (bool, float)) or not re.fullmatch(r"[1-4]", sv):
            raise LabError(f"{where}: environment variable {k!r}={v!r} is not allowed "
                           f"(only {', '.join(ENV_ALLOWED)} with a value of 1..4).")
        out[k] = sv
    return out


def check_cmd(cmd, cwd, root=None, wt=None):
    """Entrypoint = the project venv python or python3 running a .py file that resolves inside the worktree
    (wt = the sandbox's worktree path; default the 'code' worktree). No shell interpreters, no -c / -m, no env wrapper."""
    root = root or lab_root()
    exe = cmd[0]
    if os.path.basename(exe) in SHELLS or "-c" in cmd:
        raise LabError(f"Shell interpreters / -c are not allowed in a sandbox command ({cmd[0]!r}).")
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    venvs = {os.path.join(b, ".venv", "bin", n) for b in (os.path.abspath(root), here) for n in ("python", "python3")}
    if exe not in ("python3", "python") and os.path.abspath(exe) not in venvs:
        raise LabError(f"Entrypoint {exe!r} must be the project venv python or python3.")
    if len(cmd) < 2 or cmd[1].startswith("-") or not cmd[1].endswith(".py"):
        raise LabError("The first argument must be a .py script (no -c, -m or options before it).")
    script = os.path.realpath(os.path.join(cwd, cmd[1]))
    base = os.path.realpath(wt) if wt else os.path.realpath(os.path.join(root, WORKTREES["code"]))
    if not script.startswith(base + os.sep) or not os.path.isfile(script):
        raise LabError(f"Script {cmd[1]!r} resolves to {script}, which is not a file inside {base}.")
    return script


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def verify_protected(wt, ref=REFERENCE_BRANCH, files=PROTECTED_FILES):
    """sha256 of each protected file on the worktree (working copy) must equal that on `ref` (git blob).
    Missing on either side = refused."""
    bad = []
    for rel in files:
        out = subprocess.run(["git", "-C", wt, "show", f"{ref}:{rel}"], capture_output=True, timeout=30)
        try:
            with open(os.path.join(wt, rel), "rb") as f:
                have = _sha(f.read())
        except OSError:
            have = None
        if out.returncode != 0 or have != _sha(out.stdout):
            bad.append(rel)
    if bad:
        raise LabError(f"Protected file(s) differ from {ref} (or are missing): {', '.join(bad)}. Nothing was started.")


def select_worktree(sb, child):
    """Select a branch from ONE parent. All limits remain on the parent/request id."""
    pairs = sb.get("worktrees")
    if pairs is None:
        if child.get("repo", sb.get("repo")) != sb.get("repo"):
            raise LabError("Child repo differs from the sandbox repo.")
        selected = sb
    else:
        if "repo" in sb or "branch" in sb or not isinstance(pairs, list) or not pairs:
            raise LabError("Aggregate sandbox needs worktrees only, without top-level repo/branch.")
        check_finite(sb)
        budget = sb.get("cpu_hours_budget")
        if isinstance(budget, bool) or not isinstance(budget, (int, float)) or not 0 < budget <= 160:
            raise LabError("Aggregate sandbox cpu_hours_budget must be in (0, 160].")
        seen = set()
        for pair in pairs:
            if not isinstance(pair, dict) or set(pair) != {"repo", "branch"}:
                raise LabError("Each sandbox worktree needs exactly repo and branch.")
            repo = pair["repo"]
            if not isinstance(repo, str) or repo in seen or repo not in CYCLE2_BRANCHES:
                raise LabError("Unknown or duplicate aggregate worktree repo.")
            if pair["branch"] != CYCLE2_BRANCHES[repo]:
                raise LabError("Cycle2 worktree branch binding differs from the reviewed mapping.")
            seen.add(repo)
        matches = [p for p in pairs if p["repo"] == child.get("repo")]
        if len(matches) != 1:
            raise LabError("Child repo must select one authorized sandbox worktree.")
        selected = dict(sb, **matches[0])
    if selected.get("repo") in CYCLE2_BRANCHES:
        if pairs is None:
            raise LabError("Cycle2 requires one aggregate sandbox worktrees list.")
        if sb.get("frozen_env_commit") != CYCLE2_ENV_COMMIT:
            raise LabError("Cycle2 frozen_env_commit must equal the reviewed environment commit.")
        if sb.get("frozen_harness_commit") != CYCLE2_HARNESS_COMMIT:
            raise LabError("Cycle2 frozen_harness_commit must equal the reviewed harness commit.")
        if sb.get("frozen_entry_sha256") != CYCLE2_ENTRY_SHA256:
            raise LabError("Cycle2 frozen_entry_sha256 must equal the reviewed wrapper digest.")
    return selected


def verify_sandbox_protected(sb, root=None):
    wt = worktree_path(sb, root)
    if sb.get("repo") in CYCLE2_BRANCHES:
        if worktree_branch(wt) != sb["branch"]:
            raise LabError(f"Worktree {wt} is not on branch {sb['branch']}.")
        dirs = ("sim_v2", "experiments/dinos_simv2")
        out = subprocess.run(["git", "-C", wt, "ls-tree", "-rz", "--name-only", CYCLE2_ENV_COMMIT,
                              "--", *dirs], capture_output=True, timeout=30)
        tracked = set(os.fsdecode(p) for p in out.stdout.split(b"\0") if p)
        if out.returncode or not set(PROTECTED_FILES) <= tracked:
            raise LabError("Protected file tree missing from reviewed environment commit.")
        verify_protected(wt, CYCLE2_ENV_COMMIT, tuple(sorted(tracked)) + ("tuning/poisson_ms.py",))
        verify_protected(wt, CYCLE2_HARNESS_COMMIT, CYCLE2_HARNESS_FILES)
        try:
            with open(os.path.join(wt, CYCLE2_ENTRY_FILE), "rb") as f:
                entry_hash = _sha(f.read())
        except OSError as exc:
            raise LabError("Protected wrapper is missing or unreadable. Nothing was started.") from exc
        if entry_hash != CYCLE2_ENTRY_SHA256:
            raise LabError("Protected wrapper differs from reviewed digest. Nothing was started.")
        # Reject extra importable sources even if gitignored. Bytecode caches are generated normally.
        for directory in dirs:
            for base, subdirs, names in os.walk(os.path.join(wt, directory)):
                subdirs[:] = [d for d in subdirs if d != "__pycache__"]
                for name in names:
                    rel = os.path.relpath(os.path.join(base, name), wt)
                    if name.endswith(".py") and rel not in tracked:
                        raise LabError(f"Unreviewed protected Python source {rel}; refused.")
        for name in ("sitecustomize.py", "usercustomize.py"):
            if os.path.lexists(os.path.join(wt, name)):
                raise LabError(f"Unreviewed Python startup source {name}; refused.")
    else:
        verify_protected(wt)


def seed_env(sb):
    """QRL_SANDBOX_SEEDS value: allowed ranges minus forbidden ranges, e.g. '0-999,1000-1004'."""
    out = []
    for lo, hi in sorted((int(a), int(b)) for a, b in sb["seed_ranges_allowed"]):
        cur = [[lo, hi]]
        for fa, fb in sorted((int(a), int(b)) for a, b in sb["seed_ranges_forbidden"]):
            nxt = []
            for a, b in cur:
                if fb < a or fa > b:
                    nxt.append([a, b])
                    continue
                if a < fa:
                    nxt.append([a, fa - 1])
                if fb < b:
                    nxt.append([fb + 1, b])
            cur = nxt
        out += cur
    return ",".join(f"{a}-{b}" if a != b else str(a) for a, b in out)


def assign_cores(pool, busy, cpus_list, cap=MAX_TOTAL_CPUS):
    """Disjoint core sets, one per entry (len == cpus), from pool minus busy. Fail closed: LabError if the pool is
    empty or too small, or if busy + new would exceed `cap` cores in total."""
    pool = sorted(set(pool))
    if not pool:
        raise LabError("The CPU affinity pool is empty on this machine (fail closed). Nothing was started.")
    free = [c for c in pool if c not in set(busy)]
    need = sum(cpus_list)
    if len(busy) + need > cap:
        raise LabError(f"CPU cores: {len(busy)} assigned + {need} new exceed the limit {cap}. Nothing was started.")
    if need > len(free):
        raise LabError(f"Only {len(free)} free cores in the pool, {need} needed. Nothing was started.")
    out, i = [], 0
    for n in cpus_list:
        out.append(free[i:i + n])
        i += n
    return out


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
    check_finite(child)
    sb = parent.get("sandbox")
    if parent.get("kind") != "sandbox" or not isinstance(sb, dict):
        raise LabError("The request is not a sandbox approval (spec kind != 'sandbox').")
    if parent.get("scope") != "sim":
        raise LabError("Sandbox parent scope must be 'sim'.")
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
    check_env(child.get("env"), "child")
    check_env(child.get("env_threads"), "child")
    selected = select_worktree(sb, child)
    cwd = resolve_cwd(child["cwd"], selected, root)
    cap = float(sb["per_run_wall_clock_hours"])
    default_h = (child.get("limits") or {}).get("wall_clock_hours", cap)
    left_h = (parse_ts(sb["expires"]) - now).total_seconds() / 3600
    est_total = child.get("estimate_cpu_hours")
    plan = []
    for i, e in enumerate(child["entries"]):
        if not isinstance(e, dict) or not isinstance(e.get("cmd"), list) or not e["cmd"] or \
                not all(isinstance(x, str) for x in e["cmd"]):
            raise LabError(f"Entry {i} needs 'cmd' as a non-empty list of strings.")
        check_env(e.get("env"), f"entry {i}")
        check_env(e.get("env_threads"), f"entry {i}")
        for tok in e["cmd"]:
            if any(w in tok.lower() for w in FORBIDDEN_WORDS):
                raise LabError(f"Entry {i} mentions {tok!r}: kubectl/IBM/cluster commands are not allowed.")
        check_cmd(e["cmd"], cwd, root, worktree_path(selected, root))
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


def used_cpu_hours(db, rid, now=None, strict=False):
    """Actual CPU-hours of finished runs + reserved worst case of runs still starting/running (parent rid)."""
    total = 0.0
    for r in db.runs(limit=100000):
        if r["request_id"] != rid:
            continue
        try:
            with open(os.path.join(r["run_dir"], "spec_entry.json"), encoding="utf-8") as f:
                sbm = json.load(f).get("sandbox") or {}
        except (OSError, ValueError):
            if strict:
                raise LabError(f"Missing or invalid sandbox accounting for {r['run_id']}; refused.")
            sbm = {}
        cpus, reserved = sbm.get("cpus", 1), sbm.get("reserve_cpu_h", 0.0)
        if strict and (not isinstance(cpus, int) or isinstance(cpus, bool) or cpus < 1 or
                       isinstance(reserved, bool) or not isinstance(reserved, (int, float)) or
                       not math.isfinite(reserved) or reserved <= 0):
            raise LabError(f"Invalid sandbox accounting for {r['run_id']}; refused.")
        if r["status"] in ("starting", "running"):
            total += reserved
        elif r["started"] and r["ended"]:
            elapsed = (parse_ts(r["ended"]) - parse_ts(r["started"])).total_seconds() / 3600 * cpus
            if strict and elapsed < 0:
                raise LabError(f"Negative sandbox accounting for {r['run_id']}; refused.")
            total += elapsed
        elif strict:
            total += reserved  # failed before timestamps: do not silently refund unknown usage
    return total


def active_runs(db, rid):
    return sum(1 for r in db.runs(limit=100000) if r["request_id"] == rid and r["status"] in ("starting", "running"))


def log_ledger(rid, record, root=None):
    d = sandbox_dir(root)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, f"{rid}.ledger.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
