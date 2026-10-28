---
name: core-split
description: "CPU partition — 0-3 dashboard, 4-7 agents/tests, 8-39 experiments"
metadata:
  node_type: memory
  type: project
  originSessionId: 7456dd5b-8481-4276-adb4-14c4f6ae5690
  modified: 2026-10-21T12:23:10.928Z
---

Researcher, 2026-10-21: split the VM's cores. 0-3 = dashboard (Streamlit) only; tools/verify_services.py starts it with `taskset -c 0-3`. 4-7 = agents, engineer tests, profiling. 8-39 = experiments (launch_run.py DEFAULT_SIM_CPUS, R-20261017-017).
**Why:** the dashboard became too slow to use while sharing cores.
**How to apply:** pin engineer tests with `taskset -c 4-7`. Never pin the coordinator's Claude process: launch_run.py intersects the pin set with its own affinity (sched_getaffinity), so pinning it would empty the experiment pool. If the server is restarted outside verify_services, re-pin it to 0-3. Related: [[engineer-test-cpu]], [[experiment-loop]].
