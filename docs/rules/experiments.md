# Experiments — active rules

Approvals, launcher and seeds policy: see CLAUDE.md golden rule 5, AGENTS.md and PLAN §6, §8. Paused items
(quantum, IBM, real-cluster calibration, stage-B SLO): see paused.md.

## Priority and workloads
- Simulation experiments first, real hardware (cluster calibration) after. (2026-10-17, M-20261017-005/006/007)
- First run the researcher's own input load W0 (sine + noise + spike) with the latest models plus the F2/F3 fixes, then W1 (Poisson + noise + spikes). (2026-10-17, M-20261017-005/006/007) **Resolved (2026-10-20, M-20261020-025): C4: now W0 and its variants; W1 deferred**
- Workloads (PLAN §8.2): W0 + W1 for training, W2 (public production trace, scaled) for testing only, W3 (regime shift) for adaptation; W0 runs first. (2026-10-17, R-20261017-008; PLAN §13 D3) **Resolved (2026-10-20, M-20261020-025): C4: now W0 and its variants; W1 deferred**
- The DInos env is a guide, not a fixed constraint: variants (more sinusoid noise, stronger/more spikes, etc.) may be tried if they give better results; the council (Claude + Codex) judges which are worth it; the researcher's examples are suggestions, not requirements. (2026-10-20, M-20261020-013) **Resolved (2026-10-20, M-20261020-025): C1: later entry wins: env/reward variants allowed; C4: now W0 and its variants; W1 deferred**
- Improve the env per the researcher's description. (2026-10-17, M-20261017-005/006/007)

## Simulator and reward
- Sim v2 design (option 1 of `.lab/council/C-20261016-01/card.md`, provisional labelled parameters): transient fluid/cohort queue, 1–30 pods, startup delay, rebalance loss, calibrated capacity curve C(c); gates frozen before any agent run. (2026-10-16, R-20261016-013; reward part superseded, see archive.md)
- Sim v2 gates: both Sim v2.1 gates failed and remain failed; PLAN §8.1 as amended. (2026-10-17, R-20261017-014)
- Training reward r = 3·L − 5·D − 10·N − 0.5·U − 0.5·M (coefficients from ~/simulations/.../Quantum/environment.py:90-94) through a documented adapter frozen before any training: L = 10·λ/μ_ref; D = p95 over ALL requests (timed-out/dropped counted at the 60 s timeout) / SLO; N = ready+pending pods; U = CPU % points; M = memory % (constant per pod until measured in calibration stage B; disclosed). Sim v2 cost/SLA quantities are reported metrics only. (2026-10-17, R-20261017-017, C-20261017-02) **Resolved (2026-10-20, M-20261020-025): C2: later entry wins: reward may change; the original DInos reward stays as reference arm**
- Realism: literature review + calibration stage B (multi-pod sweeps; separate approval) before any final result. (2026-10-17, R-20261017-017) **Resolved (2026-10-20, M-20261020-025): C3: stage B not required for sim results; calibration stays paused**
- Wider design latitude to reach the DInos picture: the council may change inputs (more observed metrics), reward, activations, number of layers/neurons and layer types (conv, fully connected, ...); the simulator need not be accurate to the real cluster (e.g. Redis response/service times), as long as the core stays: DRL autoscaler, LSTM/transfer (DInos) vs DERP, sinusoidal load with noise and spike. Suggestions, not requirements: keep the current path if confident. (2026-10-20, M-20261020-015) **Resolved (2026-10-20, M-20261020-025): C1: later entry wins: env/reward variants allowed; C2: later entry wins: reward may change; the original DInos reward stays as reference arm; C3: stage B not required for sim results; calibration stays paused**
- Isolation: sim runs pinned to dedicated cores + one busy/quiet determinism check; real-cluster runs in a quiet window. (2026-10-17, R-20261017-017)

## Methods
- Classical scope: K8s HPA, DERP, DInos (no transfer), DInos+T. (2026-10-17, R-20261017-017)
- The K8s HPA comparator is reverse-engineered from the official Kubernetes docs/source. (2026-10-17, M-20261017-068)
- Exploratory W0 R-20261017-015 (old reward) is a pipeline test only; its numbers are not used for claims. (2026-10-17, R-20261017-017)

## Tuning sandbox and loop
- Tuning sandbox: full freedom without per-step approvals to try anything in the code on branch `dinos-tuning` (from qrl-dev) until the classical comparison (HPA, DERP, DInos, DInos+T) gives results close to the published DInos picture; if it does not work, return to qrl-dev. (2026-10-17, M-20261017-137)
- Sandbox guardrail: tune agents (hyper-parameters, training, architecture, features, bug fixes), not the simulator/reward/SLO (those change only from calibration evidence). (2026-10-17, M-20261017-137) **Resolved (2026-10-20, M-20261020-025): C1: later entry wins: env/reward variants allowed**
- Tuning on train/dev seeds only; final test seeds 20000+ run once with frozen configs. (2026-10-17, M-20261017-137)
- Sandbox runs go through a one-time "sandbox" approval in launch_run (branch, scope sim, seed ranges, CPU-hour budget). (2026-10-17, M-20261017-137)
- Absolute numbers of the old simulator (F1) are not a target; the target is the same qualitative ranking and curves. (2026-10-17, M-20261017-137) **Resolved (2026-10-20, M-20261020-025): C5: closeness % is a progress indicator for the researcher, not a paper result**
- After every tuning cycle report one closeness % to the paper sim picture (`code-tuning/tuning/closeness.py`: mean of DERP magnitude, DInos magnitude and DInos/DERP ratio vs 2.2e5 / 3.8e6 / 17.3x, log scale, 5-episode sums), with a sanity note (failed requests, latency) flagging degenerate policies; then start the next cycle immediately. (2026-10-19, M-20261019-029) **Resolved (2026-10-20, M-20261020-025): C5: closeness % is a progress indicator for the researcher, not a paper result**
