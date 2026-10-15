#!/usr/bin/env python3
"""Sanity check for a simulator: how much reward do fixed, non-learning policies get?

If a fixed policy (e.g. "always scale down") beats the trained agents, the simulator does not reward
good autoscaling, and model comparisons on it are not meaningful (PLAN.md §2 F1).

Usage:  python3 -I tools/sanity_trivial_policies.py <directory containing environment.py> [steps] [runs]
The directory's Environment class must offer reset() and step(action) -> (state, reward, ...),
with actions 0 = scale down, 1 = no change, 2 = scale up (DInos convention).
"""
import sys

import numpy as np


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sys.path.insert(0, sys.argv[1])
    from environment import Environment  # noqa: E402  # pyright: ignore[reportMissingImports]

    steps = int(sys.argv[2]) if len(sys.argv) > 2 else 5000
    runs = int(sys.argv[3]) if len(sys.argv) > 3 else 5

    def run(policy):
        totals = []
        for r in range(runs):
            np.random.seed(r)
            env = Environment()
            env.reset()
            total = 0.0
            for _ in range(steps):
                out = env.step(policy())
                total += out[1]
            totals.append(total)
        return float(np.mean(totals)), float(np.std(totals))

    policies = [
        ("always scale down", lambda: 0),
        ("always no change", lambda: 1),
        ("random", lambda: np.random.randint(3)),
        ("always scale up", lambda: 2),
    ]
    print(f"{steps} steps, mean of {runs} runs (seeds 0..{runs - 1})")
    for name, pol in policies:
        m, s = run(pol)
        print(f"  {name:20s} reward = {m:12.0f}  (std {s:.0f})")


if __name__ == "__main__":
    main()
