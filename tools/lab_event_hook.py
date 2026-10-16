#!/usr/bin/env python3
"""Claude Code hook: append a compact record of each hook event to .lab/events.jsonl.

The dashboard's Agents tab reads this file to draw who is working on what. It costs no LLM tokens.
Only a whitelist of fields is kept and every free-text field is truncated, so tool outputs, file contents
and long commands never reach the log. The hook always exits 0: it must never block Claude Code.
"""
import json
import os
import sys
import time

KEEP = ("hook_event_name", "session_id", "agent_id", "agent_type", "tool_name", "tool_use_id",
        "notification_type", "source", "model")
MAX = 140


def summarize(tool, ti):
    if not isinstance(ti, dict):
        return None
    if tool in ("Bash", "Monitor"):
        return str(ti.get("description") or ti.get("command") or "")[:MAX]
    if tool in ("Agent", "Task"):
        return f'{ti.get("subagent_type", "general")}: {ti.get("description", "")}'[:MAX]
    if tool in ("Read", "Edit", "Write", "NotebookEdit"):
        return str(ti.get("file_path", ""))[-MAX:]
    if tool in ("Skill",):
        return str(ti.get("skill", ""))[:MAX]
    if tool in ("WebSearch",):
        return str(ti.get("query", ""))[:MAX]
    if tool in ("WebFetch",):
        return str(ti.get("url", ""))[:MAX]
    if tool.startswith("mcp__codex"):
        model = ti.get("model")
        prompt = str(ti.get("prompt", ""))[:100]
        return (f"[{model}] " if model else "") + prompt
    return None


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    rec = {k: data[k] for k in KEEP if k in data and isinstance(data[k], (str, int, float))}
    rec["ts"] = round(time.time(), 3)
    if data.get("hook_event_name") == "Notification":
        # e.g. "Claude needs your permission to use Bash" - the dashboard shows it as a banner
        rec["summary"] = str(data.get("message", ""))[:MAX]
    s = summarize(str(data.get("tool_name", "")), data.get("tool_input"))
    if s:
        rec["summary"] = s
    root = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or "."
    path = os.path.join(root, ".lab", "events.jsonl")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
