"""Dashboard routing contract; AppTest and DB writes use isolated temporary roots."""
import json
import time
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import agent_models as am
from labdb import LabDB


CODEX_MODELS = ("gpt-6-luna", "gpt-6-sol", "gpt-6.1-sol", "gpt-6-astra",
                "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna")


@pytest.mark.parametrize("model", CODEX_MODELS)
def test_all_supported_routing_choices_persist(model, tmp_path):
    assert model in am.MODEL_CHOICES
    expected = ("low", "medium", "high", "xhigh", "max") + (() if model.endswith("-luna") else ("ultra",))
    assert am.effort_choices(model) == expected
    d = LabDB(str(tmp_path / "lab.db"))
    try:
        for effort in expected:
            mid = d.researcher_send("explicit routing", req_model=model, req_effort=effort)
            assert (d.message(mid)["req_model"], d.message(mid)["req_effort"]) == (model, effort)
    finally:
        d.close()


@pytest.mark.parametrize("model", [None, "haiku", "sonnet", "opus", "codex"])
def test_legacy_routing_preserved(model, tmp_path):
    assert model in am.MODEL_CHOICES
    d = LabDB(str(tmp_path / "lab.db"))
    try:
        mid = d.researcher_send("legacy routing", req_model=model, req_effort="med")
        assert d.message(mid)["req_model"] == model
        assert d.message(mid)["req_effort"] == "med"
    finally:
        d.close()


def test_composer_switches_models_and_persists_selection(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    # Reuse code through symlinks, with all state rooted in the temporary directory.
    for name in ("tools", "dashboard", "docs", "paper", ".streamlit"):
        (tmp_path / name).symlink_to(ROOT / name, target_is_directory=True)
    monkeypatch.setenv("QRL_LAB_DIR", str(tmp_path))
    monkeypatch.setenv("QRL_EAGER_TABS", "0")
    monkeypatch.setenv("QRL_PROM_URL", "http://127.0.0.1:9")
    at = AppTest.from_file(str(tmp_path / "dashboard/app.py"), default_timeout=60).run()
    assert not at.exception
    picker = at.selectbox(key="req_model_sel")
    assert all(am.MODEL_CHOICES[m] in picker.options for m in CODEX_MODELS)
    picker.set_value("gpt-6-astra").run()
    assert not at.exception
    at.selectbox(key="req_effort_sel").set_value("ultra").run()
    at.chat_input[0].set_value("Codex composer integration").run()
    assert not at.exception
    d = LabDB(str(tmp_path / ".lab/lab.db"))
    try:
        row = d.conn.execute("SELECT req_model,req_effort FROM messages WHERE body=?",
                             ("Codex composer integration",)).fetchone()
        assert tuple(row) == ("gpt-6-astra", "ultra")
    finally:
        d.close()
    at.selectbox(key="req_model_sel").set_value("gpt-6-luna").run()
    assert not at.exception
    assert "ultra" not in at.selectbox(key="req_effort_sel").options
    assert at.selectbox(key="req_effort_sel").value == "medium"
    at.selectbox(key="req_model_sel").set_value("sonnet").run()
    assert not at.exception
    assert at.selectbox(key="req_effort_sel").value == "med"


def test_agents_card_shows_current_codex_provider_role_model(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    for name in ("tools", "dashboard", "docs", "paper", ".streamlit"):
        (tmp_path / name).symlink_to(ROOT / name, target_is_directory=True)
    monkeypatch.setenv("QRL_LAB_DIR", str(tmp_path))
    monkeypatch.setenv("QRL_EAGER_TABS", "0")
    (tmp_path / ".lab").mkdir()
    now = time.time()
    records = [{"hook_event_name": "SessionStart", "ts": now - 100, "model": "claude-opus-5-5"},
               {"hook_event_name": "SubagentStart", "agent_id": "d", "agent_type": "codex-deputy",
                "ts": now - 10, "model": "gpt-6-astra", "effort": "high", "summary": "Fix dashboard"}]
    (tmp_path / ".lab/events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in records))
    (tmp_path / ".lab/health.json").write_text(json.dumps({"checked": now, "state": "limit", "since": now - 10}))
    at = AppTest.from_file(str(tmp_path / "dashboard/app.py"), default_timeout=60)
    at.query_params["tab"] = "🤖 Πράκτορες"
    at.run()
    assert not at.exception
    text = " ".join(x.value for x in at.markdown) + " ".join(x.value for x in at.caption)
    assert "Συντονιστής (Codex)" in text and "μοντέλο: gpt-6-astra" in text and "ρόλος: codex-deputy" in text
    assert "Συντονιστής (Claude)" not in text and "μοντέλο: claude-opus" not in text
