# Gates: deputy execution and reliability

OWNS: tools/deputy.py, tools/labdb.py, tests/test_lab.py, tests/test_deputy_write.py, docs/deputy_handoff.md

Scope: make the approved Codex deputy a logged acting coordinator with requested model/effort routing and reliable CLI discovery

- [ ] G1: deputy command uses the requested supported Codex model and effort and permits project writes
  CHECK: .venv/bin/python -m pytest -q tests/test_deputy_write.py -k 'routing or write' && echo 'deputy routing write tests succeeded'
  EXPECT: deputy routing write tests succeeded
  EVIDENCE: pending

- [ ] G2: automatic routing remains bounded to documented Codex roles and allowed effort values
  CHECK: .venv/bin/python -m pytest -q tests/test_deputy_write.py -k 'automatic or validation' && echo 'deputy validation tests succeeded'
  EXPECT: deputy validation tests succeeded
  EVIDENCE: pending

- [ ] G3: clean PATH CLI discovery works and failures are reported as retryable Codex errors without the obsolete Claude-only queue claim
  CHECK: .venv/bin/python -m pytest -q tests/test_deputy_write.py -k 'path or failure' && echo 'deputy path failure tests succeeded'
  EXPECT: deputy path failure tests succeeded
  EVIDENCE: pending

- [ ] G4: deputy actions emit start/end role, model, effort and task records and leave a Claude-readable handoff
  CHECK: .venv/bin/python -m pytest -q tests/test_deputy_write.py -k 'audit or handoff' && echo 'deputy audit handoff tests succeeded'
  EXPECT: deputy audit handoff tests succeeded
  EVIDENCE: pending
