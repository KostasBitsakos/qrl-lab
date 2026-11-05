#!/usr/bin/env python3
"""Cost baseline from the dispatcher's `tasks` table (v0.5.1 §4 B0). Read-only, no model calls.

  python3 tools/cost_report.py              runs and ≈$ per UTC day and task kind, last 14 days
  python3 tools/cost_report.py --days 30    other window
  python3 tools/cost_report.py --json       machine-readable rows

The database is opened as a sqlite URI with ?mode=ro and only SELECT is issued.
≈$ is tasks.cost_usd: Claude's client-side estimate (total_cost_usd). Codex runs report no cost, so they are counted
under `no_cost` and never priced here.
"""
import argparse
import datetime as dt
import json
import sqlite3
from contextlib import closing
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / ".lab" / "dispatch.db"

QUERY = """
SELECT substr(started, 1, 10) AS day, kind,
       COUNT(*) AS runs,
       SUM(provider = 'claude') AS claude,
       SUM(provider = 'codex') AS codex,
       ROUND(COALESCE(SUM(cost_usd), 0), 2) AS usd,
       SUM(cost_usd IS NULL) AS no_cost
FROM tasks
WHERE started >= ?
GROUP BY day, kind
ORDER BY day, kind
"""


def connect_ro(path):
    return sqlite3.connect(f"file:{Path(path).resolve()}?mode=ro", uri=True)


def report(path=DB, days=14, today=None):
    today = today or dt.datetime.now(dt.timezone.utc).date()
    since = (today - dt.timedelta(days=days - 1)).isoformat()
    with closing(connect_ro(path)) as c:
        c.row_factory = sqlite3.Row
        return [dict(r) for r in c.execute(QUERY, (since,))]


def render(rows):
    head = f"{'day':<10}  {'kind':<12} {'runs':>5} {'claude':>6} {'codex':>5} {'≈$':>8} {'no_cost':>7}"
    out = [head, "-" * len(head)]
    for r in rows:
        out.append(f"{r['day']:<10}  {r['kind'] or '?':<12} {r['runs']:>5} {r['claude']:>6} {r['codex']:>5}"
                   f" {r['usd']:>8.2f} {r['no_cost']:>7}")
    days = {}
    for r in rows:
        d = days.setdefault(r["day"], [0, 0.0])
        d[0] += r["runs"]
        d[1] += r["usd"]
    out.append("-" * len(head))
    for day, (n, usd) in days.items():
        out.append(f"{day:<10}  {'(all)':<12} {n:>5} {'':>6} {'':>5} {usd:>8.2f}")
    total_n, total_usd = sum(v[0] for v in days.values()), sum(v[1] for v in days.values())
    out.append(f"{'total':<10}  {'':<12} {total_n:>5} {'':>6} {'':>5} {total_usd:>8.2f}")
    if days:
        out.append(f"mean/day over {len(days)} active days: {total_n / len(days):.1f} runs, ≈${total_usd / len(days):.2f}")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Cost baseline from dispatch.db tasks (read-only)")
    ap.add_argument("--db", default=str(DB))
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    rows = report(a.db, a.days)
    print(json.dumps(rows, indent=1) if a.json else render(rows))


if __name__ == "__main__":
    main()
