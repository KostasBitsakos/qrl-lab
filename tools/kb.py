#!/usr/bin/env python3
"""QRL-Lab knowledge base: cheap retrieval over code + docs (J314, M-20261102-020).

    kb.py refresh [--full]        stage corpus, rebuild code graph (graphify, AST only) + doc/symbol index
    kb.py query "<question>"      compact answer (<~1.5k tokens) with file:line pointers
    kb.py callers <symbol>        who calls / what does <symbol> call (graph edges), with file:line
    kb.py stats                   sizes, counts, freshness
    kb.py scan                    secret scan of the staged corpus + built artifacts

No LLM, no network, no API keys. Plain CLI so Claude and Codex use it identically.
Output lives in .lab/kb/ (gitignored via .lab/). Paths printed are REAL paths (~ = /home/ubuntu).
"""
import argparse, ast, fcntl, json, os, re, shutil, sqlite3, subprocess, sys, time
from pathlib import Path

HOME = Path.home()
LAB = HOME / "qrl-lab"
KB = LAB / ".lab" / "kb"
CORPUS = KB / "corpus"
DB = KB / "kb.db"
GRAPH = KB / "graphify-out" / "graph.json"
GRAPHIFY = HOME / ".venvs" / "graphify" / "bin" / "graphify"
MAX_FILE = 400_000          # bytes; larger files are skipped (data dumps)
DOC_EXT = {".md", ".txt", ".tex", ".yaml", ".yml", ".sh", ".rst"}
CODE_EXT = {".py"}
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "graphify-out", "checkpoints", "results",
             "runs", "outputs", "output", "logs", "uploads", ".pytest_cache", "site-packages", "smoke"}
SKIP_NAMES = re.compile(r"(^\.env|id_rsa|id_ed25519|\.pem$|\.key$|auth\.json|kube.?config|credentials?\.|secrets?\.(json|ya?ml|txt)$|"
                        r"^tokens?\.(json|txt)$)", re.I)
SECRET_RE = re.compile(
    r"(-----BEGIN [A-Z ]*PRIVATE KEY-----|\bsk-[A-Za-z0-9_-]{20,}|\bghp_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}|"
    r"\bAKIA[0-9A-Z]{16}\b|\bxox[bap]-[A-Za-z0-9-]{10,}|"
    r"(?i:api[_-]?key|passwd|password|secret|token|bearer)['\"]?\s*[:=]\s*['\"]?[A-Za-z0-9/+_\-.]{16,})")

# tag -> (real root, relative dirs/files to include; None = whole tree, extra skipped dir names)
SOURCES = {
    "qrl": (LAB, ["tools", "dashboard", "tests", "prompts", "docs", "paper", "deploy", "hc", "reports",
                  "AGENTS.md", "CLAUDE.md", "CHANGELOG.md", "SETUP.md"], {"archive_big"}),
    "lab": (LAB / ".lab", None, {"corpus", "kb", "runs", "export", "figs", "usage", "outbox", "tuning_runs", "c224"}),
    "spiky": (LAB / "code-poisson-spiky", None, set()),     # current cycle-2 code (Stage 1b)
    "tuning": (LAB / "code-tuning", None, set()),           # cycle-1 final tuned code
    "simulations": (HOME / "simulations", None, set()),     # researcher's original code (read-only)
    "redis": (HOME / "redis", None, set()),
    "k8s": (HOME / "k8s", None, set()),
    "promgraf": (HOME / "prometheus-grafana", None, set()),
}
LAB_SKIP_FILES = {"events.jsonl"}
GENERATED = {"docs/INDEX.md", "docs/index.json"}
ROOT_OF = {t: str(v[0]) for t, v in SOURCES.items()}


def real_path(rel):
    tag, _, sub = rel.partition("/")
    root = ROOT_OF.get(tag)
    return f"{root}/{sub}".replace(str(HOME), "~") if root else rel


# ------------------------------------------------------------------ staging
def _walk(root, includes, extra_skip):
    starts = [root] if includes is None else [root / i for i in includes]
    for s in starts:
        if s.is_file():
            yield s
            continue
        if not s.is_dir():
            continue
        for dp, dns, fns in os.walk(s):
            dns[:] = [d for d in dns if d not in SKIP_DIRS and d not in extra_skip and not d.startswith(".git")
                      and not (root == LAB and Path(dp) == root and d.startswith("code"))]
            for fn in fns:
                yield Path(dp) / fn


def stage(full=False):
    """Copy wanted text files to CORPUS/<tag>/<rel>; returns (copied, removed, skipped_secret)."""
    CORPUS.mkdir(parents=True, exist_ok=True)
    want, copied, secret = set(), 0, []
    for tag, (root, inc, skip) in SOURCES.items():
        for f in _walk(root, inc, skip):
            ext = f.suffix.lower()
            if ext not in DOC_EXT and ext not in CODE_EXT:
                continue
            try:
                if f.is_symlink():                      # never follow links (could point at a credential file)
                    continue
                st = f.stat()
            except OSError:
                continue
            rel = f.relative_to(root).as_posix()
            if st.st_size > MAX_FILE or st.st_size == 0 or SKIP_NAMES.search(f.name):
                continue
            if tag == "qrl" and rel in GENERATED:
                continue
            if tag == "lab" and (f.name in LAB_SKIP_FILES or ext not in {".md", ".txt"}):
                continue
            dst = CORPUS / tag / rel
            key = f"{tag}/{rel}"
            try:
                raw = f.read_bytes()
            except OSError:
                continue
            if SECRET_RE.search(raw.decode("utf8", "replace")):
                secret.append(key)
                continue
            want.add(key)
            if not full and dst.exists() and dst.read_bytes() == raw:   # content compare, not size/mtime
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(raw)
            copied += 1
    removed = 0
    for p in list(CORPUS.rglob("*")):
        if p.is_file() and p.relative_to(CORPUS).as_posix() not in want:
            if "graphify-out" in p.parts:
                continue
            p.unlink()
            removed += 1
    return copied, removed, secret, len(want)


# ------------------------------------------------------------------ index
SCHEMA = """
DROP TABLE IF EXISTS chunks; DROP TABLE IF EXISTS fts; DROP TABLE IF EXISTS meta;
CREATE TABLE chunks(id INTEGER PRIMARY KEY, file TEXT, line INTEGER, end_line INTEGER, kind TEXT, title TEXT, body TEXT);
CREATE VIRTUAL TABLE fts USING fts5(title, body, content='chunks', content_rowid='id',
                                    tokenize="unicode61 remove_diacritics 2 tokenchars '_'");
CREATE TABLE meta(k TEXT PRIMARY KEY, v TEXT);
"""
IDRE = re.compile(r"\b(?:[MRJC]-\d{8}-\d{3}|[JC]\d{2,4}|R-\d{8}-\d{3})\b")


def md_chunks(text):
    lines = text.splitlines()
    heads = [(i, len(m.group(1)), m.group(2).strip()) for i, l in enumerate(lines)
             if (m := re.match(r"^(#{1,4})\s+(.*)", l))]
    if not heads:
        heads = [(0, 1, "")]
    elif heads[0][0] > 0:
        heads.insert(0, (0, 1, ""))
    for k, (i, _, title) in enumerate(heads):
        j = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
        for a in range(i, j, 60):                       # split very long sections
            b = min(j, a + 60)
            body = "\n".join(lines[a:b]).strip()
            if body:
                yield a + 1, b, title, body


def py_chunks(text):
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return
    lines = text.splitlines()
    mod_doc = ast.get_docstring(tree)
    if mod_doc:
        yield 1, 1, "<module>", mod_doc[:600], "module"
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(n) or ""
            sig = lines[n.lineno - 1].strip()
            # comment lines directly above + body identifiers give searchable context without the whole body
            above = []
            k = n.lineno - 2
            while k >= 0 and lines[k].strip().startswith("#"):
                above.append(lines[k].strip("# ").strip())
                k -= 1
            names = sorted({x.id for x in ast.walk(n) if isinstance(x, ast.Name)} |
                           {x.attr for x in ast.walk(n) if isinstance(x, ast.Attribute)})
            consts = [c.value for c in ast.walk(n) if isinstance(c, ast.Constant) and isinstance(c.value, str)
                      and 3 < len(c.value) < 60 and "\n" not in c.value][:20]
            body = "\n".join([sig, doc[:500], *reversed(above), " ".join(names[:60]), " | ".join(consts)])
            yield n.lineno, getattr(n, "end_lineno", n.lineno), n.name, body, \
                "class" if isinstance(n, ast.ClassDef) else "def"


def build_index():
    KB.mkdir(parents=True, exist_ok=True)
    tmp = DB.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    con.executescript(SCHEMA)
    rows = []
    for p in sorted(CORPUS.rglob("*")):
        if not p.is_file() or "graphify-out" in p.parts:
            continue
        rel = p.relative_to(CORPUS).as_posix()
        try:
            text = p.read_text(errors="replace")
        except OSError:
            continue
        if p.suffix == ".py":
            for a, b, name, body, kind in py_chunks(text):
                rows.append((rel, a, b, kind, name, body))
        else:
            for a, b, title, body in md_chunks(text):
                rows.append((rel, a, b, "doc", title or Path(rel).name, body))
    con.executemany("INSERT INTO chunks(file,line,end_line,kind,title,body) VALUES (?,?,?,?,?,?)", rows)
    con.execute("INSERT INTO fts(rowid,title,body) SELECT id,title,body FROM chunks")
    con.execute("INSERT INTO meta VALUES('built',?)", (time.strftime("%Y-%m-%d %H:%M:%SZ", time.gmtime()),))
    con.commit()
    n = con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    con.close()
    os.replace(tmp, DB)                                   # atomic publish
    return n


def run_graphify(full):
    env = dict(os.environ, GRAPHIFY_BACKEND="none", GRAPHIFY_QUERY_LOG_DISABLE="1")
    cmd = [str(GRAPHIFY), "extract", str(CORPUS), "--code-only", "--out", str(KB), "--no-cluster"]
    if full:
        cmd.append("--force")
    r = subprocess.run(["taskset", "-c", "4-7"] + cmd, env=env, capture_output=True, text=True, timeout=900)
    return r.returncode, (r.stdout + r.stderr)[-600:]


def cmd_refresh(a):
    KB.mkdir(parents=True, exist_ok=True)
    lock = open(KB / "refresh.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("another refresh is running")
        return 3
    t0 = time.time()
    copied, removed, secret, total = stage(a.full)
    rc, tail = run_graphify(a.full)
    n = build_index()
    con = sqlite3.connect(DB)
    con.execute("INSERT OR REPLACE INTO meta VALUES('graph_rc',?)", (str(rc),))
    con.commit(); con.close()
    print(f"staged {total} files (+{copied} copied, -{removed} removed, {len(secret)} skipped for secret patterns); "
          f"graphify rc={rc}; index {n} chunks; {time.time()-t0:.1f}s")
    if secret:
        print("secret-skipped:", ", ".join(secret[:10]))
    if rc != 0:
        print(tail)
    return rc


# ------------------------------------------------------------------ query
STOP = set("the a an of to in on for and or is are was were be by with what which who how where when why does do did "
           "this that it its from as at we our i you me my not can should would about into than then there their "
           "τι ποιο ποια ποιος πως που πού ποτε και ή το τα του της των στο στη στα ένα μια είναι έχει έχουμε "
           "να με σε από για ο η οι την τον τους κώστα κωστα πάρις παρις πείτε ποιες".split())


def tokens(q):
    out = []
    for w in re.findall(r"[\w]+", q, re.U):
        wl = w.lower()
        if wl in STOP or len(wl) < 2:
            continue
        out.append(wl)
        if "_" in wl:
            out.extend(x for x in wl.split("_") if len(x) > 2 and x not in STOP)
    return list(dict.fromkeys(out))


def fts_query(toks):
    return " OR ".join('"%s"' % t.replace('"', "") for t in toks)


def _graph():
    if not GRAPH.exists():
        return None, {}
    g = json.loads(GRAPH.read_text())
    nodes = {n["id"]: n for n in g.get("nodes", [])}
    return g, nodes


def _loc(n):
    f = n.get("source_file") or ""
    loc = n.get("source_location") or ""
    m = re.search(r"(\d+)", str(loc))
    try:
        f = Path(f).resolve().relative_to(CORPUS).as_posix()
    except Exception:
        f = re.sub(r"^.*?/kb/corpus/", "", f)
    return f, (int(m.group(1)) if m else 0)


def graph_neighbors(name, limit=6):
    g, nodes = _graph()
    if not g:
        return [], []
    ids = [i for i, n in nodes.items() if re.sub(r"[()]", "", n.get("label", "")).split(".")[-1] == name]
    callers, callees = [], []
    for e in g.get("edges", g.get("links", [])):
        rel = e.get("relation", "")
        s, t = e.get("source"), e.get("target")
        if rel not in ("calls", "imports", "imports_from", "uses", "inherits", "references"):
            continue
        if t in ids and s in nodes:
            f, fl = _loc(nodes[s])
            m = re.search(r"(\d+)", str(e.get("source_location") or ""))
            callers.append(f"{nodes[s].get('label','?')} [{rel}] {real_path(f)}:{m.group(1) if m else fl}")
        if s in ids and t in nodes:
            f, l = _loc(nodes[t])
            callees.append(f"{nodes[t].get('label','?')} [{rel}] {real_path(f)}:{l}")
    return list(dict.fromkeys(callers))[:limit], list(dict.fromkeys(callees))[:limit]


def snippet(body, toks, width=170):
    low = body.lower()
    pos = min([low.find(t) for t in toks if low.find(t) >= 0] or [0])
    s = body[max(0, pos - 40): pos + width].replace("\n", " ")
    return re.sub(r"\s+", " ", s).strip()


def cmd_query(a):
    if not DB.exists():
        print("kb not built: run `python3 tools/kb.py refresh`")
        return 2
    q = " ".join(a.question)
    con = sqlite3.connect(DB)
    b = con.execute("SELECT v FROM meta WHERE k='built'").fetchone()
    if b and time.time() - time.mktime(time.strptime(b[0][:19], "%Y-%m-%d %H:%M:%S")) + time.timezone > 86400:
        print("WARNING: index older than 24h — run `kb.py refresh` if freshness matters")
    ids = IDRE.findall(q)
    toks = tokens(q)
    hits = []
    if toks:
        sql = ("SELECT c.id,c.file,c.line,c.kind,c.title,c.body,bm25(fts,8.0,1.0) s FROM fts "
               "JOIN chunks c ON c.id=fts.rowid WHERE fts MATCH ? ORDER BY s LIMIT 60")
        hits = con.execute(sql, (fts_query(toks),)).fetchall()
    exact = []
    for t in [x for x in toks if "_" in x or len(x) >= 8]:   # exact symbol / title match beats bm25
        for r in con.execute("SELECT id,file,line,kind,title,body,-200 FROM chunks WHERE kind IN ('def','class') "
                             "AND lower(title)=? LIMIT 6", (t,)):
            exact.append(r)
    hits = exact + hits
    for i in ids:                                         # exact-id lookup (message/request/job ids)
        phrase = '"' + " ".join(re.findall(r"[A-Za-z]+|\d+", i)) + '"'
        for r in con.execute("SELECT c.id,c.file,c.line,c.kind,c.title,c.body,-99 FROM fts JOIN chunks c ON c.id=fts.rowid "
                             "WHERE fts MATCH ? LIMIT 4", (phrase,)):
            hits.insert(0, r)
    # prefer current code and canonical docs over duplicated cycle-1 copies / scratch notes
    def prior(h):
        f = h[1]
        p = h[6]
        if f.startswith("tuning/"):
            p += 3
        if f.startswith("lab/"):
            p += 1.5
        if f.startswith("qrl/docs/") and "archive" not in f:
            p -= 3.5
        if f.startswith("qrl/docs/archive"):
            p += 2
        return p
    hits.sort(key=prior)
    out, seen, used_files, budget = [], set(), {}, a.chars
    docs = [h for h in hits if h[3] == "doc"]
    code = [h for h in hits if h[3] != "doc"]
    def emit(h):
        _, f, l, kind, title, body, _s = h
        key = (f, l)
        dk = (title, kind) if kind != "doc" else None
        if key in seen or used_files.get(f, 0) >= 2 or (dk and dk in seen):
            return
        seen.add(key)
        if dk:
            seen.add(dk)
        used_files[f] = used_files.get(f, 0) + 1
        if kind != "doc":
            out.append(f"{real_path(f)}:{l} [{kind}] {body.splitlines()[0][:110]}")
        else:
            ls = body.splitlines()
            best = max(range(len(ls)), key=lambda i: sum(t in ls[i].lower() for t in toks)) if ls else 0
            out.append(f"{real_path(f)}:{l + best} [doc] {title[:50]} — {snippet(ls[best] if ls else body, toks)}")
    def fill(lst, n):
        c0 = len(out)
        for h in lst[: n + 6]:
            if len(out) - c0 >= n:
                break
            emit(h)
    if exact:
        a.code, a.docs = min(a.code, 3), min(a.docs, 3)
    codey = bool(exact) or re.search(r"\b(def|class|function|method|caller|calls?|defined|implementation|where is)\b", q, re.I)
    if ids or not codey:
        fill(docs, a.docs); fill(code, a.code)
    else:
        fill(code, a.code); fill(docs, a.docs)
    # graph neighbours for the best symbol hits
    extra, done = [], set()
    for h in code[:6]:
        if h[3] in ("def", "class") and h[4].lower() in toks and (len(h[4]) >= 7 or "_" in h[4]) \
                and h[4] not in done:
            done.add(h[4])
            cl, _ce = graph_neighbors(h[4])
            if cl:
                extra.append(f"callers of {h[4]}: " + "; ".join(cl[:4]))
    text = "\n".join(out + extra)
    if not out:
        text = "no hits (try other keywords, or grep). tokens: " + " ".join(toks)
    if len(text) > budget:
        text = text[:budget].rsplit("\n", 1)[0] + "\n…(truncated)"
    print(text)
    return 0


def cmd_callers(a):
    cl, ce = graph_neighbors(a.symbol, limit=15)
    print(f"callers/importers of {a.symbol}:\n  " + "\n  ".join(cl or ["(none in graph)"]))
    print(f"depends on:\n  " + "\n  ".join(ce or ["(none in graph)"]))
    return 0


def cmd_stats(a):
    if not DB.exists():
        print("kb not built")
        return 2
    con = sqlite3.connect(DB)
    kinds = dict(con.execute("SELECT kind,COUNT(*) FROM chunks GROUP BY kind"))
    tags = dict(con.execute("SELECT substr(file,1,instr(file,'/')-1),COUNT(DISTINCT file) FROM chunks GROUP BY 1"))
    built = con.execute("SELECT v FROM meta WHERE k='built'").fetchone()[0]
    grc = (con.execute("SELECT v FROM meta WHERE k='graph_rc'").fetchone() or ["?"])[0]
    if grc != "0":
        built += f" (graph rc={grc}: callers may be stale)"
    g, nodes = _graph()
    size = sum(p.stat().st_size for p in KB.rglob("*") if p.is_file() and "corpus" not in p.parts)
    print(f"built {built}; chunks {kinds}; files per source {tags}")
    print(f"graph nodes {len(nodes)} edges {len((g or {}).get('edges', (g or {}).get('links', [])))}; "
          f"index+graph {size/1e6:.1f} MB (corpus copy {sum(p.stat().st_size for p in CORPUS.rglob('*') if p.is_file() and 'graphify-out' not in p.parts)/1e6:.1f} MB)")
    return 0


def cmd_scan(a):
    bad = []
    for p in list(KB.rglob("*")):
        if p.is_file() and p.suffix in {".json", ".db", ".md", ".py", ".txt", ".yaml", ".yml", ".sh", ".tex", ".html"}:
            if "graphify-out/cache" in p.as_posix():
                pass
            try:
                data = p.read_bytes().decode("utf8", "replace")
            except OSError:
                continue
            m = SECRET_RE.search(data)
            if m:
                bad.append((p.relative_to(KB).as_posix(), "pattern"))
    names = [p.relative_to(KB).as_posix() for p in KB.rglob("*") if p.is_file() and SKIP_NAMES.search(p.name)]
    print(f"secret-pattern hits: {len(bad)}; sensitive-looking filenames: {len(names)}")
    for b in bad[:15]:
        print("  HIT", b)
    for n in names[:15]:
        print("  NAME", n)
    return 1 if bad or names else 0


def logged(a):
    """Run a retrieval command and append its measured output size (bytes only, never the text) to
    .lab/kb/queries.jsonl: the dashboard's honest «tokens saved» estimate counts these (J322)."""
    import contextlib, io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = a.f(a)
    out = buf.getvalue()
    sys.stdout.write(out)
    try:
        with open(KB / "queries.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": int(time.time()), "cmd": a.cmd, "out_bytes": len(out.encode()),
                                "actor": os.environ.get("QRL_COORDINATOR", "")}) + "\n")
    except OSError:
        pass
    return rc


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("refresh"); r.add_argument("--full", action="store_true"); r.set_defaults(f=cmd_refresh)
    q = sp.add_parser("query"); q.add_argument("question", nargs="+")
    q.add_argument("--code", type=int, default=5); q.add_argument("--docs", type=int, default=5)
    q.add_argument("--chars", type=int, default=5200); q.set_defaults(f=cmd_query)
    c = sp.add_parser("callers"); c.add_argument("symbol"); c.set_defaults(f=cmd_callers)
    sp.add_parser("stats").set_defaults(f=cmd_stats)
    sp.add_parser("scan").set_defaults(f=cmd_scan)
    a = ap.parse_args()
    if a.cmd in ("query", "callers"):
        sys.exit(logged(a))
    sys.exit(a.f(a))


if __name__ == "__main__":
    main()
