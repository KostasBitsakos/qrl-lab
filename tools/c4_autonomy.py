"""Temporary researcher authorization M-20261110-049; no request/card mutation."""
import datetime as dt
import json
from pathlib import Path

from labdb import LabError, canonical_hash, validate_spec

UNTIL = dt.datetime.fromisoformat("2026-11-13T23:59+02:00")
PATHS = ["code-poisson-c4/", ".lab/c4/"]


def policy(root, at=None):
    root = Path(root).resolve()
    cfg = json.loads((root / "config/c4_auto_approve.json").read_text())["auto_approve"]
    expiry = dt.datetime.fromisoformat(cfg["until"])
    if cfg["scope"] != "c4-sim" or cfg["paths"] != PATHS or expiry.tzinfo is None or expiry > UNTIL:
        raise LabError("Invalid c4 auto_approve policy.")
    active = (at or dt.datetime.now(dt.timezone.utc)) < expiry
    return dict(cfg, active=active)


def authorize(root, spec_path, at=None, entry=None):
    root = Path(root).resolve()
    cfg = policy(root, at)
    if not cfg["active"]:
        raise LabError("c4 auto_approve expired.")
    roots = [(root / p).resolve() for p in PATHS]
    if any(p != root / rel.rstrip("/") for p, rel in zip(roots, PATHS)):
        raise LabError("c4 authorized roots must not be symlinks.")
    path = Path(spec_path).resolve()
    if not any(path.is_relative_to(p) for p in roots):
        raise LabError("c4 spec path outside authorized paths.")
    spec = json.loads(path.read_text())
    validate_spec(spec)
    cwd = (root / spec["cwd"]).resolve()
    if spec["scope"] != "sim" or spec.get("kind", "run") != "run" or cwd != roots[0]:
        raise LabError("Only c4 sim run specs are auto-approved.")
    threads = spec.get("env_threads") or {}
    if any(k not in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS")
           or str(v) != "1" for k, v in threads.items()):
        raise LabError("c4 auto_approve permits only single-thread numeric environment settings.")
    # Narrow entry point: no shell, -c, kubectl, arbitrary binaries or other worktrees.
    for index, e in enumerate(spec["entries"]):
        cmd = e["cmd"]
        if len(cmd) < 3 or cmd[:2] != [str(root / ".venv/bin/python"), "-m"] or cmd[2] != "tuning.c4_train":
            raise LabError("c4 auto_approve requires the validation-only tuning.c4_train entry point.")
        args = cmd[3:]
        if len(args) % 2 or any(flag not in ("--seed", "--preset", "--set", "--out") for flag in args[::2]):
            raise LabError("c4 requires explicit flag/value pairs; no config files or abbreviated flags.")
        if args[::2].count("--out") != 1:
            raise LabError("c4 needs exactly one explicit --out.")
        output = (cwd / args[args.index("--out") + 1]).resolve()
        if not output.is_relative_to(roots[0]):
            raise LabError("c4 output/checkpoint path outside worktree.")
        if index == entry and (output.exists() or list(output.parent.glob(output.stem + ".ck*.pt"))):
            raise LabError("c4 refuses to overwrite existing results or checkpoints.")
        # --set also accepts paths. Only the explicit reviewed initialization path is allowed.
        if any("init_from" in arg or "test" in arg.lower() for arg in cmd[3:]):
            raise LabError("Test or implicit initialization arguments require separate frozen authorization.")
    digest = canonical_hash(spec)
    frozen = root / ".lab/c4/auto/frozen" / (digest + ".json")
    frozen.parent.mkdir(parents=True, exist_ok=True)
    try:
        with frozen.open("x") as f:
            json.dump(spec, f, sort_keys=True, indent=2)
        frozen.chmod(0o444)
    except FileExistsError:
        if canonical_hash(json.loads(frozen.read_text())) != digest:
            raise LabError("Frozen c4 spec hash mismatch.")
    return {"id": "AUTO-c4-" + digest, "spec_hash": digest, "auto_approve": cfg,
            "spec_path": str(frozen)}, spec
