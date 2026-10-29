import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from researcher_text import researcher_text


def test_address_signature_idempotent():
    for provider in ("claude", "codex", None):
        text = researcher_text("Η εργασία ολοκληρώθηκε.", provider)
        assert text.startswith("Κώστα,\n")
        assert text.count("— Πάρις") == 1
        assert ("(Codex)" in text) == (provider == "codex")
        assert researcher_text(text, provider) == text
        assert researcher_text(text + "\n\n— Codex · model · 1′") .count("— Πάρις") == 1


def test_existing_format_and_status_parsing():
    from dispatcher import split_status
    original = "Κώστα,\n\nΈτοιμο.\n\n— Πάρις (Codex)"
    text, status = split_status(original + "\nSTATUS: waiting_approval")
    assert status == "waiting_approval" and researcher_text(text, "codex") == original
    assert researcher_text("Κώστα,\n\nΈτοιμο.\n\n— Πάρις", "codex").count("— Πάρις") == 1


def test_dispatcher_post_boundary():
    from dispatcher import Dispatcher
    class Lab:
        def post(self, *args, **kwargs):
            self.args = args
    d = Dispatcher.__new__(Dispatcher)
    d.lab = Lab()
    d._post("M-test", "Αυτόματη ειδοποίηση.")
    assert d.lab.args[1] == "Κώστα,\n\nΑυτόματη ειδοποίηση.\n\n— Πάρις"
