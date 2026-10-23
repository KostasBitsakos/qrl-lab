#!/usr/bin/env python3
"""Claude Code statusLine command (M-20261021-021): official usage source for the dashboard rings.

Claude Code pipes a JSON object to stdin (https://code.claude.com/docs/en/statusline). We keep ONLY
rate_limits.{five_hour,seven_day}.{used_percentage,resets_at (epoch s)} (each may be absent), plus model.display_name
and as_of, written atomically to ~/qrl-lab/.lab/usage/claude.json (override: $QRL_CLAUDE_USAGE_FILE). Nothing else
from stdin is stored, except cost.total_cost_usd (a number) and session_id, kept as "session_cost_usd" / "session_id"
(M-2026-10-23: estimate of spend on purchased credits, see tools/extra_credits.py; the per-session baselines go to
.lab/usage/extra_credits_state.json). Prints one status line, e.g. "Opus · 5ω 23% · 7ημ 41%". Never fails the status line: on any bad
input it prints the model name (or "Claude") and exits 0. If stdin carries no rate-limit window, the file is left
unchanged (an earlier reading is not erased by a message that simply lacks the field).
"""
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PATH = os.path.join(ROOT, ".lab", "usage", "claude.json")
WINDOWS = (("five_hour", "5ω"), ("seven_day", "7ημ"))


def _num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def extract(data, now=None):
    """stdin object -> (record or None if no window, model display name or None)."""
    model = None
    if isinstance(data, dict):
        m = data.get("model")
        if isinstance(m, dict) and isinstance(m.get("display_name"), str):
            model = m["display_name"][:80]
    rl = data.get("rate_limits") if isinstance(data, dict) else None
    rec = {}
    if isinstance(rl, dict):
        for key, _ in WINDOWS:
            w = rl.get(key)
            if isinstance(w, dict) and _num(w.get("used_percentage")) is not None:
                rec[key] = {"used_percentage": _num(w["used_percentage"]), "resets_at": _num(w.get("resets_at"))}
    if not rec:
        return None, model
    cost = data.get("cost")
    cost = _num(cost.get("total_cost_usd")) if isinstance(cost, dict) else None
    sid = data.get("session_id")
    if cost is not None and isinstance(sid, str) and sid:
        rec["session_cost_usd"] = cost
        rec["session_id"] = sid[:80]
    rec["as_of"] = time.time() if now is None else now
    if model:
        rec["model"] = model
    return rec, model


def write_atomic(rec, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".claude.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(rec, f)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def status_line(rec, model):
    parts = [model or "Claude"]
    for key, label in WINDOWS:
        if rec and key in rec:
            parts.append(f"{label} {rec[key]['used_percentage']:.0f}%")
    return " · ".join(parts)


def main(stdin=None, stdout=None, path=None):
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    path = path or os.environ.get("QRL_CLAUDE_USAGE_FILE") or DEFAULT_PATH
    rec, model = None, None
    try:
        data = json.loads(stdin.read() or "null")
        rec, model = extract(data)
        if rec:
            write_atomic(rec, path)
            if "session_cost_usd" in rec:
                import extra_credits
                extra_credits.observe(rec["session_id"], rec["session_cost_usd"], usage_dir=os.path.dirname(path))
    except Exception:  # noqa: BLE001 - the status line must never break
        pass
    try:
        stdout.write(status_line(rec, model) + "\n")
    except Exception:  # noqa: BLE001
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
