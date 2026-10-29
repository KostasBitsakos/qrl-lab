"""Presentation only: address/signature on researcher-visible dispatcher posts."""
import re


def researcher_text(body, provider=None):
    text = body.strip()
    if not re.match(r"^Κώστα\b", text):
        text = "Κώστα,\n\n" + text
    if not re.search(r"^—\s*Πάρις(?:\s*\(Codex\))?\s*$", text, re.MULTILINE):
        text += "\n\n— Πάρις" + (" (Codex)" if provider == "codex" else "")
    return text
