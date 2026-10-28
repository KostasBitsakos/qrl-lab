# Gates: Codex deputy coordinator handover

Scope: integrate dashboard routing, deputy execution and experiment audit without disrupting live work

- [ ] G1: all child deliverables and their interfaces pass integration verification
  CHECK: .venv/bin/python -m pytest -q tests/test_agent_models.py tests/test_brain_view.py tests/test_topology_view.py tests/test_dashboard_codex_routing.py tests/test_deputy_write.py && echo 'root integration tests succeeded'
  EXPECT: root integration tests succeeded
  EVIDENCE: pending

- [ ] G2: existing dashboard/deputy regression coverage passes
  CHECK: .venv/bin/python -m pytest -q tests/test_lab.py -k 'dashboard or deputy or agent_race or health' && echo 'root regression tests succeeded'
  EXPECT: root regression tests succeeded
  EVIDENCE: pending

- [ ] G3: no experiment driver, model branch, run state or result was changed by dashboard/fallback implementation
  EVIDENCE: pending

- [ ] G4: corrected reply is posted in the researcher thread with Codex identity and completed status
  EVIDENCE: pending

- [ ] G5: model routing evidence shows routine work on Luna/low and reserves Astra/high-or-higher for experiment architecture and review
  EVIDENCE: pending
