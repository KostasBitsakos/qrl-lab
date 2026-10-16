"""Paper build and edit logic for the dashboard Paper tab (pure functions, no Streamlit).

- compile(): latexmk in a subprocess with a timeout, output under paper/build/<venue>/.
- safe_path()/save_file(): edits only inside <root>/paper (realpath check, extension whitelist, file_view deny list),
  committed with `git -C <root> commit` (only that file).
- todo_counts()/tbd_count()/claims_rows(): status of the manuscript.
"""
import datetime as dt
import os
import re
import subprocess
import time

import file_view

VENUES = ("ieee", "acm", "lncs")
EDIT_EXT = (".tex", ".bib", ".md")
MISSING_CLASS_HINT = {
    "llncs.cls": "Springer llncs.cls is not in Debian/Ubuntu TeX Live; download Springer's LNCS author kit "
                 "(llncs.cls, splncs04.bst) and place both in paper/ (researcher action).",
}


class PaperError(Exception):
    pass


def paper_dir(root):
    return os.path.join(root, "paper")


def pdf_path(root, venue):
    return os.path.join(paper_dir(root), "build", venue, f"main-{venue}.pdf")


def compile(root, venue, timeout=120):
    """Run latexmk. Returns dict ok, returncode, seconds, pdf, log_tail (last 40 lines), hint."""
    if venue not in VENUES:
        raise PaperError(f"unknown venue {venue!r}")
    out = os.path.join("build", venue)
    cmd = ["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error", f"-outdir={out}", f"main-{venue}.tex"]
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=paper_dir(root), capture_output=True, text=True, timeout=timeout)
        rc, text = p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired as e:
        rc = -1
        text = f"TIMEOUT after {timeout} s\n" + ((e.stdout or b"").decode("utf-8", "replace")
                                                if isinstance(e.stdout, bytes) else (e.stdout or ""))
    except FileNotFoundError:
        rc, text = -2, "latexmk not found"
    logf = os.path.join(paper_dir(root), out, f"main-{venue}.log")
    if rc != 0 and os.path.exists(logf):  # the TeX log has the real error; the latexmk output is only a summary
        with open(logf, errors="replace") as f:
            text = f.read()
    pdf = pdf_path(root, venue)
    ok = rc == 0 and os.path.exists(pdf)
    hint = next((h for k, h in MISSING_CLASS_HINT.items() if f"`{k}' not found" in text), "")
    return {"ok": ok, "returncode": rc, "seconds": round(time.time() - t0, 1), "pdf": pdf if ok else None,
            "log_tail": "\n".join(text.splitlines()[-40:]), "hint": hint}


def build_time(root, venue):
    p = pdf_path(root, venue)
    return dt.datetime.fromtimestamp(os.path.getmtime(p)).isoformat(timespec="seconds") if os.path.exists(p) else None


def list_files(root):
    """Relative paths (to paper/) of editable/viewable files, excluding build/."""
    base = paper_dir(root)
    out = []
    for d, dirs, files in os.walk(base):
        dirs[:] = [x for x in dirs if x != "build" and not x.startswith(".")]
        for f in files:
            if f.lower().endswith(EDIT_EXT):
                out.append(os.path.relpath(os.path.join(d, f), base))
    return sorted(out)


def safe_path(root, rel):
    """Real path of a file under <root>/paper, or PaperError."""
    if not rel or "\x00" in rel or os.path.isabs(rel):
        raise PaperError("outside paper/")
    base = os.path.realpath(paper_dir(root))
    real = os.path.realpath(os.path.join(base, rel))
    if not real.startswith(base + os.sep):
        raise PaperError("outside paper/")
    if os.path.relpath(real, base).split(os.sep)[0] == "build":
        raise PaperError("build/ is not editable")
    if file_view.is_denied(os.path.join(base, rel)) or file_view.is_denied(real):
        raise PaperError("denied")
    if not real.lower().endswith(EDIT_EXT):
        raise PaperError("extension not allowed")
    return real


def read_file(root, rel):
    with open(safe_path(root, rel), encoding="utf-8", errors="replace") as f:
        return f.read()


def save_file(root, rel, text, commit=True):
    """Write and commit one file. Returns the commit hash (or None if commit=False / nothing changed)."""
    real = safe_path(root, rel)
    if not os.path.isfile(real):
        raise PaperError("missing file")  # editing only; no new files from the dashboard
    with open(real, "w", encoding="utf-8") as f:
        f.write(text)
    if not commit:
        return None
    relroot = os.path.relpath(real, os.path.realpath(root))
    subprocess.run(["git", "-C", root, "add", "--", relroot], check=True, capture_output=True, text=True)
    r = subprocess.run(["git", "-C", root, "commit", "-m", f"paper: edit {rel} from dashboard", "--", relroot],
                       capture_output=True, text=True)
    if r.returncode != 0:
        if "nothing to commit" in (r.stdout + r.stderr) or "no changes added" in (r.stdout + r.stderr):
            return None
        raise PaperError("git commit failed: " + (r.stderr or r.stdout).strip()[-300:])
    h = subprocess.run(["git", "-C", root, "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    return h.stdout.strip()


def _strip_comments(s):
    return "\n".join(re.sub(r"(?<!\\)%.*", "", l) for l in s.splitlines())


def count_todos(text):
    """Number of \\todo markers outside LaTeX comments."""
    return len(re.findall(r"\\todo\b", _strip_comments(text)))


def todo_counts(root):
    rows = []
    d = os.path.join(paper_dir(root), "sections")
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            if f.endswith(".tex"):
                with open(os.path.join(d, f), encoding="utf-8", errors="replace") as fh:
                    t = fh.read()
                rows.append({"section": f, "words": len(_strip_comments(t).split()), "todo": count_todos(t)})
    return rows


def tbd_count(root):
    p = os.path.join(paper_dir(root), "generated", "results.tex")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8", errors="replace") as f:
        return sum(1 for l in f if l.lstrip().startswith("\\newcommand") and "[TBD]" in l)


def claims_rows(root):
    p = os.path.join(paper_dir(root), "claims.md")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip().startswith("|")]
    if len(lines) < 2:
        return []
    cells = lambda l: [c.strip() for c in l.strip("|").split("|")]
    head = cells(lines[0])
    return [dict(zip(head, cells(l))) for l in lines[2:]]
