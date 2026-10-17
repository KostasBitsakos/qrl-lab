#!/usr/bin/env python3
"""Loader for docs/changes.json (tab «Ιστορικό αλλαγών»). No LLM. Validates the schema, newest first."""
import json
import os

ROOT = os.environ.get("QRL_LAB_DIR") or os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TYPES = ("απόφαση", "simulator", "πείραμα", "αποτέλεσμα", "baseline")
BADGE = {"απόφαση": "🟦", "simulator": "🟪", "πείραμα": "🟧", "αποτέλεσμα": "🟩", "baseline": "⬜"}
STR_KEYS = ("date", "type", "title_el", "summary_el", "details_el")


class ChangesError(ValueError):
    pass


def validate(items):
    if not isinstance(items, list):
        raise ChangesError("changes.json must be a list")
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            raise ChangesError(f"item {i}: not an object")
        for k in STR_KEYS:
            if not isinstance(it.get(k), str) or not it[k].strip():
                raise ChangesError(f"item {i}: missing or empty '{k}'")
        if len(it["date"]) != 10 or it["date"][4] != "-" or it["date"][7] != "-" or not it["date"].replace("-", "").isdigit():
            raise ChangesError(f"item {i}: date must be YYYY-MM-DD")
        if it["type"] not in TYPES:
            raise ChangesError(f"item {i}: unknown type '{it['type']}'")
        refs = it.get("refs")
        if not isinstance(refs, list) or not refs or not all(isinstance(r, str) and r for r in refs):
            raise ChangesError(f"item {i}: 'refs' must be a non-empty list of strings")
    return items


def load(path=None):
    """Valid items, newest first (stable within the same date: file order, which is already newest first)."""
    path = path or os.path.join(ROOT, "docs", "changes.json")
    with open(path, encoding="utf-8") as f:
        items = validate(json.load(f))
    return sorted(items, key=lambda it: it["date"], reverse=True)


def label(it):
    return f"{it['date']} · {BADGE[it['type']]} {it['type']} · {it['title_el']}"
