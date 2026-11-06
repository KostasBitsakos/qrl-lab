"""Offline Redis RESP request schedule. Δεν ανοίγει socket ή εκτελεί αιτήματα."""
import argparse
import dataclasses
import hashlib
import json
import math
from pathlib import Path

from sim_poisson_ms import PoissonMSEnv, VARIANTS


def schedule(seed, ticks, tick_seconds, variant="poisson_ms"):
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    if isinstance(ticks, bool) or not isinstance(ticks, int) or ticks <= 0:
        raise ValueError("ticks must be a positive integer")
    if not math.isfinite(tick_seconds) or tick_seconds <= 0:
        raise ValueError("tick_seconds must be positive and finite")
    if variant not in ("poisson_ms", "poisson_hom"):
        raise ValueError("unsupported variant")
    # Match make()+reset() in the simulator run_fixed episode entry point.
    env = PoissonMSEnv(variant=variant, seed=seed)
    env.reset()
    workload = env.wl
    request_id = 0
    for tick in range(ticks):
        lam, offsets = workload.next_tick()
        for offset in offsets:
            # Fixed synthetic SET payload; keys have a stable prefix for future test isolation.
            # Distinct keys are not sufficient to make arbitrary live Redis use safe.
            parts = [b"SET", f"qrl-calib:{seed}:{request_id}".encode("ascii"), b"x"]
            resp = b"*3\r\n" + b"".join(
                b"$" + str(len(part)).encode("ascii") + b"\r\n" + part + b"\r\n"
                for part in parts
            )
            yield {"request_id": request_id, "tick": tick, "offset": float(offset),
                   "scheduled_seconds": (tick + float(offset)) * tick_seconds,
                   "lambda_per_tick": float(lam), "resp_hex": resp.hex()}
            request_id += 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--ticks", type=int, required=True)
    parser.add_argument("--tick-seconds", type=float, required=True,
                        help="Explicit draft mapping; not a calibrated service time")
    parser.add_argument("--variant", choices=["poisson_ms", "poisson_hom"], default="poisson_ms")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    # Validate before creating any file. Never overwrite existing output/sidecar.
    rows = schedule(args.seed, args.ticks, args.tick_seconds, args.variant)
    first = next(rows, None)
    meta_path = args.output.with_suffix(args.output.suffix + ".meta.json")
    if args.output.exists() or meta_path.exists():
        parser.error("output or metadata already exists")
    meta = {"seed": args.seed, "ticks": args.ticks, "tick_seconds": args.tick_seconds,
            "variant": args.variant, "params": dataclasses.asdict(VARIANTS[args.variant]),
            "source_sha256": hashlib.sha256(Path(__file__).with_name("sim_poisson_ms.py").read_bytes()).hexdigest(),
            "alignment": "PoissonMSEnv constructor + explicit reset; matches run_fixed", "transport": "offline only"}
    import itertools
    count = 0
    digest = hashlib.sha256()
    with args.output.open("x", encoding="utf-8") as out:
        for row in itertools.chain([] if first is None else [first], rows):
            line = json.dumps(row, sort_keys=True) + "\n"
            out.write(line)
            digest.update(line.encode("utf-8"))
            count += 1
    meta.update(request_count=count, schedule_sha256=digest.hexdigest())
    with meta_path.open("x", encoding="utf-8") as out:
        json.dump(meta, out, indent=2, sort_keys=True)
        out.write("\n")


if __name__ == "__main__":
    main()
