"""Acting deputy routing, execution boundaries, clean service PATH and handoff tests; no real Codex calls."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import deputy
from labdb import CODEX_MODELS, CODEX_MODEL_EFFORTS, LabDB, LabError


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("QRL_LAB_DIR", str(tmp_path))
    monkeypatch.setattr(deputy, "KIT", str(tmp_path))
    monkeypatch.setattr(deputy, "codex_bin", lambda: "/mock/bin/codex")
    (tmp_path / "AGENTS.md").write_text("Never invent numbers. Existing project rules apply.")
    lab = tmp_path / ".lab"
    db = LabDB(str(lab / "lab.db"))
    yield db, lab
    db.close()


def fake_success(cmd, **kwargs):
    Path(cmd[cmd.index("-o") + 1]).write_text("Κώστα, ολοκληρώθηκε. tools/example.py · checks passed.\nNEEDS_APPROVAL: no")
    return subprocess.CompletedProcess(cmd, 0, "", "")


@pytest.mark.parametrize("model", CODEX_MODELS)
def test_routing_requested_model_effort_and_workspace_write(state, model):
    db, lab = state
    for effort in CODEX_MODEL_EFFORTS[model]:
        mid = db.researcher_send("change project tools", req_model=model, req_effort=effort)
        calls = []

        def execute(cmd, **kwargs):
            calls.append((cmd, kwargs))
            assert db.message(mid)["status"] == "in_progress"
            return fake_success(cmd, **kwargs)

        assert deputy.handle_message(db, str(lab), mid, run=execute) == "done"
        cmd, kwargs = calls[0]
        assert cmd[:4] == ["/mock/bin/codex", "exec", "--sandbox", "workspace-write"]
        assert cmd[cmd.index("-m") + 1] == model
        assert f'model_reasoning_effort="{effort}"' in cmd
        assert 'approval_policy="never"' in cmd
        assert "approved implementation work" in kwargs["input"]
        assert "tools/launch_run.py" in kwargs["input"]
        assert "without explicit task-specific approval" in kwargs["input"]
        assert "Do not run sudo, kubectl mutations or QPU jobs here" in kwargs["input"]
        assert db.thread(mid)[-1]["model"] == f"{model} · {effort} · αναπληρωτής"
    assert not (lab / "deputy_queue.jsonl").exists()


@pytest.mark.parametrize("body,expected", [("γειά", ("gpt-6-luna", "low")),
                                               ("review the code", ("gpt-6.1-sol", "medium")),
                                               ("x" * 300, ("gpt-6.1-sol", "medium"))])
def test_automatic_routing_bounded(body, expected):
    assert deputy.choose_model([{"author": "researcher", "body": body}]) == expected


@pytest.mark.parametrize("selection,expected", [("haiku", ("gpt-6-luna", "low")),
                                                   ("sonnet", ("gpt-6.1-sol", "medium")),
                                                   ("opus", ("gpt-6-astra", "high")),
                                                   ("codex", ("gpt-6-luna", "low"))])
def test_routing_legacy_choices(selection, expected):
    message = {"author": "researcher", "body": "γειά", "req_model": selection}
    assert deputy.choose_model([message]) == expected
    message["req_effort"] = "med"
    assert deputy.choose_model([message]) == (expected[0], "medium")


def test_routing_message_selection_does_not_inherit_future_or_previous_choices(state):
    db, lab = state
    mid = db.researcher_send("edit tools", req_model="gpt-6-astra", req_effort="max")
    newer = db.researcher_send("hello", thread_id=mid, req_model="gpt-6-luna", req_effort="low")
    calls = []

    def execute(cmd, **kwargs):
        calls.append(cmd)
        assert f"[{newer} ·" not in kwargs["input"]
        return fake_success(cmd, **kwargs)

    deputy.handle_message(db, str(lab), mid, run=execute)
    assert "gpt-6-astra" in calls[0] and 'model_reasoning_effort="max"' in calls[0]
    assert db.message(newer)["status"] == "new"
    assert deputy.choose_model([db.message(mid), {"author": "researcher", "body": "hello"}]) == ("gpt-6-luna", "low")
    assert deputy.choose_model([{"author": "researcher", "body": "hello", "req_effort": "ultra"}]) == ("gpt-6.1-sol", "ultra")


def test_validation_disallows_unknown_or_unsupported_routing(state):
    db, _ = state
    for model, effort in [("invented", "low"), ("gpt-6-sol", "injected"),
                          ("gpt-6-luna", "ultra"), ("gpt-5.6-luna", "ultra")]:
        with pytest.raises(LabError):
            db.researcher_send("x", req_model=model, req_effort=effort)
        with pytest.raises(LabError):
            deputy.build_command("unused", model=model, effort=effort)
    with pytest.raises(LabError):
        deputy.choose_model([{"author": "researcher", "body": "hello", "req_model": "haiku", "req_effort": "ultra"}])
    with pytest.raises(LabError):
        db.researcher_send("hello", req_model="haiku", req_effort="ultra")


def test_path_clean_service_discovers_cli_and_node(tmp_path, monkeypatch):
    # Numeric ordering must choose v24 over v9; no installed system executable participates.
    monkeypatch.setattr(deputy.os.path, "expanduser", lambda path: str(tmp_path / path.removeprefix("~/")))
    monkeypatch.setenv("PATH", "/missing")
    for version in ("v9.0.0", "v24.2.0"):
        directory = tmp_path / ".nvm" / "versions" / "node" / version / "bin"
        directory.mkdir(parents=True)
        for filename in ("codex", "node"):
            file = directory / filename
            file.write_text("#!/bin/sh\nexit 0\n")
            file.chmod(0o755)
    chosen = deputy.codex_bin()
    assert "/v24.2.0/bin/codex" in chosen
    assert os.environ["PATH"].split(os.pathsep)[0] == str(Path(chosen).parent)
    assert deputy.shutil.which("node") == str(Path(chosen).with_name("node"))


def test_path_missing_node_and_cli_reports_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(deputy.os.path, "expanduser", lambda path: str(tmp_path / path.removeprefix("~/")))
    monkeypatch.setenv("PATH", "/missing")
    with pytest.raises(FileNotFoundError, match="CLI or Node.js"):
        deputy.codex_bin()
    directory = tmp_path / ".nvm" / "versions" / "node" / "v24.2.0" / "bin"
    directory.mkdir(parents=True)
    cli = directory / "codex"
    cli.write_text("#!/usr/bin/env node\n")
    cli.chmod(0o755)
    with pytest.raises(FileNotFoundError, match="CLI or Node.js"):
        deputy.codex_bin()


def test_path_discovery_failure_reaches_retryable_dashboard_state(state, monkeypatch):
    db, lab = state
    mid = db.researcher_send("edit tools")

    def missing():
        raise FileNotFoundError("Codex CLI or Node.js runtime not found")

    def unexpected_run(*args, **kwargs):
        pytest.fail("A missing CLI must fail before subprocess execution")

    monkeypatch.setattr(deputy, "codex_bin", missing)
    assert deputy.handle_message(db, str(lab), mid, run=unexpected_run) == "failed"
    assert "CLI or Node.js runtime not found" in db.thread(mid)[-1]["body"]
    assert not (lab / "deputy_queue.jsonl").exists()


@pytest.mark.parametrize("failure", ["missing", "timeout", "exit", "empty"])
def test_failure_retryable_codex_status_and_handoff(state, failure):
    db, lab = state
    mid = db.researcher_send("edit dashboard")

    def execute(cmd, **kwargs):
        if failure == "missing":
            raise FileNotFoundError("Codex CLI missing")
        if failure == "timeout":
            raise subprocess.TimeoutExpired(cmd, 600)
        return subprocess.CompletedProcess(cmd, 1 if failure == "exit" else 0, "", "")

    assert deputy.handle_message(db, str(lab), mid, run=execute) == "failed"
    assert db.message(mid)["status"] == "failed"
    text = db.thread(mid)[-1]["body"]
    assert "νέα προσπάθεια από τον Codex" in text
    assert "σε ουρά για τον Claude" not in text
    assert not (lab / "deputy_queue.jsonl").exists()
    assert "Retry with Codex" in (lab / "deputy_handoff.md").read_text()
    events = [json.loads(line) for line in (lab / "events.jsonl").read_text().splitlines()]
    assert events[-1]["hook_event_name"] == "SubagentStop" and events[-1]["status"] == "failed"
    assert events[-1]["model"] and events[-1]["effort"] and mid in events[-1]["task"]


def test_audit_start_end_and_handoff_for_every_action(state):
    db, lab = state
    mid = db.researcher_send("change project tools", req_model="gpt-6-sol", req_effort="high")
    deputy.handle_message(db, str(lab), mid, run=fake_success)
    events = [json.loads(line) for line in (lab / "events.jsonl").read_text().splitlines()]
    assert [e["hook_event_name"] for e in events] == ["SubagentStart", "SubagentStop"]
    for event in events:
        assert event["agent_type"] == "codex-deputy"
        assert (event["model"], event["effort"]) == ("gpt-6-sol", "high")
        assert mid in event["task"]
    records = [r for r in db.audit() if r["action"] in ("deputy_start", "deputy_end")]
    assert len(records) == 2
    for row in records:
        detail = json.loads(row["detail"])
        assert (detail["role"], detail["model"], detail["effort"]) == ("codex-deputy", "gpt-6-sol", "high")
        assert mid in detail["task"]
    handoff = json.loads((lab / "deputy_handoff.jsonl").read_text().strip())
    assert handoff["status"] == "done" and handoff["message"] == mid
    assert "tools/example.py" in (lab / "deputy_handoff.md").read_text()


def test_handoff_approval_block_remains_explicit(state):
    db, lab = state
    mid = db.researcher_send("change experiment architecture")

    def execute(cmd, **kwargs):
        Path(cmd[cmd.index("-o") + 1]).write_text("Κώστα, απαιτείται έγκριση νέας αρχιτεκτονικής.\nNEEDS_APPROVAL: yes")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    assert deputy.handle_message(db, str(lab), mid, run=execute) == "waiting_approval"
    assert db.message(mid)["status"] == "waiting_approval"
    entry = json.loads((lab / "deputy_queue.jsonl").read_text().strip())
    assert entry["reason"] == "approval required"
    assert "σε ουρά για τον Claude" not in entry["answer"]
