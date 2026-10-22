"""tools/msg_structure.py: deterministic message structuring (M-20261022-015)."""
import os
import random
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import msg_structure as ms  # noqa: E402


def nows(s):
    return re.sub(r"\s+", "", s)


def check_property(text):
    assert nows("".join(ms.points(text))) == nows(text), (text, ms.points(text))


def test_inline_bare_numbering():
    t = "1 κανε αυτο το τεστ να περναει 2 εδω βαλε και ενα κουμπι 3 στειλε μου αναφορα"
    assert ms.points(t) == ["1 κανε αυτο το τεστ να περναει", "2 εδω βαλε και ενα κουμπι", "3 στειλε μου αναφορα"]
    check_property(t)


def test_inline_bare_numbering_ambiguous_not_split():
    t = "1 κανε αυτο με 2 seeds και 2 εδω αλλαξε το label"
    assert ms.points(t) == [t]
    # a count in the middle of a sentence with no leading 1 is not numbering
    t2 = "θελω 2 seeds και 3 runs για το baseline"
    assert ms.points(t2) == [t2]


def test_inline_dotted_parens_and_greek_letters():
    assert ms.points("Κανε τα εξης: 1. φτιαξε το test 2. κανε commit") == \
        ["Κανε τα εξης:", "1. φτιαξε το test", "2. κανε commit"]
    assert ms.points("α) διορθωσε το label β) προσθεσε test γ) ενημερωσε τα docs") == \
        ["α) διορθωσε το label", "β) προσθεσε test", "γ) ενημερωσε τα docs"]
    assert ms.points("1) πρωτο 2) δευτερο") == ["1) πρωτο", "2) δευτερο"]


def test_lines_bullets_and_continuations():
    t = "Γεια σου Παρι\n\n- πρωτο θεμα\n  συνεχεια του πρωτου\n- δευτερο θεμα\nκαι μια τελευταια γραμμη"
    assert ms.points(t) == ["Γεια σου Παρι", "- πρωτο θεμα\n  συνεχεια του πρωτου", "- δευτερο θεμα",
                            "και μια τελευταια γραμμη"]
    check_property(t)


def test_episis_and_kai_only_when_clearly_separate():
    long_a = "Θελω να δεις γιατι το dashboard δειχνει αγνωστο μοντελο στο chat."
    long_b = "επισης φτιαξε ενα script που δομει τα μηνυματα μου σε markdown"
    assert ms.points(long_a + " " + long_b) == [long_a, long_b]
    assert ms.points(long_a + " Και θελω να ξερω ποτε τελειωνει το run των οκτω seeds") == \
        [long_a, "Και θελω να ξερω ποτε τελειωνει το run των οκτω seeds"]
    short = "κανε commit. επισης push"  # too short to be sure
    assert ms.points(short) == [short]
    mid = "κοιτα το test και διορθωσε το label του συντονιστη στο dashboard και στο brain view"
    assert ms.points(mid) == [mid]  # mid-sentence και never splits


def test_exact_wording_and_accents_preserved():
    t = "Πάρι, δες το ~/qrl-lab/docs/PLAN.md;  Επίσης   τρέξε τα tests του dashboard/app.py χωρίς να αλλάξεις κάτι άλλο."
    for p in ms.points(t):
        assert p in t
    check_property(t)


def test_questions_and_refs():
    t = ("Τι εγινε με το M-20261022-013;\nΕιδες το R-20261021-009? δες ~/qrl-lab/tools/agent_models.py\n"
         "και το tests/test_lab.py. 2.5 δεν ειναι αρχειο")
    assert ms.questions(t) == ["Τι εγινε με το M-20261022-013;", "Ειδες το R-20261021-009?"]
    assert ms.refs(t) == ["M-20261022-013", "R-20261021-009", "~/qrl-lab/tools/agent_models.py", "tests/test_lab.py"]


def test_markdown_keeps_original_verbatim():
    t = "1 κανε αυτο ```κωδικας``` 2 εδω κατι αλλο;"
    md = ms.to_markdown(t)
    assert "````text\n" + t + "\n````" in md
    assert "- **P1** 1 κανε αυτο ```κωδικας```" in md and "- **P2** 2 εδω κατι αλλο;" in md
    assert "#### Ερωτήσεις" in md


def test_property_random_messages():
    rnd = random.Random(7)
    words = ["κανε", "1", "2", "3", "α)", "β)", "επισης", "Και", "και", "test", "M-20261022-001", "~/qrl-lab/x.py",
             "-", ".", ";", "?", ",", ":", "1.", "2)", "δες", "το", "dashboard", "\n", "\n\n", "  ", "Πάρι", "ά"]
    for _ in range(500):
        text = " ".join(rnd.choice(words) for _ in range(rnd.randint(0, 40)))
        check_property(text)
        for p in ms.points(text):
            assert p in text.replace("\r\n", "\n")


def test_gate_toggle_off_unchanged_and_preview_flow():
    st = {}
    assert ms.gate(st, "chat", None) == (None, None, None)
    assert ms.gate(st, "chat", "γεια") == ("send", "γεια", None)
    assert st == {}
    st[ms.TOGGLE_KEY + "chat"] = True
    act, md, files = ms.gate(st, "chat", "1 κανε αυτο 2 εδω", [("a.txt", b"x")])
    assert act == "preview" and "**P2** 2 εδω" in md and files == [("a.txt", b"x")]
    assert ms.gate(st, "chat", None) == ("preview", md, files)  # re-shown on a full rerun
    ms.choose(st, "chat", "md")
    assert ms.gate(st, "chat", None) == ("send", md, [("a.txt", b"x")])
    assert ms.gate(st, "chat", None) == (None, None, None)  # consumed once
    ms.gate(st, "chat", "αρχικο κειμενο")
    ms.choose(st, "chat", "original")
    assert ms.gate(st, "chat", None) == ("send", "αρχικο κειμενο", None)
    ms.gate(st, "chat", "κατι")
    ms.dismiss(st)
    assert ms.gate(st, "chat", None) == (None, None, None)  # ✕ drops it, nothing sent
    assert ms.gate(st, "paper", "x") == ("send", "x", None)  # per-composer toggle
    assert ms.gate(st, "chat", "", [("f", b"")])[0] == "send"  # files only: nothing to structure


def test_question_not_cut_at_file_dot():
    assert ms.questions("τι κανει το app.py;") == ["τι κανει το app.py;"]
