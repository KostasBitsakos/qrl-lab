"""Downloadable tutorial library; no Streamlit dependency for catalog discovery."""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Tutorial:
    path: Path
    title: str
    date: str
    description: str


def discover(root: str | Path) -> list[Tutorial]:
    folder = Path(root) / "docs" / "tutorials"
    if not folder.is_dir():
        return []
    try:
        catalog = json.loads((folder / "catalog.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        catalog = {}
    if not isinstance(catalog, dict):
        catalog = {}
    result = []
    for path in folder.glob("*.pdf"):
        # Only direct, regular PDFs inside the library; never follow a symlink.
        if path.is_symlink() or not path.is_file():
            continue
        try:
            with path.open("rb") as stream:
                if stream.read(5) != b"%PDF-":
                    continue
            fallback_date = dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc).date().isoformat()
        except OSError:
            continue
        meta = catalog.get(path.name, {})
        if not isinstance(meta, dict):
            meta = {}
        title = meta.get("title") or path.stem.replace("_", " ")
        date = meta.get("date", fallback_date)
        try:
            date = dt.date.fromisoformat(date).isoformat()
        except (ValueError, TypeError):
            date = fallback_date
        description = meta.get("description", "")
        result.append(Tutorial(path, str(title), date, str(description)))
    return sorted(result, key=lambda item: (item.date, item.path.name), reverse=True)


def render(root: str | Path) -> None:
    import streamlit as st

    st.header("📚 Tutorials")
    st.caption("Σύντομοι οδηγοί για να κατανοείς την έρευνα, με παραδείγματα και εξηγημένα μαθηματικά.")
    items = discover(root)
    if not items:
        st.info("Εδώ θα βρίσκεις τους οδηγούς και θα κατεβάζεις τα PDF τους.")
        return
    for item in items:
        with st.container(border=True):
            st.subheader(item.title)
            st.caption(item.date)
            if item.description:
                st.write(item.description)
            try:
                data = item.path.read_bytes()
            except OSError:
                st.warning("Το PDF δεν είναι προσωρινά διαθέσιμο.")
                continue
            st.download_button("⬇ Λήψη PDF", data=data, file_name=item.path.name,
                               mime="application/pdf", key=f"tutorial_{item.path.name}",
                               width="stretch")
