#!/usr/bin/env python3
"""Loader for the dashboard tab «🧩 Επεκτάσεις». Entries come ONLY from .lab/extensions_catalog.json.

File format: {"categories": {"<category>": [{"name","kind","provider","description","url","cost"}, ...]}}
or a plain {"<category>": [...]}. kind: skill|plugin|MCP|feature; provider: Claude|ChatGPT; cost: free text that must
say whether it is free/included. Nothing here is a built-in suggestion; a missing/broken file -> empty catalog.
"""
import json
import os

KIT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CATEGORIES = ["Ποιότητα κώδικα", "Εξοικονόμηση tokens", "Συγγραφή / papers", "Έρευνα / βιβλιογραφία", "Testing", "Ops"]
FIELDS = ("name", "kind", "provider", "description", "url", "cost")
KINDS = ("skill", "plugin", "MCP", "feature")
PROVIDERS = ("Claude", "ChatGPT")
MAX_PER_CATEGORY = 4
EXT_TAG = "EXT-SEARCH"
EXT_THREAD_TITLE = "Επεκτάσεις: αναζήτηση skills/plugins"


def catalog_path(root=None):
    return os.path.join(root or os.environ.get("QRL_LAB_DIR") or KIT, ".lab", "extensions_catalog.json")


def _valid(e):
    return (isinstance(e, dict) and all(isinstance(e.get(k), str) and e.get(k).strip() for k in FIELDS)
            and str(e["url"]).startswith(("http://", "https://")))


def load(root=None):
    """-> {category: [entry, ...]} (at most 4 valid entries each; invalid ones skipped); {} when nothing usable."""
    try:
        with open(catalog_path(root), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    if isinstance(data, dict) and isinstance(data.get("categories"), dict):
        data = data["categories"]
    if not isinstance(data, dict):
        return {}
    out = {}
    for cat, items in data.items():
        if isinstance(items, list):
            good = [{k: e[k].strip() for k in FIELDS} for e in items if _valid(e)][:MAX_PER_CATEGORY]
            if good:
                out[str(cat)] = good
    return out


def search_message(text):
    """Body of the dashboard message that triggers the coordinator's search agent."""
    text = (text or "").strip()
    if not text:
        raise ValueError("empty")
    # The coordinator's handling rule lives in the inbox procedure, not in the researcher's visible text.
    return f"[{EXT_TAG}] Ζητώ skill/επέκταση: {text}"


def strip_instruction(body):
    """Hide the coordinator instruction that older EXT-SEARCH messages carried in their body."""
    i = (body or "").find("\n\n(Συντονιστή: στείλε search agent")
    return body if i < 0 else body[:i]


def add_request(entry):
    """-> (title, body) for `labq ask --kind approval --scope external`. Never installs anything."""
    e = {k: str(entry.get(k, "")) for k in FIELDS}
    title = f"Προσθήκη επέκτασης: {e['name']} ({e['kind']}, {e['provider']})"
    body = (f"Ο Κώστας ζήτησε να προστεθεί η επέκταση «{e['name']}».\n\n- Είδος: {e['kind']}\n- Πάροχος: {e['provider']}\n"
            f"- Περιγραφή: {e['description']}\n- Πηγή: {e['url']}\n- Κόστος: {e['cost']}\n\n"
            "Η έγκριση δεν εγκαθιστά τίποτα από μόνη της: ο συντονιστής θα προτείνει συγκεκριμένα βήματα εγκατάστασης.")
    return title, body
