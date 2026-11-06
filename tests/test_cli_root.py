"""The CLIs find their lab from the script's location ($QRL_LAB_DIR wins), never from the caller's current directory."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
CLIS = [("dispatcher.py", ["status"]), ("labq.py", ["pending"]), ("work.py", ["status"]),
        ("launch_run.py", ["list"]), ("ask_peer.py", ["wait", "P-none", "--timeout", "1"])]


def clean_env(**extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith("QRL_")}
    env.update(extra)
    return env


def make_lab(tmp_path):
    lab = tmp_path / "lab"
    shutil.copytree(TOOLS, lab / "tools", ignore=shutil.ignore_patterns("__pycache__", "cycle3", "spiky_stage1"))
    (lab / ".lab").mkdir()
    return lab


def run(lab, cli, args, cwd, env):
    return subprocess.run([sys.executable, str(lab / "tools" / cli), *args], cwd=cwd, env=env, capture_output=True,
                          text=True, timeout=60)


def test_cli_uses_the_scripts_lab_not_the_current_directory(tmp_path):
    lab, elsewhere = make_lab(tmp_path), tmp_path / "home"
    elsewhere.mkdir()
    for cli, args in CLIS:
        run(lab, cli, args, elsewhere, clean_env())
        assert not (elsewhere / ".lab").exists(), f"{cli} created a .lab in the caller's directory"
    assert (lab / ".lab" / "dispatch.db").exists() or (lab / ".lab" / "lab.db").exists(), "the script's own lab was used"


def test_qrl_lab_dir_overrides_the_script_location(tmp_path):
    lab, other = make_lab(tmp_path), tmp_path / "other"
    (other / ".lab").mkdir(parents=True)
    run(lab, "dispatcher.py", ["status"], tmp_path, clean_env(QRL_LAB_DIR=str(other)))
    assert (other / ".lab" / "dispatch.db").exists()
    assert not (lab / ".lab" / "dispatch.db").exists(), "QRL_LAB_DIR must win over the script's own lab"


def test_exhaust_drill_from_any_directory_hits_the_scripts_dispatch_db(tmp_path):
    lab, elsewhere = make_lab(tmp_path), tmp_path / "home"
    elsewhere.mkdir()
    r = run(lab, "dispatcher.py", ["exhaust", "claude", "10"], elsewhere, clean_env())
    assert r.returncode == 0, r.stderr
    import sqlite3
    c = sqlite3.connect(lab / ".lab" / "dispatch.db")
    assert c.execute("SELECT state FROM providers WHERE name='claude'").fetchone()[0] == "exhausted"
    assert not (elsewhere / ".lab").exists()
