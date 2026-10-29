#!/usr/bin/env python3
"""Cycle-2 daily report (J72): a plain script, no LLM.

Reads `launch_run.py list` / `sandbox-status`, the per-run spec_entry.json files and docs/EXPERIMENTS.md, and posts
a short Greek status into thread M-20261029-006 (researcher's cycle-2 spec, `docs/cycle2_plan.md:75,82`).

  python3 tools/cycle2_daily.py --dry-run     print the report, post nothing
  python3 tools/cycle2_daily.py               post once per Athens day, only at 18:xx Athens (cron runs it hourly)
  python3 tools/cycle2_daily.py --force       post now regardless of the hour/stamp (still respects the deadline)

After the deadline (2026-11-02, Athens) it posts nothing and removes its own crontab line.
Never launches runs, never touches kubectl.
"""
import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
REQUEST = "R-20261029-006"
THREAD = "M-20261029-006"
BUDGET_CPU_H = 160.0
DEADLINE = dt.date(2026, 11, 2)
POST_HOUR = 18
TZ = ZoneInfo("Europe/Athens")
STAMP_DIR = ROOT / ".lab" / "cycle2_daily"
CRON_MARK = "tools/cycle2_daily.py"
STAGES = ("smoke", "tuning", "final")

LIST_RE = re.compile(r"^(?P<run>\S+)\s+(?P<status>\S+)\s+exit=(?P<exit>\S+)\s+(?P<scope>\S+)\s+(?P<label>\S+)\s*$")
STATUS_RE = re.compile(r"(?P<used>[\d.]+)\s*/\s*(?P<budget>[\d.]+)\s*CPU-h used.*?(?P<running>\d+)/(?P<slots>\d+) running")


def run_cli(*args):
    p = subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, timeout=120)
    return p.stdout if p.returncode == 0 else ""


def parse_list(text, request=REQUEST):
    runs = []
    for line in text.splitlines():
        m = LIST_RE.match(line.strip())
        if m and f"-{request}-" in m["run"]:
            runs.append(m.groupdict())
    return runs


def parse_status(text):
    m = STATUS_RE.search(text or "")
    if not m:
        return None
    return {"used": float(m["used"]), "budget": float(m["budget"]), "running": int(m["running"])}


def stage_of(label):
    low = label.lower()
    if "smoke" in low:
        return "smoke"
    if "final" in low or "test" in low:
        return "final"
    if "tun" in low or "screen" in low or "val" in low:
        return "tuning"
    return "unknown"


def branch_of(run, runs_dir):
    """claude/codex from the run's spec_entry.json (sandbox.repo), else from the label."""
    try:
        repo = json.loads((runs_dir / run["run"] / "spec_entry.json").read_text())["sandbox"]["repo"]
        return "codex" if repo.endswith("astra") else "claude"
    except (OSError, ValueError, KeyError, TypeError):
        low = run["label"].lower()
        return "codex" if "codex" in low or "astra" in low else ("claude" if "claude" in low else "unknown")


def is_failure(run):
    if run["status"] == "running":
        return False
    return run["status"] != "done" or run["exit"] != "0"


def experiments_line(path):
    try:
        for i, line in enumerate(path.read_text().splitlines(), 1):
            if REQUEST in line and line.startswith("|"):
                return i
    except OSError:
        pass
    return None


def build_report(runs, status, runs_dir, exp_line, today):
    table = {(b, s): {"done": 0, "running": 0, "failed": 0} for b in ("claude", "codex") for s in STAGES}
    failures = []
    for r in runs:
        b, s = branch_of(r, runs_dir), stage_of(r["label"])
        cell = table.setdefault((b, s), {"done": 0, "running": 0, "failed": 0})
        if r["status"] == "running":
            cell["running"] += 1
        elif is_failure(r):
            cell["failed"] += 1
            failures.append(r)
        else:
            cell["done"] += 1
    days_left = (DEADLINE - today).days
    lines = [f"**Ημερήσια αναφορά κύκλου 2 — {today:%d/%m}** (αυτόματη, `tools/cycle2_daily.py`; προθεσμία 02/11, "
             f"{days_left} μέρες)", ""]
    if status:
        note = " (άνω όριο: μετράει και κρατήσεις των runs που τρέχουν)" if status["running"] else ""
        lines.append(f"- CPU-h: {status['used']:.1f} / {status['budget']:.0f}{note} "
                     f"→ `launch_run.py sandbox-status --request {REQUEST}`")
    else:
        lines.append(f"- CPU-h: unknown (sandbox-status δεν απάντησε) → {REQUEST}")
    lines.append(f"- Runs {REQUEST}: {len(runs)} σύνολο → `launch_run.py list`")
    for b in ("claude", "codex"):
        parts = []
        for s in STAGES:
            c = table[(b, s)]
            n = sum(c.values())
            parts.append(f"{s} {c['done']}✓/{c['running']}▶/{c['failed']}✗" if n else f"{s} —")
        lines.append(f"- {b}: " + " · ".join(parts))
    other = sum(sum(c.values()) for (b, s), c in table.items() if b == "unknown" or s == "unknown")
    if other:
        lines.append(f"- Χωρίς αναγνωρίσιμο branch/στάδιο: {other} runs")
    if failures:
        shown = ", ".join(f"`{f['run']}` ({f['status']}, exit={f['exit']})" for f in failures[:3])
        more = f" +{len(failures) - 3}" if len(failures) > 3 else ""
        lines.append(f"- Αποτυχίες: {len(failures)}: {shown}{more} → `.lab/runs/<run>/output.log`")
    else:
        lines.append("- Αποτυχίες: 0")
    lines.append(f"- Μητρώο: `docs/EXPERIMENTS.md:{exp_line}`" if exp_line else "- Μητρώο: unknown")
    lines.append("- Αποτελέσματα/συγκρίσεις: μόνο σε ξεχωριστή ανάλυση με CI, όχι εδώ.")
    lines += ["", "— Πάρις (script)"]
    return "\n".join(lines[:17])


def remove_cron_line():
    cur = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if cur.returncode != 0 or CRON_MARK not in cur.stdout:
        return False
    keep = "".join(l + "\n" for l in cur.stdout.splitlines() if CRON_MARK not in l)
    subprocess.run(["crontab", "-"], input=keep, text=True, check=True)
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="print the report, post nothing")
    ap.add_argument("--force", action="store_true", help="post now (ignore hour and once-per-day stamp)")
    a = ap.parse_args(argv)
    now = dt.datetime.now(TZ)
    today = now.date()
    if today > DEADLINE and not a.dry_run:
        print("cycle2_daily: past deadline; removed cron line" if remove_cron_line() else "cycle2_daily: past deadline")
        return 0
    stamp = STAMP_DIR / f"posted-{today.isoformat()}"
    if not a.dry_run and not a.force and (now.hour != POST_HOUR or stamp.exists()):
        return 0
    runs = parse_list(run_cli("tools/launch_run.py", "list"))
    status = parse_status(run_cli("tools/launch_run.py", "sandbox-status", "--request", REQUEST))
    body = build_report(runs, status, ROOT / ".lab" / "runs", experiments_line(ROOT / "docs" / "EXPERIMENTS.md"), today)
    if a.dry_run:
        print(body)
        return 0
    out = subprocess.run([sys.executable, "tools/labq.py", "post", "--reply-to", THREAD, "--kind", "status",
                          "--author", "coordinator", "--model", "script", "--body", body],
                         cwd=ROOT, capture_output=True, text=True)
    print(out.stdout.strip() or out.stderr.strip())
    if out.returncode == 0:
        STAMP_DIR.mkdir(parents=True, exist_ok=True)
        stamp.write_text(now.isoformat() + "\n")
    return out.returncode


if __name__ == "__main__":
    sys.exit(main())
