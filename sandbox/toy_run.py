"""Toy experiment for acceptance test A5: writes 60 metric lines (about 30 s). No research code, no data."""
import json
import math
import os
import random
import sys
import time

run_dir = os.environ.get("QRL_RUN_DIR", ".")
seed = int(sys.argv[1]) if len(sys.argv) > 1 else 0
random.seed(seed)
total = 60
with open(os.path.join(run_dir, "metrics.jsonl"), "a", encoding="utf-8") as f:
    for step in range(total):
        reward = 100 * (1 - math.exp(-step / 15)) + random.gauss(0, 2)
        f.write(json.dumps({"step": step, "reward": round(reward, 3)}) + "\n")
        f.flush()
        with open(os.path.join(run_dir, "progress.json"), "w") as p:
            json.dump({"step": step + 1, "total": total}, p)
        time.sleep(0.5)
print("toy run finished")
