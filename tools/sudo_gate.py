#!/usr/bin/env python3
"""Claude Code PreToolUse hook (matcher Bash): gate every `sudo` behind a researcher grant.

No `sudo` in the command  -> no output, Claude Code's normal permission rules apply.
`sudo` and an active grant that covers every sudo'd program -> "allow", logged to .lab/sudo_audit.jsonl.
Anything else with `sudo` -> "ask" (the old behaviour: the researcher approves in the terminal).

The grant is written only by tools/sudo_grant.py (researcher-only) to a root-owned file, so an agent
cannot create one without sudo, which this hook itself gates. Never fails closed into "allow".
"""
import json
import os
import re
import shlex
import sys
import time

GRANT = "/etc/qrl-lab/sudo_grant.json"
# Programs that would let a grant escalate to anything (shells, editors, file writers, interpreters).
NEVER = {"sh", "bash", "zsh", "dash", "su", "sudo", "tee", "cp", "mv", "dd", "rm", "chmod", "chown",
         "install", "visudo", "vi", "vim", "nano", "env", "python", "python3", "perl", "ruby", "node",
         "passwd", "usermod", "useradd", "chpasswd", "find", "xargs", "awk", "sed", "ln", "mount",
         "crontab", "at", "nsenter", "docker", "script", "less", "more", "man", "git"}
SUDO_FLAGS_WITH_ARG = {"-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-U"}


HEREDOC = re.compile(r"<<-?\s*(['\"])(\w+)\1[^\n]*\n.*?\n\s*\2\s*(?=\n|$)", re.S)
RUNS_STDIN = re.compile(r"\b(sh|bash|zsh|dash|python3?|perl|ruby|node|ssh|sudo|eval|source|xargs)\b")


def strip_literal_heredocs(cmd):
    """Drop the bodies of quoted heredocs (<<'EOF') that feed plain data, e.g. `cat > f <<'EOF'`.

    A quoted heredoc is never expanded, so `sudo` inside it only runs if the receiving command is a shell
    or interpreter; those are kept so the gate still sees them.
    """
    def repl(m):
        line_start = cmd.rfind("\n", 0, m.start()) + 1
        head = cmd[line_start:m.start()]
        return m.group(0) if RUNS_STDIN.search(head) else "<<HEREDOC\n"
    return HEREDOC.sub(repl, cmd)


def sudo_programs(cmd):
    """Return the programs run under sudo, or None if the command is too complex to judge."""
    if re.search(r"\$\(|`|\beval\b|<\(|>\(", cmd) and "sudo" in cmd:
        return None
    progs = []
    for seg in re.split(r"&&|\|\||[;|&\n()]", cmd):
        try:
            toks = shlex.split(seg)
        except ValueError:
            return None
        for i, t in enumerate(toks):
            if os.path.basename(t) != "sudo":
                continue
            j = i + 1
            while j < len(toks) and toks[j].startswith("-"):
                j += 2 if toks[j] in SUDO_FLAGS_WITH_ARG else 1
            if j >= len(toks):
                return None
            progs.append(os.path.basename(toks[j]))
    # `sudo` appears but not as a command word we could parse (e.g. inside a quoted bash -c)
    if not progs:
        return None
    return progs


def load_grant(now):
    try:
        with open(GRANT, encoding="utf-8") as f:
            g = json.load(f)
        st = os.stat(GRANT)
    except (OSError, ValueError):
        return None
    if st.st_uid != 0 or st.st_mode & 0o022:  # must be root-owned and not group/world-writable
        return None
    if float(g.get("expires", 0)) <= now:
        return None
    return g


def decide(decision, reason):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                             "permissionDecision": decision,
                                             "permissionDecisionReason": reason}}))


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    if data.get("tool_name") != "Bash":
        return 0
    cmd = strip_literal_heredocs(str((data.get("tool_input") or {}).get("command", "")))
    if not re.search(r"\bsudo\b", cmd):
        return 0
    now = time.time()
    g = load_grant(now)
    if not g:
        decide("ask", "sudo needs the researcher: no active grant (python3 tools/sudo_grant.py open ...)")
        return 0
    progs = sudo_programs(cmd)
    allowed = set(g.get("programs", [])) - NEVER
    if progs is None or GRANT in cmd or not set(progs) <= allowed:
        decide("ask", f"sudo outside grant {g.get('task')} (allowed: {', '.join(sorted(allowed))})")
        return 0
    root = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or "."
    try:
        with open(os.path.join(root, ".lab", "sudo_audit.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": round(now, 3), "task": g.get("task"), "programs": progs,
                                "session_id": data.get("session_id"), "agent_type": data.get("agent_type"),
                                "command": cmd[:500]}, ensure_ascii=False) + "\n")
    except OSError:
        pass
    left = int((float(g["expires"]) - now) / 60)
    decide("allow", f"sudo grant {g.get('task')} ({left} min left)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
