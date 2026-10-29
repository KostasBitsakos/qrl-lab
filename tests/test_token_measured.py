import json, os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import token_savings as ts  # noqa: E402


def test_measured():
    with tempfile.TemporaryDirectory() as r:
        os.makedirs(os.path.join(r, ".lab")); os.makedirs(os.path.join(r, ".claude"))
        open(os.path.join(r, "CLAUDE.md"), "w").write("x" * 100)
        open(os.path.join(r, ".lab", "CLAUDE.md.bak-20261028"), "w").write("x" * 500)
        json.dump({"enabledMcpjsonServers": ["a"], "disableClaudeAiConnectors": True, "enabledPlugins": {"p": False, "q": True}},
                  open(os.path.join(r, ".claude", "settings.local.json"), "w"))
        m = ts.measured(r)
        c, a = m["files"]
        assert (c["now"], c["before"], c["saved_bytes"], c["saved_tokens_approx"]) == (100, 500, 400, 100)
        assert a["now"] is None and a["saved_bytes"] is None  # missing files are never guessed
        assert [s["value"] for s in m["settings"]] == [1, "ναι", 1]
