import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import agent_models, labdb, deputy


def test_label_dynamic():
    assert "Claude Opus 5.5" in agent_models.coordinator_label({"model": "claude-opus-5-5", "role": "coordinator"})
    l = agent_models.coordinator_label({"model": "gpt-6.1-sol", "role": "codex-deputy"})
    assert "Codex gpt-6.1-sol, αναπληρωτής" in l
    assert "άγνωστο" in agent_models.coordinator_label({})


def test_options_and_validation(tmp_path):
    ch = agent_models.model_choices({"model": "claude-opus-5-5"})
    assert list(ch)[0] is None and "τώρα" in ch[None]
    assert ch["coordinator:claude-sonnet-5-5"] == "Πάρις με Claude Sonnet 5.5"
    assert "coordinator:gpt-6-astra" in ch and len(agent_models.COORD_CHOICES) == 7
    assert agent_models.effort_choices("coordinator:gpt-6-sol") == agent_models.CODEX_EFFORTS
    db = labdb.LabDB(str(tmp_path / "l.db"))
    mid = db.researcher_send("hi", req_model="coordinator:claude-sonnet-5-5", req_effort="high")
    assert db.message(mid)["req_model"] == "coordinator:claude-sonnet-5-5"
    try:
        db.researcher_send("x", req_model="coordinator:nope")
        assert False
    except labdb.LabError:
        pass
