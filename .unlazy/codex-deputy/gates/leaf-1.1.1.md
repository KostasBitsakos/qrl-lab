# Gates: dashboard routing and active identity

OWNS: dashboard/app.py, tools/agent_models.py, tools/race_view.py, tools/brain_view.py, tests/test_agent_models.py, tests/test_brain_view.py, tests/test_dashboard_codex_routing.py, docs/agents_tab_audit.md

Scope: expose supported Codex routing choices and render the real coordinator identity across Agents views

- [ ] G1: dashboard stores every supported Codex model and effort selection without breaking legacy choices
  CHECK: .venv/bin/python -m pytest -q tests/test_dashboard_codex_routing.py && echo 'dashboard routing tests succeeded'
  EXPECT: dashboard routing tests succeeded
  EVIDENCE: pending

- [ ] G2: coordinator, race and brain views derive Codex deputy identity/model when Claude is unavailable
  CHECK: .venv/bin/python -m pytest -q tests/test_agent_models.py tests/test_brain_view.py && echo 'active identity tests succeeded'
  EXPECT: active identity tests succeeded
  EVIDENCE: pending

- [x] G3: prior unfulfilled Agents-tab requests are inventoried and mapped to implemented behavior or a precise handoff
  EVIDENCE: Reviewed docs/agents_tab_audit.md against researcher message bodies in .lab/lab.db read-only, including M-20261016-067, M-20261017-005/006/007/012/059/064/073/094 and M-20261021-014/016/049/063/066/075. Each Agents request maps to existing/new implementation; Architecture controls have exact file/test handoff. Four passes completed: full implementation, domain review, integration-defect hunt, clean polish/diff review. No experiment paths edited.
