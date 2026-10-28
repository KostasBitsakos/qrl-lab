"""«Γνώση» tab helpers: folder tree of md files from docs/index.json and the lookup-path diagram."""
import html
import json
import os

ENTRY_POINTS = ["docs/STATE.md", "docs/INDEX.md", "docs/DECISIONS.md", "docs/rules/README.md", "docs/EXPERIMENTS.md", "docs/PLAN.md"]

DOT = """digraph G { rankdir=LR; node [shape=box, style="rounded,filled", fillcolor="#eef3ff", fontname="Helvetica"];
task [label="Νέα εργασία", fillcolor="#fff3cd"]; state [label="docs/STATE.md\\n(πού βρισκόμαστε)"];
index [label="grep docs/INDEX.md\\n(λέξη-κλειδί)"]; file [label="το σχετικό αρχείο"];
dec [label="docs/DECISIONS.md\\n(αποφάσεις)"]; rules [label="docs/rules/\\n(κανόνες)"]; jr [label="docs/journal/\\n(ημερολόγιο)"];
db [label="labq.py show\\n(βάση του lab)"];
task -> state -> index; index -> file; index -> dec; index -> rules; index -> jr; index -> db; }"""


def load(root):
    with open(os.path.join(root, "docs", "index.json"), encoding="utf-8") as f:
        return json.load(f)


def build_tree(entries):
    """{folder: [entry,...]} sorted; root-level files under '.'; entry points first inside a folder."""
    tree = {}
    for e in entries:
        folder = os.path.dirname(e["path"]) or "."
        tree.setdefault(folder, []).append(e)
    for fl in tree.values():
        fl.sort(key=lambda e: (e["path"] not in ENTRY_POINTS, e["path"]))
    return dict(sorted(tree.items()))


def file_html(e):
    star = e["path"] in ENTRY_POINTS
    bg = "background:#fff3cd;border-left:4px solid #f0ad4e;" if star else ""
    name = html.escape(os.path.basename(e["path"]))
    desc = html.escape(e.get("description") or "")
    return (f'<div style="padding:3px 8px;margin:2px 0;{bg}"><b>{"⭐ " if star else "📄 "}{name}</b> '
            f'<span style="color:#666">({e.get("lines", "?")} γρ.)</span><br><span style="font-size:0.9em">{desc}</span></div>')
