"""J444: per-tick trajectories of the reference controllers (eval-only, val split only, no learning).
Run with cwd = code-poisson-c345 via tools/envelope.py. Uses the same env/controllers as tuning/pms_reference.py."""
import json, os, sys
sys.path.insert(0, os.getcwd())
from tuning import pms_adapter as PA
from tuning import pms_reference as PR
from tuning.legacy import c5_protocol as C5, live_rec

def main():
    variant, out, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
    ctrls = [x.split("=") for x in sys.argv[4].split(",")]      # kind=param
    seeds = [int(s) for s in PA.split_seeds(variant, "val")][:n]
    res = {"variant": variant, "split": "val", "seeds": seeds, "controllers": {}}
    for kind, x in ctrls:
        x = float(x) if "." in x else int(x)
        eps = []
        for s in seeds:
            env = PA.make(variant, s); s0 = env.reset(); tr = live_rec.TrajRecorder()
            ep = C5.eval_episode(env, PR.make_policy(kind, x, env), False, s0, env.p.ep_ticks, None, 1, None, tr)
            eps.append(dict(seed=s, ret=ep["ret"], **tr.d))
        res["controllers"][f"{kind}_{x}"] = eps
        print(kind, x, [round(e["ret"]) for e in eps], flush=True)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(res, open(out, "w"), separators=(",", ":"))

if __name__ == "__main__":
    main()
