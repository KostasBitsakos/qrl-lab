"""Which model actually ran each agent task (Agents tab / race view, M-20261021-014 / -016). Pure; no I/O except
defaults_from_agents_dir().

Per subagent run (SubagentStart record of .lab/events.jsonl), first match wins:
  1. the record's own `model` (tools/agent_log.py start --model ...; Codex roles and explicit logs)  -> source "agent_log"
  2. a tools/agent_log.py start of the same role within MATCH_S seconds of a hook-recorded start that has no model
     (the coordinator logs its delegations there)                                                     -> source "agent_log"
  3. the model of the coordinator's Agent tool call (PreToolUse, tool_input.model, recorded by lab_event_hook.py as
     `agent_model`) for the same subagent type within CALL_S seconds before the start                  -> source "hook"
  4. the role's default from .claude/agents/<role>.md frontmatter                                       -> source "default"
  else «άγνωστο».
Coordinator: the model of the latest SessionStart record (Claude Code reports it there), else «άγνωστο».
"""
import glob
import os
import re

UNKNOWN = "άγνωστο"
MATCH_S = 1800.0
CALL_S = 30.0


def text(model, source):
    """Display text: the model, «προεπιλογή: <model>» for frontmatter defaults, «άγνωστο» when nothing is known."""
    if not model:
        return UNKNOWN
    return f"προεπιλογή: {model}" if source == "default" else str(model)


def defaults_from_agents_dir(root):
    """{role: model} from the `model:` line of each .claude/agents/*.md frontmatter (read-only)."""
    out = {}
    for p in sorted(glob.glob(os.path.join(root, ".claude", "agents", "*.md"))):
        try:
            with open(p, encoding="utf-8") as f:
                head = f.read(4000)
        except OSError:
            continue
        m = re.match(r"^---\s*\n(.*?)\n---", head, re.S)
        if not m:
            continue
        fm = dict((k.strip(), v.strip()) for k, _, v in (ln.partition(":") for ln in m.group(1).splitlines()) if _)
        name = fm.get("name") or os.path.splitext(os.path.basename(p))[0]
        if fm.get("model"):
            out[name] = fm["model"]
    return out


def _is_log(e):
    return str(e.get("agent_id", "")).startswith("log-")


def resolve(events, defaults=None):
    """{agent_id: (model or "", source)} for every SubagentStart in events (ordered by time)."""
    defaults = defaults or {}
    starts = [e for e in events if e.get("hook_event_name") == "SubagentStart" and e.get("agent_id")]
    logs = [e for e in starts if _is_log(e) and e.get("model")]
    calls = [e for e in events if e.get("hook_event_name") == "PreToolUse" and not e.get("agent_id")
             and e.get("tool_name") in ("Agent", "Task") and e.get("agent_model")]
    used_logs, used_calls, out = set(), set(), {}
    for e in starts:
        aid, role, ts = e["agent_id"], e.get("agent_type") or "", float(e.get("ts") or 0)
        if e.get("model"):
            out[aid] = (str(e["model"]), "agent_log" if _is_log(e) else "hook")
            continue
        best = None
        for i, lg in enumerate(logs):
            if i in used_logs or lg.get("agent_type") != role:
                continue
            d = abs(float(lg.get("ts") or 0) - ts)
            if d <= MATCH_S and (best is None or d < best[0]):
                best = (d, i)
        if best:
            used_logs.add(best[1])
            out[aid] = (str(logs[best[1]]["model"]), "agent_log")
            continue
        call = None
        for i, c in enumerate(calls):
            ct = float(c.get("ts") or 0)
            styp = str(c.get("summary") or "").split(":", 1)[0].strip()
            if i not in used_calls and 0 <= ts - ct <= CALL_S and styp == role:
                call = i
        if call is not None:
            used_calls.add(call)
            out[aid] = (str(calls[call]["agent_model"]), "hook")
            continue
        if defaults.get(role):
            out[aid] = (defaults[role], "default")
        else:
            out[aid] = ("", "unknown")
    return out


def coordinator_model(events):
    """Model of the latest SessionStart record that carries one, else ""."""
    for e in reversed(events):
        if e.get("hook_event_name") == "SessionStart" and e.get("model"):
            return str(e["model"])
    return ""
