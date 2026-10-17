"""Read-only detection of what is installed for the agents (plugins, skills, agents, hooks, Codex CLI).
Only names and descriptions are returned, never file contents beyond that."""
import glob
import json
import os
import re
import subprocess

GREEK = {
    "ask-user": "Ο συντονιστής ρωτά τον ερευνητή μέσω της καρτέλας Αποφάσεις αντί να μαντεύει.",
    "council": "Δομημένη συζήτηση Claude–Codex (τυφλές προτάσεις, αντίκρουση, κάρτα απόφασης) για αποφάσεις που αλλάζουν την έρευνα.",
    "inbox": "Χειρισμός μηνυμάτων του ερευνητή από το dashboard: ορατή απάντηση και τελική κατάσταση σε κάθε νήμα.",
    "codex@openai-codex": "Επίσημο plugin της OpenAI: επιτρέπει στον συντονιστή να καλεί το Codex ως συν-ερευνητή/reviewer.",
    "Explore": "Γρήγορη αναζήτηση σε κώδικα, logs και φακέλους (Claude Haiku).",
    "engineer": "Υλοποίηση και δοκιμές κώδικα μέσα στο ~/qrl-lab, μαζί με το dashboard.",
    "runner": "Εκτελεί εγκεκριμένα runs μέσω του launcher και παρακολουθεί την πορεία τους.",
    "scholar": "Βιβλιογραφία, παραπομπές και επιλογή συνεδρίων.",
    "writer": "Συγγραφή και επιμέλεια του κειμένου του paper.",
}
HOOK_GREEK = "Αυτόματη ενέργεια του Claude Code στο συμβάν «{}»."


def _frontmatter(path):
    try:
        with open(path, encoding="utf-8") as f:
            head = f.read(4000)
    except OSError:
        return {}
    m = re.match(r"---\s*\n(.*?)\n---", head, re.S)
    out = {}
    if m:
        for line in m.group(1).splitlines():
            k, sep, v = line.partition(":")
            if sep and not line.startswith((" ", "\t")):
                out[k.strip()] = v.strip()
    return out


def _short(s, n=160):
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _md_dir_items(pattern, kind, home):
    items = []
    for p in sorted(glob.glob(pattern)):
        fm = _frontmatter(p)
        name = fm.get("name") or os.path.basename(os.path.dirname(p) if p.endswith("SKILL.md") else p[:-3])
        items.append({"kind": kind, "name": name, "desc": GREEK.get(name) or _short(fm.get("description")) or "—",
                      "source": p.replace(home, "~", 1)})
    return items


def detect(root, home=None, codex_cmd="codex"):
    home = home or os.path.expanduser("~")
    items = []
    try:
        with open(os.path.join(home, ".claude/plugins/installed_plugins.json"), encoding="utf-8") as f:
            d = json.load(f)
        pl = d.get("plugins", d)
        for name in (pl if isinstance(pl, dict) else []):
            items.append({"kind": "plugin", "name": name, "desc": GREEK.get(name, "Plugin του Claude Code."),
                          "source": "~/.claude/plugins/installed_plugins.json"})
    except (OSError, ValueError):
        pass
    items += _md_dir_items(os.path.join(root, ".claude/skills/*/SKILL.md"), "skill", home)
    items += _md_dir_items(os.path.join(home, ".claude/skills/*/SKILL.md"), "skill", home)
    items += _md_dir_items(os.path.join(root, ".claude/agents/*.md"), "agent", home)
    try:
        with open(os.path.join(root, ".claude/settings.json"), encoding="utf-8") as f:
            hooks = json.load(f).get("hooks", {})
        for ev in (hooks if isinstance(hooks, dict) else []):
            items.append({"kind": "hook", "name": ev, "desc": HOOK_GREEK.format(ev),
                          "source": "~/qrl-lab/.claude/settings.json"})
    except (OSError, ValueError):
        pass
    try:
        r = subprocess.run([codex_cmd, "--version"], capture_output=True, text=True, timeout=3)
        v = (r.stdout or "").strip().splitlines()
        if r.returncode == 0 and v:
            items.append({"kind": "cli", "name": "Codex CLI " + _short(v[0], 40),
                          "desc": "Γραμμή εντολών της OpenAI που τρέχει πίσω από το plugin του Codex.",
                          "source": "codex --version"})
    except (OSError, subprocess.SubprocessError):
        pass
    return items


ICONS = {"plugin": "🔌", "skill": "🧠", "agent": "🤖", "hook": "🪝", "cli": "🧰"}
LABELS = {"plugin": "plugin", "skill": "skill", "agent": "agent", "hook": "hook", "cli": "CLI"}


def card_html(it):
    from html import escape as e
    return ("<div style='border:1px solid #e3e6ea;border-radius:10px;padding:10px 12px;margin-bottom:10px;background:#fafbfc'>"
            f"<div style='font-weight:600'>{ICONS[it['kind']]} {e(it['name'])} "
            f"<span style='font-size:0.7em;background:#e8eef7;color:#2a5a9a;border-radius:8px;padding:1px 7px;margin-left:4px'>{LABELS[it['kind']]}</span></div>"
            f"<div style='font-size:0.88em;margin:4px 0'>{e(it['desc'])}</div>"
            f"<div style='font-size:0.72em;color:#8a9099'>{e(it['source'])}</div></div>")
