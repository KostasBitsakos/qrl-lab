#!/usr/bin/env python3
"""Save researcher uploads under docs/uploads/<message id>/ safely, and format the attachments block for a message.
Files are only ever written and offered for download; nothing here executes them."""
import os
import re
import unicodedata

MAX_BYTES = 200 * 1024 * 1024  # per file; keep equal to server.maxUploadSize (MB) in .streamlit/config.toml
_BAD = re.compile(r"[^\w.\-]", re.UNICODE)  # \w keeps letters (incl. Greek), digits, underscore


class UploadError(Exception):
    pass


def sanitize_filename(name):
    name = (name or "").replace("\\", "/").split("/")[-1]  # basename only
    name = "".join(ch for ch in name if unicodedata.category(ch)[0] != "C")
    name = _BAD.sub("_", name).lstrip(".")  # no hidden files, no '..' prefix
    name = name.replace("..", "_")
    return name[:150] or "file"


def _free_path(d, name):
    stem, ext = os.path.splitext(name)
    p, i = os.path.join(d, name), 0
    while os.path.exists(p):
        i += 1
        p = os.path.join(d, f"{stem}-{i}{ext}")
    return p


def save_uploads(files, root, subdir):
    """files: iterable of (filename, bytes) saved under docs/uploads/<subdir>/ (subdir = the message id).
    Returns list of (relative_path, size). Never overwrites."""
    base = os.path.realpath(os.path.join(root, "docs", "uploads"))
    day = sanitize_filename(subdir)
    out = []
    for fname, data in files:
        if len(data) > MAX_BYTES:
            raise UploadError(f"Το αρχείο {fname} ξεπερνά το όριο {MAX_BYTES // 2**20} MB.")
        d = os.path.join(base, day)
        os.makedirs(d, exist_ok=True)
        # exclusive create closes the exists/open race
        name = sanitize_filename(fname)
        while True:
            p = os.path.realpath(_free_path(d, name))
            if os.path.dirname(p) != os.path.realpath(d) or not p.startswith(base + os.sep):
                raise UploadError("Μη έγκυρο όνομα αρχείου.")
            try:
                with open(p, "xb") as f:
                    f.write(data)
                break
            except FileExistsError:
                continue
        out.append((os.path.relpath(p, root), len(data)))
    return out


def _size(n):
    return f"{n / 2**20:.1f} MB" if n >= 2**20 else f"{max(1, round(n / 1024))} KB"


def attachments_block(saved):
    if not saved:
        return ""
    return "Συνημμένα:\n" + "\n".join(f"- {p} ({_size(n)})" for p, n in saved)


def body_with_attachments(text, saved):
    parts = [(text or "").strip(), attachments_block(saved)]
    return "\n\n".join(p for p in parts if p)


def attachment_paths(body):
    """Paths listed in the `Συνημμένα:` block of a message body (as written by attachments_block)."""
    if "Συνημμένα:" not in (body or ""):
        return []
    tail = body.split("Συνημμένα:", 1)[1]
    out = []
    for line in tail.splitlines():
        m = re.match(r"^- (docs/uploads/\S.*?) \(\d+(?:\.\d+)? (?:KB|MB)\)$", line.strip())
        if m:
            out.append(m.group(1))
    return out
