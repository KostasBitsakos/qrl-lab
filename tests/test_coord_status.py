import os, sqlite3, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import agent_models, coord_status as cs


def st(**kw):
    s = {"settings": dict(cs.DEFAULTS), "providers": {}, "running": None, "hb_age": 3.0}
    s.update(kw)
    return s


def test_idle_and_down():
    assert cs.classify(st(), True)[0] == "idle"
    assert cs.classify(st(), False)[0] == "down"
    assert cs.classify(st(hb_age=500), True)[0] == "down"


def test_running_with_stale_heartbeat_is_working():
    run = {"id": 7, "started": "2026-10-29T00:17:07+00:00", "provider": "claude", "model": None, "refs": '["M-1", "M-2"]'}
    k, icon, head, _ = cs.classify(st(running=run, hb_age=900), True)
    assert k == "working" and "task #7" in head and "M-1, M-2" in head and "02:17" in head


def test_paused_and_limit():
    s = st()
    s["settings"]["paused"] = "1"
    assert cs.classify(s, True)[0] == "paused"
    lim = st(providers={"claude": {"state": "exhausted", "until_ts": time.time() + 3600}})
    assert cs.classify(lim, True)[0] == "limit"


def test_read_state_ro(tmp_path):
    (tmp_path / ".lab").mkdir()
    c = sqlite3.connect(tmp_path / ".lab" / "dispatch.db")
    c.executescript("CREATE TABLE settings(key,value);CREATE TABLE providers(name,state,until_ts);"
                    "CREATE TABLE tasks(id,started,provider,model,refs,status);"
                    "INSERT INTO settings VALUES('coordinator','codex');INSERT INTO settings VALUES('codex_model','gpt-6-sol');"
                    "INSERT INTO tasks VALUES(3,'2026-10-29T00:00:00+00:00','codex','gpt-6-sol','[]','running');")
    c.commit(); c.close()
    s = cs.read_state(str(tmp_path))
    assert s["running"]["id"] == 3 and s["settings"]["coordinator"] == "codex"
    assert cs.coordinator_now(s) == ("codex", "gpt-6-sol", "medium")


def test_label_from_dispatcher():
    assert agent_models.coordinator_label({}, ("claude", "opus", "medium")) == "Πάρις · συντονιστής (τώρα: Claude Opus · medium)"
    assert "Codex gpt-6-sol · high" in agent_models.coordinator_label({}, ("codex", "gpt-6-sol", "high"))
