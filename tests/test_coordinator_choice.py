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


def test_selector_label_from_file_when_sessionstart_scrolled_out(tmp_path):
    """M-20261022-013: the selector showed «τώρα: άγνωστο» although the coordinator was claude-opus-5-5."""
    import json
    p = tmp_path / "events.jsonl"
    recs = [{"hook_event_name": "SessionStart", "model": "claude-opus-5-5", "ts": 100.0}]
    recs += [{"hook_event_name": "PreToolUse", "tool_name": "Bash", "ts": 100.0 + i} for i in range(1, 50)]
    p.write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
    tail = recs[-10:]  # in-memory tail without the SessionStart
    assert agent_models.latest_session_start(str(p), block=64)["model"] == "claude-opus-5-5"
    ev = agent_models.with_session_start(tail, str(p))
    ident = agent_models.coordinator_identity(ev, None, now=200.0)
    assert ident["model"] == "claude-opus-5-5"
    assert agent_models.model_choices(ident)[None] == "Πάρις · συντονιστής (τώρα: Claude Opus 5.5)"
    assert agent_models.with_session_start(tail, str(tmp_path / "missing.jsonl")) == tail


def test_identity_rejects_dataframe():
    import pandas as pd
    df = pd.DataFrame([{"event": "SessionStart", "model": "claude-opus-5-5"}])
    try:
        agent_models.coordinator_identity(df)
        assert False
    except TypeError:
        pass


def test_selector_label_codex_deputy():
    ev = [{"hook_event_name": "SessionStart", "model": "claude-opus-5-5", "ts": 100.0},
          {"hook_event_name": "SubagentStart", "agent_type": "codex-deputy", "agent_id": "d1",
           "model": "gpt-6.1-sol", "ts": 150.0}]
    ident = agent_models.coordinator_identity(ev, {"claude": {"state": "limit"}}, now=200.0)
    assert "Codex gpt-6.1-sol, αναπληρωτής" in agent_models.model_choices(ident)[None]
