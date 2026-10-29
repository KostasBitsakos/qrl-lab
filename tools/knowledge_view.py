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


# ---------------------------------------------------------------- zoomable icicle (M-20261029-003 item 4)
# Roles drive colour + legend. "index" = files/folders the coordinator reads to find things fast.
INDEX_FILES = {
    "docs/STATE.md": "Αρχίζει από εδώ κάθε εργασία: πού βρισκόμαστε, τι τρέχει, τι περιμένει.",
    "docs/INDEX.md": "Κατάλογος όλων των md (1 γραμμή/αρχείο). Ο συντονιστής κάνει grep λέξης εδώ αντί να ανοίγει αρχεία.",
    "docs/DECISIONS.md": "Αποδεκτές αποφάσεις με ημερομηνία/id: ελέγχεται πριν από κάθε πρόταση.",
    "docs/EXPERIMENTS.md": "Μητρώο κάθε batch πειραμάτων: πού τρέχει, πού είναι τα αποτελέσματα, κατάσταση.",
    "docs/rules/README.md": "Ευρετήριο κανόνων: ποιο αρχείο κανόνων ισχύει για τι.",
    "docs/PLAN.md": "Πηγή αλήθειας του σχεδίου (§1, §2, §6).",
    "docs/journal": "Ημερολόγιο: μία γραμμή ανά εργασία, γράφεται αυτόματα από τον dispatcher.",
}
ROLE_COLOR = {"index": "#f0ad4e", "folder": "#9db4d6", "file": "#e8eef7", "match": "#d9534f", "root": "#ffffff"}
LEGEND = [("index", "⭐ ευρετήριο / σημείο εισόδου (εδώ ψάχνει πρώτα ο συντονιστής)"),
          ("folder", "📁 φάκελος (πάτησέ τον για zoom)"), ("file", "📄 αρχείο md"),
          ("match", "🔎 αποτέλεσμα αναζήτησης")]
ROOT_ID = "qrl-lab"


def role(path):
    return "index" if path in INDEX_FILES else "file"


def _wrap(text, width=60):
    out, line = [], ""
    for w in text.split():
        if len(line) + len(w) > width:
            out.append(line)
            line = ""
        line = (line + " " + w).strip()
    return "<br>".join(out + [line])


def matches(entries, query):
    """Paths whose path/title/description contain the query (case-insensitive)."""
    q = (query or "").strip().lower()
    if not q:
        return set()
    return {e["path"] for e in entries
            if q in " ".join([e["path"], e.get("title") or "", e.get("description") or ""]).lower()}


def icicle_data(entries, query=""):
    """Flat ids/parents/labels/values/colors/hover for every folder and md file. Folder value = files under it."""
    hits = matches(entries, query)
    nodes = {ROOT_ID: {"parent": "", "label": "qrl-lab", "kind": "root", "n": 0, "hit": False}}
    for e in sorted(entries, key=lambda e: e["path"]):
        parts = e["path"].split("/")
        parent = ROOT_ID
        for i in range(len(parts) - 1):
            fid = "/".join(parts[:i + 1])
            nodes.setdefault(fid, {"parent": parent, "label": parts[i] + "/", "kind": "folder", "n": 0, "hit": False})
            parent = fid
        nodes[e["path"]] = {"parent": parent, "label": parts[-1], "kind": role(e["path"]), "n": 1,
                            "hit": e["path"] in hits, "entry": e}
        p = parent
        while p:  # counts and hit propagation up to the root
            nodes[p]["n"] += 1
            nodes[p]["hit"] = nodes[p]["hit"] or e["path"] in hits
            p = nodes[p]["parent"]
    ids, parents, labels, values, colors, hover = [], [], [], [], [], []
    for nid, n in nodes.items():
        kind = "index" if nid in INDEX_FILES else n["kind"]
        star = "⭐ " if kind == "index" else ""
        ids.append(nid)
        parents.append(n["parent"])
        labels.append(star + n["label"])
        values.append(n["n"])
        colors.append(ROLE_COLOR["match"] if n["hit"] and kind != "root" else ROLE_COLOR[kind])
        if "entry" in n:
            e = n["entry"]
            txt = (f"<b>{html.escape(e['path'])}</b> ({e.get('lines', '?')} γρ.)<br>"
                   f"{_wrap(html.escape(e.get('title') or ''))}<br><i>{_wrap(html.escape(e.get('description') or ''))}</i>")
        else:
            txt = f"<b>{html.escape(nid)}</b><br>{n['n']} αρχεία md"
        if nid in INDEX_FILES:
            txt += "<br>⭐ " + _wrap(html.escape(INDEX_FILES[nid]))
        hover.append(txt)
    return {"ids": ids, "parents": parents, "labels": labels, "values": values, "colors": colors,
            "hover": hover, "hits": sorted(hits)}


def folders(entries):
    """Every folder id (for the "zoom to branch" picker)."""
    out = set()
    for e in entries:
        parts = e["path"].split("/")
        out.update("/".join(parts[:i + 1]) for i in range(len(parts) - 1))
    return sorted(out)


def figure(entries, query="", level=None, depth=3, height=720):
    """Plotly icicle: click a box to zoom into it, breadcrumb (pathbar) on top to go back."""
    import plotly.graph_objects as go
    d = icicle_data(entries, query)
    fig = go.Figure(go.Icicle(
        ids=d["ids"], parents=d["parents"], labels=d["labels"], values=d["values"], branchvalues="total",
        marker=dict(colors=d["colors"], line=dict(color="#555", width=0.5)),
        hovertext=d["hover"], hoverinfo="text", textinfo="label", insidetextfont=dict(size=14),
        tiling=dict(orientation="h"), pathbar=dict(visible=True, side="top", textfont=dict(size=14)),
        maxdepth=depth, level=level if level in d["ids"] else ROOT_ID, root=dict(color="#ffffff")))
    fig.update_layout(margin=dict(t=30, l=0, r=0, b=0), height=height, uniformtext=dict(minsize=11, mode="hide"))
    return fig


def detail_md(e):
    """Side panel (markdown) for one file."""
    s = f"**{e['path']}** · {e.get('lines', '?')} γραμμές\n\n**{e.get('title') or ''}**\n\n{e.get('description') or ''}"
    if e["path"] in INDEX_FILES:
        s += f"\n\n⭐ *Ευρετήριο:* {INDEX_FILES[e['path']]}"
    return s


# ---------------------------------------------------------------- thematic tree (M-20261029-118: mobile zoomable tree)
# Folders alone read as chaos (10 worktree copies, .lab/ next to docs/). The tree groups files by MEANING first,
# then by folder inside each theme. First matching rule wins; (prefix, exact) — exact=True means whole path.
CATEGORIES = [  # (key, label, emoji, one-line help, color, rules)
    ("start", "Ξεκίνα εδώ", "⭐", "Τα ευρετήρια: από εδώ ξεκινά κάθε εργασία και κάθε αναζήτηση.", "#f0ad4e",
     [(p, True) for p in INDEX_FILES if p.endswith(".md")] + [("AGENTS.md", True), ("CLAUDE.md", True),
                                                               ("README.md", True)]),
    ("plan", "Σχέδιο & σχεδιασμός", "🧭", "Τι θέλουμε να αποδείξουμε και πώς στήνονται οι κύκλοι.", "#5b8def",
     [("docs/cycle2_", False), ("docs/hpa_spec.md", True), ("docs/loop_playbook.md", True),
      ("docs/COORDINATION.md", True), ("docs/dashboard_requests", False)]),
    ("exp", "Πειράματα & αποτελέσματα", "🧪", "Μητρώα, κύκλοι tuning, αποτελέσματα test.", "#2fa66a",
     [("docs/tuning_experiments.md", True), (".lab/tuning/", False), ("reports/", False), ("export/results/", False)]),
    ("paper", "Paper & βιβλιογραφία", "📝", "Σημειώσεις paper, σχετική δουλειά, συνέδρια, expert pack.", "#a05bd6",
     [("paper/", False), ("docs/paper_notes.md", True), ("docs/related_work", False), ("docs/VENUES.md", True),
      ("docs/venue_", False), ("docs/papers/", False), ("docs/expert/", False)]),
    ("rules", "Κανόνες & ρόλοι", "📏", "Κανόνες του lab, ρόλοι των agents, μνήμη και prompts.", "#d9534f",
     [("docs/rules/", False), ("prompts/", False), (".claude/", False), ("docs/claude-memory/", False)]),
    ("talk", "Συμβούλια & παραδόσεις", "🤝", "Συζητήσεις Claude–Codex και παραδόσεις βάρδιας.", "#e07b39",
     [(".lab/council/", False), (".lab/codex-handoff/", False), ("docs/handoffs/", False),
      ("docs/deputy_handoff.md", True)]),
    ("guide", "Οδηγοί & tutorials", "🎓", "Εξηγήσεις για σένα: tutorials, κινητό, ανάκαμψη, εργαλεία.", "#17a2b8",
     [("docs/tutorial", False), ("docs/guides/", False), ("docs/MOBILE.md", True), ("docs/RECOVERY.md", True),
      ("docs/INVENTORY.md", True), ("docs/token_", False), ("docs/extensions_eval", False),
      ("docs/for_other_projects.md", True)]),
    ("log", "Ημερολόγιο & αρχείο", "📓", "Τι έγινε πότε· παλιές εκδόσεις.", "#8a8f98",
     [("docs/journal/", False), ("docs/archive/", False), ("CHANGELOG.md", True)]),
    ("export", "GitHub export", "📦", "Το επιμελημένο αντίγραφο για το GitHub.", "#6c757d", [("export/", False)]),
    ("code", "Κώδικας (worktrees)", "💻", "Τα md μέσα στα worktrees του κώδικα· κάθε worktree χωριστά.", "#495057",
     [("code", False)]),
    ("other", "Λοιπά", "📎", "Ό,τι δεν ταιριάζει αλλού.", "#adb5bd", [("", False)]),
]


def category(path):
    for key, *_rest, rules in CATEGORIES:
        for pref, exact in rules:
            if (path == pref) if exact else path.startswith(pref):
                return key
    return "other"


def _strip_prefix(path, key):
    """Folder path shown INSIDE a theme: drop the part the theme already says (docs/, .lab/, .claude/)."""
    for pref in ("docs/", ".lab/", ".claude/", "export/"):
        if path.startswith(pref) and key != "code" and (pref != "export/" or key == "export"):
            return path[len(pref):]
    return path


def tree_data(entries, query=""):
    """Nested {name, kind, children|entry fields} for the HTML tree: root → theme → sub-folders → files.
    Every node carries n (md files under it) and hit (search match in it or below)."""
    hits = matches(entries, query)
    meta = {c[0]: c for c in CATEGORIES}
    root = {"id": ROOT_ID, "name": "Γνώση του lab", "kind": "root", "children": [], "n": 0, "hit": False}
    themes = {}
    for e in sorted(entries, key=lambda e: (e["path"] not in INDEX_FILES, e["path"])):
        key = category(e["path"])
        if key not in themes:
            _k, label, emoji, help_, color, _r = meta[key]
            themes[key] = {"id": "cat:" + key, "name": label, "emoji": emoji, "help": help_, "color": color,
                           "kind": "theme", "children": [], "n": 0, "hit": False}
        node = themes[key]
        chain = [root, node]
        rel = _strip_prefix(e["path"], key) if key != "start" else os.path.basename(e["path"])
        parts = rel.split("/")
        for i, part in enumerate(parts[:-1]):
            fid = f"{node['id']}/{part}"
            sub = next((c for c in node["children"] if c["id"] == fid), None)
            if sub is None:
                sub = {"id": fid, "name": part + "/", "kind": "folder", "children": [], "n": 0, "hit": False}
                node["children"].append(sub)
            node = sub
            chain.append(node)
        node["children"].append({
            "id": e["path"], "name": parts[-1], "kind": "index" if e["path"] in INDEX_FILES else "file",
            "path": e["path"], "title": e.get("title") or "", "desc": e.get("description") or "",
            "lines": e.get("lines"), "note": INDEX_FILES.get(e["path"], ""), "n": 1, "hit": e["path"] in hits})
        for c in chain:
            c["n"] += 1
            c["hit"] = c["hit"] or e["path"] in hits
    order = [c[0] for c in CATEGORIES]
    root["children"] = [themes[k] for k in order if k in themes]
    return root
