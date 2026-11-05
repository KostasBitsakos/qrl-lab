import importlib.util, os, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("kb", Path(__file__).resolve().parents[1] / "tools" / "kb.py")
kb = importlib.util.module_from_spec(spec); spec.loader.exec_module(kb)


def setup(tmp, monkeypatch):
    src, kbd = tmp / "src", tmp / "kb"
    src.mkdir()
    monkeypatch.setattr(kb, "KB", kbd); monkeypatch.setattr(kb, "CORPUS", kbd / "corpus")
    monkeypatch.setattr(kb, "DB", kbd / "kb.db"); monkeypatch.setattr(kb, "SOURCES", {"t": (src, None, set())})
    monkeypatch.setattr(kb, "ROOT_OF", {"t": str(src)})
    return src


def test_symlink_secret_and_changes(tmp_path, monkeypatch):
    src = setup(tmp_path, monkeypatch)
    (tmp_path / "cred.md").write_text("-----BEGIN RSA PRIVATE KEY-----\nabc")
    (src / "link.md").symlink_to(tmp_path / "cred.md")
    (src / "a.md").write_text("# T\nhello alpha\n")
    (src / "b.md").write_text('{"password": "abcdefghijklmnopqrstuv"}')
    (src / "c.md").write_text("token = abcdefghijklmnopqrstuvwxyz")
    (src / "ok.md").write_text("uses secrets.token_urlsafe(8)\n")
    (src / "m.py").write_text("def foo_bar():\n    '''doc'''\n")
    copied, removed, secret, total = kb.stage()
    names = {p.name for p in kb.CORPUS.rglob("*") if p.is_file()}
    assert names == {"a.md", "ok.md", "m.py"} and set(secret) == {"t/b.md", "t/c.md"}
    # same-size edit with preserved mtime must be picked up (content compare)
    st = (src / "a.md").stat()
    (src / "a.md").write_text("# T\nhello omega\n"); os.utime(src / "a.md", (st.st_atime, st.st_mtime))
    assert kb.stage()[0] == 1 and "omega" in (kb.CORPUS / "t/a.md").read_text()
    (src / "a.md").unlink()
    assert kb.stage()[1] == 1 and not (kb.CORPUS / "t/a.md").exists()   # deletion propagates
    assert kb.build_index() >= 1
