"""Bounded, local content comparisons. Byte proxies are never billed token usage."""
import datetime as dt
import json
from pathlib import Path
import subprocess
import time

MAX_JSON = 65536
MAX_INDEX_BYTES = 1024 * 1024


def comparison(label, before, after, source, window):
    valid = (type(before) is int and type(after) is int
             and before > 0 and after >= 0)
    saved = before - after if valid else None
    return {"σύγκριση": label, "bytes πριν": before, "bytes μετά": after,
            "μείωση bytes": saved, "≈ tokens ανά ανάγνωση": round(saved / 4) if valid else None,
            "% του baseline bytes": round(100 * saved / before, 2) if valid else None,
            "είδος": "εκτίμηση tokens: bytes/4 · μετρημένα bytes", "πηγή": source,
            "παράθυρο": window}


def _size(path):
    try:
        if path.is_symlink():
            return None
        return path.stat().st_size
    except OSError:
        return None


def load_audit(root):
    path = Path(root) / ".lab/j137/audit-summary.json"
    fallback = {"status": "εκκρεμεί", "checked_at": "άγνωστο", "coverage": ["δεν έχει παραδοθεί έλεγχος"],
                "findings": [], "limits": ["Δεν τεκμηριώνεται καθολική απουσία διαρροής/σπατάλης."]}
    try:
        if path.is_symlink():
            return fallback
        with path.open("rb") as f:
            raw = f.read(MAX_JSON + 1)
        if len(raw) > MAX_JSON:
            return fallback
        data = json.loads(raw)
        if not isinstance(data, dict):
            return fallback
        for k in ("status", "checked_at"):
            if not isinstance(data.get(k), str):
                return fallback
        for k in ("coverage", "findings", "limits"):
            if not isinstance(data.get(k), list) or not all(isinstance(x, str) for x in data[k]):
                return fallback
        return {k: data[k] for k in fallback}
    except (OSError, ValueError):
        return fallback


def dispatcher_usage(root, hours=24):
    """MEASURED tokens of the dispatcher's own jobs (J228): per provider, the sums the Claude/Codex CLI reported in each
    task's final JSON (tasks.input_tokens/cached_tokens/output_tokens in .lab/dispatch.db). Not interactive sessions,
    not the account total. [] when the table is unreadable."""
    import sqlite3
    path = Path(root) / ".lab/dispatch.db"
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)).isoformat(timespec="seconds")
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute(
                "SELECT provider, COUNT(*) n, SUM(COALESCE(input_tokens,0)) inp, SUM(COALESCE(cached_tokens,0)) cached, SUM(COALESCE(cache_write_tokens,0)) cw,"
                " SUM(COALESCE(output_tokens,0)) out FROM tasks WHERE started >= ? AND input_tokens IS NOT NULL"
                " GROUP BY provider", (since,)).fetchall()
        finally:
            con.close()
        return [dict(r) for r in rows]
    except (sqlite3.Error, OSError):
        return []


def snapshot(root):
    started = time.monotonic()
    root = Path(root)
    rows = []
    stamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    for name in ("CLAUDE.md", "AGENTS.md"):
        backup = f".lab/{name}.bak-20261028"
        rows.append(comparison(name, _size(root / backup), _size(root / name),
                               f"{backup} → {name} (stat)", "snapshot 28/10 → " + stamp))
    # A defined search excerpt, not a claim of equivalent full-document information.
    index = root / "docs/INDEX.md"
    excerpt = None
    index_size = _size(index)
    if index_size is not None and index_size <= MAX_INDEX_BYTES:
        try:
            p = subprocess.run(["rg", "-i", "-m", "8", "--max-columns", "500",
                                "--max-columns-preview", "token", str(index)],
                               capture_output=True, timeout=2, check=False)
            if p.returncode == 0:
                excerpt = len(p.stdout)
        except (OSError, subprocess.TimeoutExpired):
            pass
    rows.append(comparison("Index: αναζήτηση «token», έως 8 γραμμές", index_size, excerpt,
                           "docs/INDEX.md · rg -i -m 8 --max-columns 500 --max-columns-preview token",
                           "ανά συγκεκριμένη αναζήτηση · " + stamp))
    return {"as_of": stamp, "rows": rows, "audit": load_audit(root), "used24": dispatcher_usage(root, 24),
            "runtime_ms": round((time.monotonic() - started) * 1000, 2)}


def summary_text(data):
    parts = []
    for r in data["rows"][:2]:
        n, pct = r["≈ tokens ανά ανάγνωση"], r["% του baseline bytes"]
        parts.append(f"{r['σύγκριση']}: ≈{n:,} tokens ({pct:.1f}% bytes)" if n is not None
                     else f"{r['σύγκριση']}: άγνωστο")
    return " · ".join(parts)


def card_html(data):
    """Compact sidebar card: one bar per comparison (smaller is better), honest caption, no LLM calls."""
    import html as _html
    rows = []
    for r in data["rows"][:2]:
        n, pct = r["≈ tokens ανά ανάγνωση"], r["% του baseline bytes"]
        name = _html.escape(str(r["σύγκριση"]))
        if n is None or pct is None:
            rows.append(f'<div class="tk-row"><span>{name}</span><b>άγνωστο</b></div>')
            continue
        saved = max(0.0, min(100.0, pct))
        rows.append(f'<div class="tk-row"><span>{name}</span><b>−{saved:.0f}%</b></div>'
                    f'<div class="tk-bar"><i style="width:{saved:.0f}%"></i></div>'
                    f'<div class="tk-sub">≈{n:,} tokens λιγότερα ανά ανάγνωση</div>')
    audit = _html.escape(str(data["audit"]["status"]))
    used = "".join(f'<div class="tk-sub" title="Άθροισμα όσων ανέφερε το CLI στο τέλος κάθε task (.lab/dispatch.db). '
                   f'Μόνο jobs του dispatcher, όχι διαδραστικά sessions.">{_html.escape(str(u["provider"]))} 24ω '
                   f'(μετρημένα): {u["n"]} tasks · input {u["inp"]:,} · cached {u["cached"]:,} · cache-write {u["cw"]:,} · output {u["out"]:,}</div>'
                   for u in data.get("used24", []))
    return ('<style>.tk-card{border:1px solid rgba(16,163,127,.35);border-radius:12px;padding:10px 12px;'
            'margin:6px 0 10px;background:rgba(16,163,127,.06);font-size:.85rem}'
            '.tk-card h4{margin:0 0 6px;font-size:.95rem}.tk-row{display:flex;justify-content:space-between}'
            '.tk-row b{color:#10a37f}.tk-bar{height:6px;border-radius:3px;background:rgba(128,128,128,.25);'
            'margin:3px 0 1px}.tk-bar i{display:block;height:100%;border-radius:3px;background:#10a37f}'
            '.tk-sub,.tk-foot{opacity:.7;font-size:.75rem;margin-bottom:4px}</style>'
            '<div class="tk-card"><h4>💡 Εξοικονόμηση tokens <small>(εκτίμηση)</small></h4>' + "".join(rows) + used
            + f'<div class="tk-foot">Μείωση μεγέθους οδηγιών έναντι 28/10 (εκτίμηση bytes/4). Συνολική πραγματική '
            f'εξοικονόμηση: άγνωστη · έλεγχος σπατάλης: {audit} · λεπτομέρειες στις Επεκτάσεις</div></div>')


def render(st, data, compact=False):
    st.markdown("**💡 Εξοικονόμηση tokens**")
    st.caption(summary_text(data))
    st.caption("Εκτίμηση bytes/4 ανά ανάγνωση έναντι backup 28/10. Συνολική πραγματική εξοικονόμηση και %: άγνωστα.")
    st.caption(f"Πηγή: .lab/{{CLAUDE,AGENTS}}.md.bak-20261028 → τρέχοντα αρχεία · {data['as_of']}")
    for u in data.get("used24", []):
        st.caption(f"**Μετρημένα** {u['provider']} 24ω (jobs dispatcher): {u['n']} tasks · input {u['inp']:,} · "
                   f"cached {u['cached']:,} · cache-write {u['cw']:,} · output {u['out']:,} — πηγή: tasks.* στο .lab/dispatch.db (CLI result JSON).")
    audit = data["audit"]
    st.caption(f"Έλεγχος σπατάλης: {audit['status']} · {audit['checked_at']}")
    if compact:
        st.caption("Αναλυτικές πηγές, παρονομαστές και κάλυψη: καρτέλα Επεκτάσεις.")
        return
    st.dataframe(data["rows"], hide_index=True, width="stretch")
    st.info("Οι συγκρίσεις δεν αθροίζονται και δεν είναι εξοικονόμηση λογαριασμού. Index: μέγεθος συγκεκριμένου αποσπάσματος έναντι ολόκληρου index, όχι ισοδύναμη πληροφορία. "
            "Επεκτάσεις: saved tokens/% άγνωστα χωρίς συγκρίσιμο baseline εργαλείων. Πραγματική χρήση και cached tokens δεν περιλαμβάνονται εδώ· στο OpenAI/Codex τα cached είναι μέρος των input, όχι λιγότερα συνολικά tokens. Τα πεδία Claude έχουν διαφορετική καταμέτρηση και δεν αθροίζονται εδώ.")
    st.caption("Πηγή: OpenAI prompt caching — https://developers.openai.com/api/docs/guides/prompt-caching")
    st.write("Κάλυψη ελέγχου: " + "; ".join(audit["coverage"]))
    for finding in audit["findings"]:
        st.write("• " + finding)
    for limit in audit["limits"]:
        st.caption("Όριο: " + limit)
    st.caption(f"Snapshot: {data['as_of']} · τοπικός χρόνος παραγωγής {data['runtime_ms']} ms. "
               "Cache 300s, 0 κλήσεις LLM από τον μηχανισμό. Μόνο metadata 5 αρχείων, index έως 1MiB/search έως 8 γραμμές, JSON audit έως 64KiB. "
               "Overhead tokens των οδηγιών/index στις πραγματικές κλήσεις: άγνωστο.")
