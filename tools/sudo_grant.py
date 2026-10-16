#!/usr/bin/env python3
"""Researcher-only: open, show or close a time-limited sudo grant for one approved task.

  python3 tools/sudo_grant.py open R-20261016-006 --preset k8s [--minutes 60]
  python3 tools/sudo_grant.py open R-... --programs systemctl,kubeadm --minutes 30
  python3 tools/sudo_grant.py status
  python3 tools/sudo_grant.py close

While a grant is open, tools/sudo_gate.py lets agents run `sudo <program>` without a terminal prompt, only
for the listed programs, and logs every use to .lab/sudo_audit.jsonl. Agents are denied this script in
.claude/settings.json. The grant lives in a root-owned file, so writing it needs your sudo.
"""
import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sudo_gate import GRANT, NEVER  # noqa: E402

PRESETS = {
    "k8s": ["systemctl", "kubeadm", "crictl", "ctr", "journalctl", "swapoff", "modprobe", "sysctl",
            "containerd", "kubelet", "ls", "ss", "iptables", "ip"],
}
MAX_MINUTES = 240


def sudo(args, stdin=None):
    return subprocess.run(["sudo", *args], input=stdin, text=True, check=True)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("open")
    o.add_argument("task", help="approved request or message id, e.g. R-20261016-006")
    o.add_argument("--preset", choices=sorted(PRESETS))
    o.add_argument("--programs", default="", help="comma-separated program names")
    o.add_argument("--minutes", type=int, default=60)
    sub.add_parser("status")
    sub.add_parser("close")
    a = p.parse_args()

    if a.cmd == "status":
        try:
            g = json.load(open(GRANT, encoding="utf-8"))
        except (OSError, ValueError):
            print("no grant")
            return 0
        left = (g["expires"] - time.time()) / 60
        state = f"{left:.0f} min left" if left > 0 else "expired"
        print(f"{g['task']}: {', '.join(g['programs'])} ({state})")
        return 0
    if a.cmd == "close":
        sudo(["rm", "-f", GRANT])
        print("grant closed")
        return 0

    progs = list(PRESETS.get(a.preset, [])) + [x.strip() for x in a.programs.split(",") if x.strip()]
    bad = sorted(set(progs) & NEVER)
    if bad:
        sys.exit(f"refused: {', '.join(bad)} would allow anything as root")
    if not progs:
        sys.exit("give --preset or --programs")
    minutes = max(1, min(a.minutes, MAX_MINUTES))
    g = {"task": a.task, "programs": sorted(set(progs)), "opened": time.time(),
         "expires": time.time() + minutes * 60}
    sudo(["install", "-d", "-o", "root", "-g", "root", "-m", "755", os.path.dirname(GRANT)])
    sudo(["sh", "-c", f"umask 022; cat > {GRANT}.tmp && mv {GRANT}.tmp {GRANT}"], stdin=json.dumps(g))
    print(f"grant open for {a.task}, {minutes} min: {', '.join(g['programs'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
