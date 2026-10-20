"""APPROXIMATE estimate of Claude tokens saved by the skills/extension system in a rolling window (εκτίμηση).

Real local data only (event counts); the per-event token numbers are ASSUMPTIONS in dashboard/token_savings.json.
saved = sum_over_categories n_events * (without_per_event - with_per_event). Nothing here is measured.
"""
import json
import os
import time

DEFAULTS = {
    "subagents": {"label": "Subagents (Explore/engineer/scholar/...)", "without": 6000, "with": 600,
                  "why": "work kept out of the coordinator context; only a ~600-token summary returns"},
    "codex": {"label": "Κλήσεις Codex (codex-*)", "without": 8000, "with": 800,
              "why": "review/research done by Codex instead of Claude; Claude only posts and synthesises"},
    "skills": {"label": "Skills (ask-user/inbox/council)", "without": 600, "with": 150,
               "why": "a stored protocol replaces re-explaining the procedure in prompts"},
    "sandbox_runs": {"label": "Ολοκληρωμένα sandbox runs (scripts)", "without": 1500, "with": 100,
                     "why": "drive_chunks/sum_*.py collect and summarise results instead of an LLM polling loop"},
    "health_events": {"label": "Health watcher (HealthState)", "without": 400, "with": 0,
                      "why": "a script watches health; an LLM check would cost a few hundred tokens"},
}


def load_assumptions(path):
    try:
        data = json.load(open(path, encoding="utf-8"))
        return {k: {**DEFAULTS[k], **(data.get(k) or {})} for k in DEFAULTS}
    except (OSError, ValueError):
        return {k: dict(v) for k, v in DEFAULTS.items()}


def _iso(ts):
    import datetime as dt
    try: return dt.datetime.fromisoformat(ts).timestamp()
    except (TypeError, ValueError): return None


def count_events(events_path, ledger_paths, since, until=None):
    """Counts per category in [since, until]. Codex wrapper agents ('codex:codex-rescue') are not counted (double)."""
    until = until or time.time()
    n = {k: 0 for k in DEFAULTS}
    try:
        with open(events_path, encoding="utf-8") as f:
            for ln in f:
                try: r = json.loads(ln)
                except ValueError: continue
                ts = r.get("ts")
                if not isinstance(ts, (int, float)) or not since <= ts <= until: continue
                k, at = r.get("hook_event_name"), r.get("agent_type") or ""
                if k == "SubagentStart":
                    if at.startswith("codex-"): n["codex"] += 1
                    elif at and not at.startswith("codex:"): n["subagents"] += 1
                elif k == "PreToolUse" and r.get("tool_name") == "Skill": n["skills"] += 1
                elif k == "HealthState": n["health_events"] += 1
    except OSError: pass
    for p in ledger_paths:
        try:
            for ln in open(p, encoding="utf-8"):
                try: r = json.loads(ln)
                except ValueError: continue
                t = _iso(r.get("ts"))
                if r.get("event") == "done" and t and since <= t <= until: n["sandbox_runs"] += 1
        except OSError: pass
    return n


def compute(counts, assumptions):
    rows, w, s = [], 0, 0
    for k, a in assumptions.items():
        n = counts.get(k, 0)
        wo, wi = n * a["without"], n * a["with"]
        rows.append({"key": k, "label": a["label"], "n": n, "without": wo, "with": wi, "saved": wo - wi})
        w += wo; s += wi
    return {"rows": rows, "without": w, "with": s, "saved": w - s, "pct": (100.0 * (w - s) / w) if w else 0.0}
