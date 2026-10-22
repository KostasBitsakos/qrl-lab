#!/usr/bin/env python3
"""Deterministic structuring of a researcher message into Markdown (M-20261022-015). No LLM, no I/O in the core.

Output (to_markdown):
  1. the ORIGINAL text verbatim in a fenced block (source of truth);
  2. «Σημεία»: P1..Pn, each an exact slice of the original (no paraphrase, no accent changes);
  3. detected questions (sentences/lines ending with ; ? or the Greek question mark);
  4. mentioned ids and paths (M-…, R-…, ~/…, /home/…, file names).

Splitting, most explicit first; when unsure we do NOT split:
  - lines: every non-empty line is a point, except indented continuation lines of a list item;
  - inline numbering inside a line: «1. … 2. …», «1) … 2) …», «α) … β) …», or bare «1 … 2 …», only as a sequence
    starting at 1/α at the start of the line or after «:», increasing by one; bare numbers are used only when every
    next number occurs exactly once as a standalone token (otherwise ambiguous -> no split);
  - «επίσης» at the start of a sentence (after . ! ; ? or a comma) and «Και» starting a sentence after . ! ; ?,
    only when both sides are at least MIN_SIDE characters long. A mid-sentence «και» is never split.
Property: "".join(points) contains every non-whitespace character of the original, in order.

CLI: python3 tools/msg_structure.py [file]   (stdin when no file; --json prints the structure)
"""
import json
import re
import sys

MIN_SIDE = 40
TOGGLE_KEY = "msfmt_"       # st.session_state key prefix of the per-composer toggle
CHOICE_KEY = "_msfmt_choice_"
PENDING_KEY = "_msfmt_pending_"

_GREEK_LETTERS = "αβγδεζηθικλμνξοπρστυφχψω"
_BULLET = re.compile(r"^\s*(?:[-*•·–]|\d{1,2}[.)]|[α-ωa-z][.)]|\(\d{1,2}\)|\([α-ωa-z]\))\s+")
_Q_END = ("?", ";", ";")
_ID = re.compile(r"\b[A-Z]{1,3}-\d{8}-\d{2,4}[a-z]?\b")
_PATH = re.compile(r"(?:~|/home)/[^\s`'\"«»()<>,;]+")
_FILE = re.compile(r"(?<![\w/~.-])[\w.-]+(?:/[\w.-]+)*\.(?:py|md|json|jsonl|ya?ml|txt|csv|tex|sh|ipynb|toml|pdf|png|svg|"
                   r"zip|db|log|cfg|ini)\b")


def _lines(text):
    """[(start, end)] spans of the non-empty lines (without the newline)."""
    out, pos = [], 0
    for ln in text.split("\n"):
        if ln.strip():
            out.append((pos, pos + len(ln)))
        pos += len(ln) + 1
    return out


def _line_blocks(text):
    """Group line spans into blocks: a list item keeps its indented continuation lines (no blank line between)."""
    blocks = []
    prev_end = None
    for s, e in _lines(text):
        line = text[s:e]
        cont = (blocks and prev_end is not None and "\n" not in text[prev_end + 1:s]  # directly the next line
                and line[:1] in (" ", "\t") and not _BULLET.match(line)
                and _BULLET.match(text[blocks[-1][0]:blocks[-1][1]]))
        if cont:
            blocks[-1] = (blocks[-1][0], e)
        else:
            blocks.append((s, e))
        prev_end = e
    return blocks


def _seq_marks(seg, pat, labels, bare=False):
    """Offsets where an inline sequence labels[0], labels[1], … starts, or [] when there is no clear sequence."""
    cands = [(m.start(1), m.group(2)) for m in re.finditer(pat, seg)]
    if not cands:
        return []
    first = [c for c in cands if c[1] == labels[0]]
    if not first:
        return []
    s0 = first[0][0]
    if seg[:s0].strip() and not seg[:s0].rstrip().endswith(":"):
        return []
    marks, k = [s0], 1
    while k < len(labels):
        nxt = [c for c in cands if c[1] == labels[k] and c[0] > marks[-1]]
        if not nxt:
            break
        if bare and len(nxt) > 1:
            return []  # ambiguous ("2 seeds … 2 εδω"): do not split
        marks.append(nxt[0][0])
        k += 1
    return marks if len(marks) >= 2 else []


def _inline_numbering(seg):
    nums = [str(i) for i in range(1, 21)]
    for pat, labels, bare in (
            (r"(?:^|(?<=\s))((\d{1,2})[.)])(?=\s)", nums, False),
            (r"(?:^|(?<=\s))(\((\d{1,2})\))(?=\s)", nums, False),
            (r"(?:^|(?<=\s))(([α-ω])\))(?=\s)", list(_GREEK_LETTERS), False),
            (r"(?:^|(?<=\s))((\d{1,2}))(?=\s+[^\W\d_])", nums, True)):
        marks = _seq_marks(seg, pat, labels, bare)
        if marks:
            return marks
    return []


_ALSO = re.compile(r"(?:(?<=[.!;?;])|(?<=,))\s+(?=(?:επίσης|επισης|Επίσης|Επισης|ΕΠΙΣΗΣ)\b)"
                   r"|(?<=[.!;?;])\s+(?=(?:Και|ΚΑΙ)\s)")


def _also_marks(seg):
    marks, last = [], 0
    for m in _ALSO.finditer(seg):
        cut = m.end()
        if len(seg[last:cut].strip()) >= MIN_SIDE and len(seg[cut:].strip()) >= MIN_SIDE:
            marks.append(cut)
            last = cut
    return marks


def _split(seg, marks):
    cuts = sorted(set(m for m in marks if 0 < m < len(seg)))
    parts, prev = [], 0
    for c in cuts + [len(seg)]:
        parts.append(seg[prev:c])
        prev = c
    return [p.strip() for p in parts if p.strip()]


def points(text):
    """Exact slices of the original, in order (see module docstring for the rules)."""
    text = (text or "").replace("\r\n", "\n")
    out = []
    for s, e in _line_blocks(text):
        block = text[s:e]
        if "\n" in block:  # a list item with continuation lines stays whole
            out.append(block.strip())
            continue
        for part in _split(block, _inline_numbering(block)):
            out.extend(_split(part, _also_marks(part)))
    return out


def questions(text):
    """Sentences (within a line) ending with ; ? or the Greek question mark."""
    out = []
    for ln in (text or "").splitlines():
        for sent in re.split(r"(?<=[.!?;;])\s+", ln.strip()):
            sent = sent.strip()
            if len(sent) > 1 and sent.endswith(_Q_END) and sent not in out:
                out.append(sent)
    return out


def refs(text):
    """Ids (M-…, R-…), paths (~/…, /home/…) and file names, in order of appearance, without duplicates."""
    found = []
    for rx in (_ID, _PATH, _FILE):
        for m in rx.finditer(text or ""):
            found.append((m.start(), m.group(0).rstrip(".:")))
    out = []
    for _, r in sorted(found):
        if r not in out and not any(r != o and r in o for o in out):
            out.append(r)
    return [r for r in out if not any(r != o and r in o for o in out)]


def structure(text):
    return {"original": text or "", "points": points(text), "questions": questions(text), "refs": refs(text)}


def _fence(text):
    longest = max([len(m) for m in re.findall(r"`+", text or "")] + [2])
    return "`" * (longest + 1)


def to_markdown(text):
    s = structure(text)
    f = _fence(s["original"])
    md = ["#### Αρχικό μήνυμα (αυτούσιο)", f + "text", s["original"], f, "", "#### Σημεία"]
    for i, p in enumerate(s["points"], 1):
        md.append(f"- **P{i}** " + p.replace("\n", "\n  "))
    if s["questions"]:
        md += ["", "#### Ερωτήσεις"] + [f"- {q}" for q in s["questions"]]
    if s["refs"]:
        md += ["", "#### Αναφορές"] + [f"- `{r}`" if "`" not in r else f"- {r}" for r in s["refs"]]
    return "\n".join(md) + "\n"


# ---------------------------------------------------------------- dashboard composer gate (pure, testable)
def gate(state, name, submitted=None, files=None):
    """What a chat composer does this run. state: dict-like (st.session_state).
    Returns ("send", body, files) | ("preview", markdown, files) | (None, None, None).
    The preview stays pending (re-shown on every full rerun) until choose() or dismiss(); a choice is consumed once.
    With the toggle off nothing changes."""
    ck, pk = CHOICE_KEY + name, PENDING_KEY + name
    if ck in state:
        body, files = state[ck]
        del state[ck]
        return "send", body, files
    if submitted is not None and (str(submitted).strip() or files):
        if state.get(TOGGLE_KEY + name) and str(submitted).strip():
            state[pk] = {"original": submitted, "md": to_markdown(submitted), "files": files}
        else:
            return "send", submitted, files
    if pk in state:
        p = state[pk]
        return "preview", p["md"], p["files"]
    return None, None, None


def choose(state, name, which):
    """Preview dialog choice: which = "md" (structured) or "original". Sent on the composer's next run."""
    p = state[PENDING_KEY + name]
    del state[PENDING_KEY + name]
    state[CHOICE_KEY + name] = (p["md"] if which == "md" else p["original"], p["files"])


def dismiss(state):
    """Dialog closed with ✕: drop every pending preview (nothing is sent)."""
    for k in [k for k in list(state.keys()) if str(k).startswith(PENDING_KEY)]:
        del state[k]


def main(argv):
    args = [a for a in argv if a != "--json"]
    text = open(args[0], encoding="utf-8").read() if args else sys.stdin.read()
    if "--json" in argv:
        print(json.dumps(structure(text), ensure_ascii=False, indent=1))
    else:
        sys.stdout.write(to_markdown(text))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
