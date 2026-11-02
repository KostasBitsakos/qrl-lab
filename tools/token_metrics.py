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


# docs/kb_eval.md TOTAL row: 15 dev-set questions, best-case grep baseline 11392 tokens (bytes/4), KB output 4578.
KB_GREP_TOK_PER_Q = 11392 / 15


def kb_savings(root, hours=24 * 7):
    """Honest kb.py estimate from the measured query log (.lab/kb/queries.jsonl: output bytes per query/callers call).
    saved ≈ n × (grep baseline per question from the dev-set eval) − Σ measured KB output tokens (bytes/4).
    None when there is no log. An estimate, not billed usage; the eval is a small dev-set (grep wins on exact symbols)."""
    path = Path(root) / ".lab" / "kb" / "queries.jsonl"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-20000:]
    except OSError:
        return None
    since = time.time() - hours * 3600
    n = out = 0
    for ln in lines:
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if r.get("ts", 0) >= since and r.get("cmd") == "query" and type(r.get("out_bytes")) is int:
            n += 1
            out += r["out_bytes"] // 4
    return {"hours": hours, "n": n, "out_tok": out, "saved_tok": max(0, round(n * KB_GREP_TOK_PER_Q - out))}


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
            "kb": kb_savings(root),
            "runtime_ms": round((time.monotonic() - started) * 1000, 2)}


def summary_text(data):
    parts = []
    for r in data["rows"][:2]:
        n, pct = r["≈ tokens ανά ανάγνωση"], r["% του baseline bytes"]
        parts.append(f"{r['σύγκριση']}: ≈{n:,} tokens ({pct:.1f}% bytes)" if n is not None
                     else f"{r['σύγκριση']}: άγνωστο")
    return " · ".join(parts)


CARD_CSS = ('<style>.tk-card{border:1px solid rgba(16,163,127,.35);border-radius:12px;padding:10px 12px;'
            'margin:6px 0 10px;background:rgba(16,163,127,.06);font-size:.85rem}'
            '.tk-card h4{margin:0 0 6px;font-size:.95rem}.tk-row{display:flex;justify-content:space-between}'
            '.tk-row b{color:#10a37f}.tk-bar{height:6px;border-radius:3px;background:rgba(128,128,128,.25);'
            'margin:3px 0 1px}.tk-bar i{display:block;height:100%;border-radius:3px;background:#10a37f}'
            '.tk-sub,.tk-foot{opacity:.7;font-size:.75rem;margin-bottom:4px}</style>')


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
    kb = data.get("kb")
    if kb is None or not kb["n"]:
        rows.append('<div class="tk-row"><span>Βάση γνώσης (kb.py)</span><b>άγνωστο</b></div>'
                    '<div class="tk-sub">δεν υπάρχουν καταγεγραμμένα queries ακόμη (.lab/kb/queries.jsonl)</div>')
    else:
        rows.append(f'<div class="tk-row"><span>Βάση γνώσης (kb.py), {kb["hours"] // 24}ημ</span>'
                    f'<b>≈{kb["saved_tok"]:,} tokens</b></div>'
                    f'<div class="tk-sub" title="n × (grep baseline {KB_GREP_TOK_PER_Q:.0f} tokens/ερώτηση από το dev-set '
                    f'docs/kb_eval.md) − μετρημένο output του kb ({kb["out_tok"]:,} tokens, bytes/4). Μικρό dev-set, '
                    f'best-case grep· για exact-symbol το grep κερδίζει. ΔΕΝ μετρά πραγματικές ολόκληρες ανάγνωσεις αρχείων.">'
                    f'{kb["n"]} queries · ΕΚΤΙΜΗΣΗ έναντι grep (bytes/4)</div>')
    audit = _html.escape(str(data["audit"]["status"]))
    used = "".join(f'<div class="tk-sub" title="Άθροισμα όσων ανέφερε το CLI στο τέλος κάθε task (.lab/dispatch.db). '
                   f'Μόνο jobs του dispatcher, όχι διαδραστικά sessions.">{_html.escape(str(u["provider"]))} 24ω '
                   f'(μετρημένα): {u["n"]} tasks · input {u["inp"]:,} · cached {u["cached"]:,} · cache-write {u["cw"]:,} · output {u["out"]:,}</div>'
                   for u in data.get("used24", []))
    return (CARD_CSS +
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


# ---- J319 (M-20261102-026): sidebar «πόσα απομένουν και πού πάνε» -------------------------------------------------
WINDOW_HOURS = {"5ω": 5, "7ημ": 168}
MIN_PCT_FOR_ESTIMATE = 5.0  # below this the ratio tokens/pct is too noisy to show


def usage_by_kind(root, hours, provider):
    """MEASURED dispatcher tokens (input + cache-write + output as the CLI reported them; cached-read field not added) per task kind and model in the last
    `hours`. None when unreadable. Same source and limits as dispatcher_usage."""
    import sqlite3
    path = Path(root) / ".lab/dispatch.db"
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)).isoformat(timespec="seconds")
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute(
                "SELECT COALESCE(kind,'?') kind, COALESCE(model,'?') model, COUNT(*) n,"
                " SUM(COALESCE(input_tokens,0)+COALESCE(cache_write_tokens,0)+COALESCE(output_tokens,0)) tok"
                " FROM tasks WHERE started >= ? AND provider = ? AND input_tokens IS NOT NULL"
                " GROUP BY kind, model ORDER BY tok DESC", (since, provider)).fetchall()
        finally:
            con.close()
        return [dict(r) for r in rows]
    except (sqlite3.Error, OSError):
        return None


def remaining_lower_bound(measured_tokens, used_pct):
    """ROUGH estimate of tokens left in a window, or None: T*(1-p)/p. NOT a guaranteed bound (provider quotas weight
    model/cache/reasoning differently and the wall-clock window may differ from the provider's). T = measured dispatcher
    tokens, p = used share; dispatcher-only T under-counts total use, so the true figure is likely larger. None if p is unknown,
    < MIN_PCT_FOR_ESTIMATE or T is 0."""
    if used_pct is None or not measured_tokens or used_pct < MIN_PCT_FOR_ESTIMATE:
        return None
    p = min(100.0, float(used_pct)) / 100.0
    return int(measured_tokens * (1 - p) / p)


def _fmt(n):
    return f"{n/1e6:.1f}M" if n >= 1e6 else (f"{n/1e3:.0f}k" if n >= 1e3 else str(n))


def with_token_estimates(root, provider, windows):
    """Copies of the usage windows with w["tok"] = rough tokens left (see remaining_lower_bound) when derivable."""
    out = []
    for w in windows or []:
        w = dict(w)
        hrs = WINDOW_HOURS.get(w.get("label"))
        if hrs and w.get("pct") is not None:
            tot = sum(k["tok"] or 0 for k in (usage_by_kind(root, hrs, provider) or []))
            lb = remaining_lower_bound(tot, w["pct"])
            if lb is not None:
                w["tok"] = _fmt(lb)
        out.append(w)
    return out


def sidebar_bars_html(root, provider, windows, name):
    """Per provider: for each window a lower-bound estimate of tokens left (basis stated, «άγνωστο» when not derivable)
    and small bars of where measured tokens went (by task kind·model) in the longest known window."""
    import html as _html
    out = []
    longest = None
    for w in windows or []:
        hrs = WINDOW_HOURS.get(w.get("label"))
        if not hrs:
            continue
        longest = max(longest or 0, hrs)
        kinds = usage_by_kind(root, hrs, provider)
        tot = sum(k["tok"] or 0 for k in (kinds or []))
        lb = remaining_lower_bound(tot, w.get("pct"))
        txt = f"~{_fmt(lb)} tokens (πολύ χονδρική εκτίμηση)" if lb is not None else "άγνωστο"
        out.append(f'<div class="tk-sub">{_html.escape(str(w["label"]))}: απομένουν {txt}</div>')
    if not out:
        return ""
    kinds = usage_by_kind(root, longest, provider)
    unreadable = kinds is None
    kinds = kinds or []
    tot = sum(k["tok"] or 0 for k in kinds) or 0
    bars = []
    for k in kinds[:5]:
        share = 100.0 * (k["tok"] or 0) / tot if tot else 0
        lab = _html.escape(f'{k["kind"]} · {k["model"]}')
        bars.append(f'<div class="tk-row"><span>{lab}</span><b>{share:.0f}%</b></div>'
                    f'<div class="tk-bar"><i style="width:{share:.0f}%"></i></div>')
    where = ("".join(bars) if bars else '<div class="tk-sub">' + ("η βάση δεν διαβάζεται" if unreadable else "καμία μετρημένη χρήση") + '</div>')
    return ('<div class="tk-card"><h4>📊 ' + _html.escape(name) + ' <small>(εκτίμηση)</small></h4>' + "".join(out)
            + f'<div class="tk-sub">Πού πάνε ({longest}ω, μετρημένα tokens jobs dispatcher):</div>' + where
            + '<div class="tk-foot" title="Εκτίμηση T·(1−p)/p: T = μετρημένα tokens (input+cache-write+output) των jobs του '
              'dispatcher στο παράθυρο, p = ποσοστό χρήσης που αναφέρει ο πάροχος. Δεν περιλαμβάνει διαδραστικά sessions, '
              'ενώ ο πάροχος ζυγίζει διαφορετικά μοντέλα/cache/reasoning· όχι εγγυημένο.">Χονδρική εκτίμηση T·(1−p)/p από μετρημένα tokens dispatcher (παράθυρο = τελευταίες ώρες, όχι reset) · '
              'ο πάροχος δίνει μόνο %, όχι απόλυτα tokens</div></div>')
