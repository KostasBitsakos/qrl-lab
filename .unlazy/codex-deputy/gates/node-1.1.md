# Gates: implementation and audit integration

Scope: integrate children 1.1.1, 1.1.2 and 1.1.3

- [ ] N1: every named direct child is reverified from its exact ledger
  CHECK: node /home/ubuntu/.codex/skills/unlazy/scripts/gate-check.mjs --root . --cwd . --reverify --jobs 1 .unlazy/codex-deputy/gates/leaf-1.1.1.md .unlazy/codex-deputy/gates/leaf-1.1.2.md .unlazy/codex-deputy/gates/leaf-1.1.3.md
  EXPECT: ALL MET
  EVIDENCE: pending

- [ ] N2: dashboard selections are accepted by the DB and honored by the deputy
  CHECK: .venv/bin/python -m pytest -q tests/test_dashboard_codex_routing.py tests/test_deputy_write.py && echo 'routing integration tests succeeded'
  EXPECT: routing integration tests succeeded
  EVIDENCE: pending

- [ ] N3: composed dashboard and fallback behavior works without experiment-side writes
  EVIDENCE: pending

- [ ] N4: affected existing tests show no regression
  CHECK: .venv/bin/python -m pytest -q tests/test_agent_models.py tests/test_brain_view.py tests/test_topology_view.py && echo 'view regression tests succeeded'
  EXPECT: view regression tests succeeded
  EVIDENCE: pending

- [ ] N5: every direct leaf ownership lease was released after parent verification
  EVIDENCE: pending

- [ ] N6: consequential deputy write authority and experiment non-interference were reviewed by the root agent
  EVIDENCE: pending
