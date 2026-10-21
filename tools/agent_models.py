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
Coordinator: actual deputy start/stop records and provider health, or the latest Claude SessionStart; absent
evidence is «άγνωστο». Legacy coordinator_model() remains a SessionStart-only compatibility helper.
"""
import glob
import os
import re
import time

UNKNOWN = "άγνωστο"
MATCH_S = 1800.0
CALL_S = 30.0

AUTO_LABEL = "Πάρις (συντονιστής, αυτόματη επιλογή)"
CLAUDE_MODELS = ("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "claude-fable-5-1")
MODEL_CHOICES = {None: AUTO_LABEL, "haiku": "Γρήγορο · Haiku", "sonnet": "Κανονικό · Sonnet",
                 "opus": "Βαθύ · Opus", "codex": "Codex · αυτόματα",
                 **{m: f"Claude · {m}" for m in CLAUDE_MODELS},
                 **{m: f"Codex · {m}" for m in ("gpt-6-luna", "gpt-6-sol", "gpt-6.1-sol", "gpt-6-astra",
                                                "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna")}}
CODEX_EFFORTS = ("low", "medium", "high", "xhigh", "max", "ultra")


def effort_choices(model):
    """Explicit Codex routing supports extended efforts; legacy Claude/auto keep their existing choices."""
    if model == "codex" or str(model).startswith("gpt-"):
        return CODEX_EFFORTS[:-1] if model == "codex" or str(model).endswith("-luna") else CODEX_EFFORTS
    if str(model).startswith("claude-"):
        return ("low", "medium", "high")  # per-family Claude efforts are not documented in the repo: conservative set
    return ("low", "med", "high")


EFFORT_HELP = ("Πόση προσπάθεια/σκέψη θα καταναλώσει η απάντηση. Codex: low–xhigh (luna) ή έως max/ultra (άλλα). "
               "Claude: οι υποστηριζόμενες εντάσεις ανά μοντέλο δεν είναι τεκμηριωμένες στο repo, προσφέρονται "
               "low/medium/high.")


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


def _msg_ts(m):
    """Epoch seconds of a labdb message row (ts is local ISO text); 0 when unparsable."""
    import datetime as dt
    try:
        return dt.datetime.fromisoformat(str(m.get("ts"))).timestamp()
    except (ValueError, TypeError):
        return 0.0


def coordinator_identity(events, health=None, now=None, messages=None):
    """Observed coordinator identity, including temporary Codex leadership.

    Health accepts raw health.json or race_view's normalized provider map. A Claude limit/down suppresses its
    historical session identity. Never infer a deputy model from a routing default or an unrelated Codex worker.
    """
    now = time.time() if now is None else now
    events = sorted((e for e in events if isinstance(e, dict) and float(e.get("ts") or 0) <= now),
                    key=lambda e: float(e.get("ts") or 0))
    health = health or {}
    ch = health.get("claude") or health
    fallback = ch.get("state") in ("limit", "down", "api_error")
    sessions = [e for e in events if e.get("hook_event_name") == "SessionStart"]
    deputies = [e for e in events if e.get("hook_event_name") == "SubagentStart"
                and e.get("agent_type") == "codex-deputy"]
    session = sessions[-1] if sessions else {}
    deputy = deputies[-1] if deputies else {}
    stopped = {e.get("agent_id") for e in events if e.get("hook_event_name") == "SubagentStop"}
    deputy_active = bool(deputy and deputy.get("agent_id") not in stopped
                         and now - float(deputy.get("ts") or 0) < 3 * 3600)
    # Latest ACTUAL actor wins: Claude coordinator tool calls / session start vs the deputy's start and its
    # posted answers (labq messages with author codex; row `model` looks like «gpt-6.1-sol · low · αναπληρωτής»).
    claude_ts = max([float(x.get("ts") or 0) for x in events if not x.get("agent_id")
                     and x.get("hook_event_name") in ("SessionStart", "PreToolUse", "PostToolUse")] or [0.0])
    posts = [m for m in (messages or []) if m.get("author") == "codex" and "αναπληρωτής" in str(m.get("model") or "")
             and 0 <= now - _msg_ts(m) < 3 * 3600]
    post = max(posts, key=_msg_ts) if posts else None
    dep_ts = max(float(deputy.get("ts") or 0) if deputy else 0.0, _msg_ts(post) if post else 0.0)
    use_deputy = bool((deputy or post) and (fallback or (deputy_active and dep_ts >= claude_ts) or
                      (dep_ts > claude_ts and now - dep_ts < 3 * 3600)))
    if use_deputy and not deputy_active and post and _msg_ts(post) >= float(deputy.get("ts") or 0 if deputy else 0):
        e = {"ts": _msg_ts(post), "model": str(post["model"]).split("·")[0].strip(), "agent_id": post.get("id"),
             "effort": (str(post["model"]).split("·") + ["", ""])[1].strip()}
        provider, role, active = "Codex", "codex-deputy", False
    elif use_deputy:
        e, provider, role, active = deputy, "Codex", "codex-deputy", deputy_active
    elif session and not fallback:
        e, provider, role = session, "Claude", "coordinator"
        active = any(not x.get("agent_id") and x.get("hook_event_name") in ("PreToolUse", "PostToolUse")
                     and 0 <= now - float(x.get("ts") or 0) < 120 for x in events)
    else:
        e, provider, role = {}, UNKNOWN, "coordinator"
        active = not fallback and any(not x.get("agent_id") and x.get("hook_event_name") in ("PreToolUse", "PostToolUse")
                                     and 0 <= now - float(x.get("ts") or 0) < 120 for x in events)
    label = f"Συντονιστής ({provider})" + (" · αναπληρωτής" if role == "codex-deputy" else "")
    mdl = str(e.get("model") or "")
    card = ("🧭 Συντονιστής (Codex αναπληρωτής)" if role == "codex-deputy" else f"🧭 Συντονιστής ({provider})") \
        + " · μοντέλο " + (mdl or UNKNOWN)
    return {"card": card, "provider": provider, "role": role, "model": str(e.get("model") or ""),
            "effort": str(e.get("effort") or ""), "active": active, "agent_id": e.get("agent_id"),
            "label": label, "ts": float(e.get("ts") or 0),
            "task": str(e.get("task") or e.get("summary") or "")}
