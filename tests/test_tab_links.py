import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import tab_links  # noqa: E402


def test_script():
    s = tab_links.SCRIPT
    assert "contextmenu" in s and "auxclick" in s and "searchParams.set('tab'" in s
    assert "'click'" not in s and '"click"' not in s  # left click is never intercepted
    assert s.count("{") == s.count("}") and s.count("(") == s.count(")")
