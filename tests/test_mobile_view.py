"""Phone CSS and home-screen tags (tools/mobile_view.py, J79)."""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import mobile_view  # noqa: E402


def test_css_only_inside_phone_media_query():
    body = mobile_view.CSS.replace("<style>", "").replace("</style>", "").strip()
    assert body.startswith("@media (max-width:480px){") and body.endswith("}")
    assert body.count("{") == body.count("}")
    assert "font-size:16px" in body and "min-height:44px" in body


def test_script_has_home_screen_tags():
    s = mobile_view.script()
    for name in ("apple-mobile-web-app-capable", "apple-mobile-web-app-title", "theme-color"):
        assert name in s
    assert "/app/static/apple-touch-icon.png" in s and "/app/static/manifest.json" in s
    assert "%(" not in s and "window.parent" in s and "max-width:480px" in s


def test_static_files_exist_and_manifest_matches():
    static = os.path.join(ROOT, "dashboard", "static")
    on_disk = json.load(open(os.path.join(static, "manifest.json")))
    assert on_disk == mobile_view.manifest()
    assert on_disk["display"] == "standalone"
    for icon in on_disk["icons"] + [{"src": "/app/static/apple-touch-icon.png"}]:
        assert os.path.isfile(os.path.join(static, os.path.basename(icon["src"])))


def test_static_serving_enabled():
    cfg = open(os.path.join(ROOT, ".streamlit", "config.toml")).read()
    assert re.search(r"(?m)^enableStaticServing\s*=\s*true", cfg)


def test_every_tab_has_a_group():
    src = open(os.path.join(ROOT, "dashboard", "app.py"), encoding="utf-8").read()
    names = re.search(r"TAB_NAMES = \[(.*?)\]", src, re.S).group(1)
    consts = dict(re.findall(r'^(\w+_TAB) = "([^"]+)"', src, re.M))
    labels = [consts.get(x.strip(), x.strip().strip('"')) for x in names.split(",") if x.strip()]
    keys = [k for _, ks in mobile_view.GROUPS for k in ks]
    missing = [lab for lab in labels if not any(k in lab for k in keys)]
    assert not missing, missing
