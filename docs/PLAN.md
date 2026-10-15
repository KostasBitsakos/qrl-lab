# QRL-Lab — Plan and Operating Manual

Version 0.1 · 2026-10-15 · owner: the researcher (Kostas). Maintainer: the coordinator (Claude Opus).

This file is the single source of truth for every agent working on this project, Claude and Codex alike.
Read it before acting. Only the coordinator edits it, and only §13 (decisions) and §11 (timeline status)
without asking; every other change goes through the researcher.

Markers used below:
- `[VERIFIED yyyy-mm-dd]` checked against code, docs or an official source on that date.
- `[TO VERIFY]` believed true, must be checked before anyone relies on it.
- `[DECISION PENDING]` the researcher has not decided yet. Do not act on it.

---

## 1. Goal and requirements

**Goal.** Produce the next paper of the PhD: a hybrid quantum–classical extension of the DInos autoscaler
(Kubernetes + Redis, Deep RL), evaluated first in simulation and then on the real cluster, submitted to a
conference by the end of November 2026.

**Requirements stated by the researcher** (do not reinterpret; ask if unclear):

| ID | Requirement |
|---|---|
| R1 | One conversation. The researcher talks only to the coordinator (Claude Opus). Claude and Codex **collaborate and exchange ideas until they agree on the best one**; Codex is a co-researcher, not only a reviewer. |
| R2 | As many agents as needed, no more, no fewer. Strong models only for hard tasks; cheap models for easy ones. Use the existing subscriptions (Claude **Pro**, ChatGPT **Plus**); buy nothing unless strictly necessary, and then ask first. |
| R3 | Work on the researcher's VM (OpenStack, reached over VPN + SSH; researcher has sudo). Agents need read access to all working directories (simulation and real-world code, YAMLs, configs) and must be able to run experiments and scale the Redis pods on Kubernetes, under the approval rules of §6. |
| R4 | Re-read the thesis and its planned next steps. Directions A and B are only indicative. **Take initiative** on which parts of the model to make quantum, or propose quantum additions not yet considered. Try several approaches until 2–3 give the best results on: better predictions, faster convergence (faster training), lower space and time complexity, better adaptation to new environments. |
| R5 | Never modify existing code. Copy into a new working directory / branch and work there. |
| R6 | Simulation first, then the real environment, as in the previous work. |
| R7 | Propose workload models beyond sine + noise + spikes (e.g. Poisson + spikes or better) and ask. |
| R8 | A paper is written in parallel as a template-agnostic scaffold, with careful related work. Another agent scouts venues (good tier, realistic deadlines). Target: submit mid/end of November 2026. Conferences only. Audience: both cloud/systems and quantum/QML. |
| R9 | A dashboard with live progress of experiments and code versions, charts, bars, and a live view of **which agent works on what**. The researcher proposes changes there and agents ask questions there. Notifications to phone (Claude app) or browser. |
| R10 | Agents propose a publication-readiness criterion and ask the researcher. Compare not only time complexity but also **space complexity, memory and disk** needs of the models. |
| R11 | Initiatives only after proposing and getting approval. |
| R12 | Do not guess. Ask. |
| R13 | This file. |
| R14 | Spend tokens carefully (memory, routing, scripts instead of LLM calls). |

**Autonomy agreed with the researcher (2026-10-15):** simulation runs are approved in batches; every
real-environment run is approved separately; every change outside the working copy is approved separately.

---

## 2. Findings in the existing code — read before any experiment

Source: GitHub `KostasBitsakos/K8s_Redis_DeepRL`, branch `evaluation`, commit `9a32518` (2026-10-15).
All findings `[VERIFIED 2026-10-15]` by reading the code and running it. Reproduce F1 with
`python3 -I tools/sanity_trivial_policies.py <dir-containing-environment.py>`.

### F1. The simulator rewards only "scale down to the minimum"
In every `environment*.py` used by the final scripts (`lstm_transfer/`, `Quantum/`, `HPA/`, `dense/`, …):
- `latency(t)` depends only on time `t` and noise, never on the number of VMs/pods;
- `cpu_usage(t)` and `memory_usage(t)` are `uniform(30,75)` / `uniform(40,65)` noise, independent of VMs;
- `load(t)` is exogenous; `capacity` depends on VMs but is **not in the reward**.

So the only action-dependent reward term is `-10 * num_vms`. The optimal policy is "always scale down".
Measured over 5000 steps, mean of 5 runs, `lstm_transfer/environment.py`:

| Policy | Mean reward |
|---|---|
| always scale down (→ 1 VM) | **728,358** |
| always no-op (6 VMs) | 478,458 |
| random | 306,296 |
| always scale up (→ 20 VMs) | −220,632 |
| *stored DInos+transfer models (final_metrics_lstm)* | 564,423 – 723,523 |
| *stored HPA results* | ≈ −207,000 |

The fixed "always scale down" policy beats every stored DInos+transfer model. The simulated HPA reacts to
uniform noise above its 50 % thresholds, so it drifts towards 20 VMs. `HPA/environment.py` gives the same
picture (728,402 for always scale down).

**Consequence.** Any model, including a tiny quantum circuit, can learn "always scale down". A quantum vs
classical comparison on this simulator would show fake parity ("same reward with 1000× fewer parameters").
Simulation v2 (§8.1) comes first. Real-cluster results are not affected by this finding.
Whether the published simulation figures came from these exact files is `[TO VERIFY]` on the VM; the
researcher decides how to handle that. Agents do not edit thesis or published material.

### F2. Transfer fine-tuning ran for only 1 of 5 models
`lstm_transfer/lstm_transfer.py` creates `env` once and never resets it before `fine_tune`.
After model_1's evaluation `env.time == 5000`, so fine-tuning of models 2, 5, 10 and 20 stops at step 0
(`done` is already true). The timing files confirm it: fine-tuning took 0.00–0.30 s for those models.

### F3. The agent is not Double DQN, and has three other defects
In `agentHuber.py` and `networks.py`:
1. The target is `reward + gamma * max_a Q_target(s', a)`: a plain DQN target. Double DQN takes
   `a* = argmax Q_online(s')` and evaluates `Q_target(s', a*)`.
2. `update_target_model()` runs at the end of every `replay()` call. The target network never lags.
3. The LSTM keeps `self.hidden` between forward calls. Replay samples are shuffled, so each sample's output
   depends on whichever sample came before. Each window should start from a zero hidden state.
4. Replay updates one sample at a time inside the minibatch loop (16 optimizer steps per call). Slow and
   high-variance.

### F4. The current "Quantum" variant is not a quantum model
- `Quantum/agentHuber.py`: a 4-qubit PennyLane circuit is used only to **sample the random exploration
  action** (the ε-branch). Its 16 weights get no gradient, because the loss does not depend on them.
  The Q-function is the same classical LSTM.
- `Quantum/quantum_optimizer.py`: "QuantumInspiredOptimizer" is SGD plus Gaussian noise. No quantum computation.
- `QuantumExp.py` defines a 2-qubit `quantum_act` that the main loop never calls.

Results match the classical ones (e.g. model_2: 718,387 vs 723,523). None of this can be presented as a
quantum model.

### F5. The model in the code differs from its description in the papers/thesis `[TO VERIFY]`
Code: `nn.LSTM(input=6, hidden=128, layers=3)` + `Linear(128→3)`, input window 10 × 6 features
(load, capacity, cpu, memory, latency, num_vms). Parameters: **334,211** (LSTM 333,824; head 387),
1.34 MB fp32, consistent with the stored `.pth` size. The thesis/paper description recorded earlier is
"LSTM 64 → Dense 128 → Dense 64 → Q-head" on a 5-dim state. Check the VM code and the papers; the new paper
must describe what actually runs.

Note for the quantum design: **99.9 % of the parameters are in the LSTM**. Replacing only the output head
with a circuit cannot reduce space.

### F6. Where the rest of the code lives
Neither `evaluation` nor `main` on GitHub contains Kubernetes/Redis code, YAMLs or real-world logs. They are
on the VM. The GitHub repository is **public** (anyone can read F1–F4).

---

## 3. Architecture

```
 Phone (Claude app)        Laptop browser            Laptop VS Code (Remote-SSH)
   push + chat           claude.ai/code + dashboard     terminal: tmux attach -t lab
        \                    |  (SSH tunnel :8501)          /
         \___________________|_____________________________/
                             |  same Remote Control session
                  ┌──────────▼───────────────────────────────────────── VM ──┐
                  │ COORDINATOR  Claude Code, Opus 5.5, in tmux "lab"        │
                  │   ├─ Claude subagents: Explore(Haiku) runner(Haiku)      │
                  │   │   engineer(Sonnet) scholar(Sonnet) writer(Sonnet)    │
                  │   ├─ Codex: plugin codex@openai-codex + `codex mcp-server`│
                  │   ├─ lab-bridge plugin monitor ← .lab/inbox.jsonl        │
                  │   └─ hooks → .lab/events.jsonl (agent timeline)          │
                  │ Experiments (nohup/tmux, checkpoints) → .lab/lab.db      │
                  │ Dashboard (Streamlit, 127.0.0.1:8501) ↔ .lab/*           │
                  │ K8s + Redis (real environment)    IBM Quantum (outbound) │
                  └──────────────────────────────────────────────────────────┘
```

**Why the coordinator runs on the VM, not the laptop.**
- Remote Control needs the `claude` process to keep running; on a remote machine it must run inside tmux.
  The laptop sleeps and closes, the VM does not. `[VERIFIED 2026-10-15, Remote Control docs]`
- Agents must read the VM's directories, run experiments and call `kubectl`. On the VM these are local
  commands; from the laptop every action would be a quoted `ssh` call.
- The laptop then needs only VS Code, a browser and the VPN. Its Node 12 stops mattering.

**Access paths for the researcher.**
- Chat with the coordinator from any of: the VS Code terminal (`tmux attach -t lab`), claude.ai/code, or the
  Claude phone app. All three are the **same session** (Remote Control). `[VERIFIED: Pro supports Remote Control]`
- Phone works without VPN, because the VM connects outbound to Anthropic. The dashboard needs the VPN + SSH
  tunnel: `ssh -N -L 8501:127.0.0.1:8501 <vm>`, then open `http://localhost:8501`.
- Do **not** open separate Claude panels in VS Code for this project. They would be separate, uncoordinated
  sessions.

**Event paths.**
- researcher → coordinator: chat (any surface), or the dashboard inbox. The dashboard appends a JSON line to
  `.lab/inbox.jsonl`; the `lab-bridge` plugin monitor (`tail -n0 -F`) delivers it to the running session as a
  notification. Plugin monitors run for the whole interactive session. `[VERIFIED 2026-10-15, plugin docs]`
- coordinator → researcher: chat; `PushNotification` (desktop + phone when Remote Control is connected)
  `[VERIFIED]`; the dashboard request queue `.lab/requests.jsonl` (badge + optional browser notification
  while the tab is open).
- Channels (`--channels`) are not used: custom channels need a development flag during the research preview.

**Directory layout on the VM** (`~/qrl-lab`, a new local git repo; nothing pushed without approval):

```
~/qrl-lab/
  CLAUDE.md  AGENTS.md  .mcp.json  .claude/ (settings, agents, skills)
  docs/      PLAN.md  INVENTORY.md  VENUES.md  DECISIONS.md
  code/      git worktree of K8s_Redis_DeepRL on branch qrl-dev (from the confirmed baseline)
  sim/       Simulation v2 (if kept outside code/)
  dashboard/ Streamlit app
  paper/     LaTeX scaffold (sections/, generated/, refs.bib, venue mains)
  tools/     scripts, hooks, lab-bridge plugin
  .lab/      lab.db  events.jsonl  requests.jsonl  inbox.jsonl  council/  runs/
```
Original VM directories are added read-only through `permissions.additionalDirectories` after the inventory.

---

## 4. Agents and model routing

| Agent | Engine (default → escalation) | When | Writes to |
|---|---|---|---|
| **coordinator** (main session) | Opus 5.5, effort medium → high for design decisions | always | PLAN §11 §13, `.lab/requests.jsonl`, task routing |
| **Explore** (overrides built-in) | Haiku | code/log/directory search | summaries only |
| **runner** | Haiku | start/monitor approved runs, collect results | `.lab/runs/`, `lab.db` via scripts |
| **engineer** | Sonnet → Opus per call for circuit/simulator design | implementation, tests, dashboard | `code/`, `sim/`, `dashboard/`, `tools/` |
| **scholar** | Sonnet + web | related work, citation checks, venues (weekly) | `paper/refs.bib`, `paper/notes/`, `docs/VENUES.md` |
| **writer** | Sonnet → Opus per call for final prose | paper scaffold and sections | `paper/` |
| **Codex** | GPT-6 Sol (medium/high) → GPT-6 Astra only for major council items and final adversarial review | council, implementation share, cross-review | assigned paths only |

Model names on the Codex side must match the account's real picker (`/model` in Codex). `[TO VERIFY]`

**Budget policy (R2, R14).**
1. Scripts first. Metrics collection, plotting, parsing logs, run monitoring, result tables: Python, not LLM.
2. The coordinator does not read large files or logs itself. It delegates to Explore (Haiku) and receives a summary.
3. At most 3 concurrent subagents; subagents cannot spawn subagents (settings.json).
4. Escalate to Opus/Astra only with a stated reason, logged in the event stream.
5. Balance quotas: when Claude Pro's window runs low, implementation moves to Codex (separate ChatGPT Plus quota),
   and vice versa.
6. Weekly: `/usage` on Claude and the rate-limit view in Codex. If Pro's window is exhausted on most days in
   week 1, the coordinator brings the researcher three options: `opusplan`/Sonnet coordinator, usage credits,
   or Max. Nothing is bought without explicit approval.
7. Memory that saves tokens: this file, `CLAUDE.md`, `AGENTS.md`, `docs/DECISIONS.md`, scholar's project memory,
   and Claude Code's built-in auto memory. No third-party memory plugins (they inject context every session).
   `pyright-lsp` gives symbol navigation instead of whole-file reads.

---

## 5. Claude ↔ Codex collaboration

Four modes. The coordinator picks one per task and logs it.

1. **Council** (skill `council`): for any decision that changes the research. Blind proposals from both sides,
   cross-critique, one revision, synthesis into a decision card with the points of agreement and disagreement.
   The researcher decides. Max two rounds unless the researcher asks for more.
2. **Pair**: one implements, the other reviews the diff before it is used for results. Who implements depends
   on quota and fit (Codex tends to take the quantum circuit code; Claude the simulator and orchestration).
3. **Delegate**: a self-contained task goes to Codex via `/codex:rescue --background` and returns via
   `/codex:result`.
4. **Adversarial review** at milestones: `/codex:adversarial-review` on the method, the experiment protocol and
   the paper claims. The automatic review gate stays **off** (the plugin warns it can loop and drain limits).

Interfaces:
- Official OpenAI plugin `codex@openai-codex`: `/codex:review`, `/codex:adversarial-review`, `/codex:rescue`
  (`--background --wait --resume --fresh --model --effort`), `/codex:status`, `/codex:result`, `/codex:cancel`,
  `/codex:setup`. Needs Node ≥ 18.18 and the local Codex CLI. `[VERIFIED 2026-10-15, plugin README]`
- `codex mcp-server` registered in `.mcp.json`: tools `codex` (new thread) and `codex-reply` (continue a thread)
  let the coordinator hold a multi-turn discussion directly. `[TO VERIFY in smoke test S3: tool names, threadId,
  sandbox/approval parameters on codex-cli 0.162.1]`
- Shared rules: `AGENTS.md` (Codex reads it natively; Claude Code also loads it as project instructions).

---

## 6. Approvals and autonomy

| Action | Rule |
|---|---|
| Read any project file, run read-only commands, `kubectl get/describe/logs/top` | automatic |
| Edit inside `~/qrl-lab` (code worktree, sim, dashboard, paper, tools) | automatic, logged; non-trivial diffs get a Codex or Claude cross-review before producing results |
| Simulation runs | **batch approval**: the coordinator submits a run spec (configs, seeds, est. CPU-hours, wall-clock); the researcher approves the batch |
| New experiment family, new model architecture, simulator/reward change, workload change | **proposal + approval** (council first) |
| Any real-environment run (K8s/Redis), `kubectl apply/scale/delete/patch`, Helm | **per-run approval**; namespace and context named in the request; resource limits and rollback stated |
| IBM Quantum hardware jobs | **per-job approval** with estimated QPU seconds |
| Changes outside `~/qrl-lab` (original dirs, system packages, `sudo`) | **per-item approval** |
| `git push`, publishing anything, sharing data outside the VM | **per-item approval** |
| Reading secrets (`~/.ssh`, tokens, `.env`, `~/.codex/auth.json`, IBM credentials) | **forbidden** |
| Inventing numbers, citations or results | **forbidden** |

An approval covers exactly what it lists. It is never a blanket permission.

---

## 7. Dashboard

**Tech.** Streamlit + Plotly, bound to `127.0.0.1:8501`. State in `.lab/lab.db` (SQLite) and the JSONL streams.
Built once by the engineer from this spec; updates by refresh, no LLM tokens.

**Tabs.**
1. **Overview** — current phase, timeline vs CCGrid deadlines, open requests count, last events.
2. **Runs** — live table of runs (status, progress bar, ETA, seed, config hash, code commit); live reward/loss
   curves; stop button that files a request (never kills directly).
3. **Compare** — pick runs or code versions; reward, SLA violations, p95/p99 latency, pods over time;
   bootstrap CIs; parameter count, checkpoint size, peak RAM, wall-clock, env steps to target.
4. **Agents** — swimlane timeline per agent (coordinator, subagents, Codex threads) from `events.jsonl`:
   who is working, on what, which model, duration; a graph view task → agent → artifact.
5. **Inbox** — requests from agents (approval / question / proposal) with Approve / Reject / Request changes +
   comment; a free-text box for the researcher's own proposals. Writes to `.lab/inbox.jsonl`.
6. **Resources** — VM CPU/RAM/GPU/disk, K8s pods and nodes in the experiment namespace.
7. **Quantum** — per model: qubits, depth, gate counts, two-qubit gates, shots, circuit evaluations per decision,
   simulator time per update; IBM jobs and QPU seconds used.
8. **Paper & venues** — section status, claim → evidence table, venue table with deadlines.
9. **Budget** — Claude and Codex usage notes; escalations log. `[optional: Claude Code OpenTelemetry token metrics]`

**Notifications.** Phone: `PushNotification` from the coordinator via Remote Control. Browser: the dashboard
raises a notification for new requests while its tab is open (cannot work with the tab or laptop closed).

**Security.** Bound to localhost; reached only through the SSH tunnel. Exposing it beyond the VM needs a
security review and the researcher's approval.

---

## 8. Research plan

### 8.1 Simulation v2 (first deliverable) `[DECISION PENDING: design approval]`
Per control step (15 s, as DInos):
- arrivals `λ(t)` from the workload model (§8.2);
- capacity `c · μ`, `c` = Redis pods, `μ` = ops/s per pod **calibrated from the real cluster** (existing real-world
  logs, or a short approved load test);
- latency from a queueing model (M/M/c / Erlang-C) or a curve fitted to real measurements; CPU ≈ utilisation
  `ρ = λ / (c μ)` plus noise; memory from dataset size plus noise;
- **pod start-up delay** of `d` steps, so that proactive scaling pays off (this is what the LSTM is for);
- reward `= −α·c − β·1[latency > SLO] − γ·|Δc|` (cost, SLA, churn), weights agreed with the researcher.

Sanity gates before any comparison: "always min", "always max" and "static best `c`" must lose to a tuned
threshold policy; an oracle that knows `λ(t+h)` gives the upper bound. `tools/sanity_trivial_policies.py`
is extended to Sim v2.

### 8.2 Workloads `[DECISION PENDING]`
- **W0** sine + noise + spikes: continuity with previous work.
- **W1** non-homogeneous Poisson with a daily `λ(t)` + MMPP bursts (normal/burst regimes). Plain Poisson with a
  constant rate is memoryless: it removes the temporal structure the LSTM exploits, so it is not on its own more
  realistic.
- **W2** replay of a public production trace (candidates: Wikipedia pageviews, Azure Functions 2019, Alibaba
  cluster trace; scholar checks licences), scaled to the Redis capacity. Train on W0/W1, test on W2.
- **W3** regime shift (pattern changes mid-run): measures adaptation, for the transfer story.

### 8.3 Baselines — answer to the researcher's question
DInos+transfer is the main baseline. Earlier models (DERP, dense DDQN, plain LSTM) are not re-run; the paper
summarises in one paragraph where DInos+transfer beat them and cites the earlier papers, using **real-cluster**
numbers (the old simulation numbers are affected by F1). Add, cheaply:
- **HPA** (threshold on real utilisation in Sim v2): systems reviewers expect it.
- **Parameter-matched classical model** (small GRU/MLP with the same parameter count as the quantum model).
  Without it, a parameter reduction cannot be attributed to the quantum part.
- **Frozen-encoder classical fine-tuning** with the same number of trainable parameters (control for QC4).
- Trivial bounds (always min/max, static best, oracle) as sanity rows.
- DInos+transfer re-trained on Sim v2 with F2/F3 fixed (as "DInos+T (fixed)"), and the as-is version for reference.

### 8.4 Quantum candidates (proposal for council + researcher)

| ID | Idea | What becomes quantum | Targets (R4) | Trainable params (order) | Sim cost | Risk |
|---|---|---|---|---|---|---|
| QC1 | Full VQC Q-function with data re-uploading over the window (time steps re-uploaded sequentially), trainable input and output scaling | whole Q-function | space ↓↓, convergence? | 10²–10³ | low (6–8 qubits) | expressivity on bursty loads |
| QC2 | Quantum LSTM (VQCs inside the gates), small hidden size | recurrent core | predictions, convergence | 10²–10³ | high (many circuits per window) | slow in simulation |
| QC3 | Small classical GRU (h = 8–16) → dressed VQC head | encoder shrinks, head quantum | space ↓, accuracy kept | 10³ | low | gain may be classical (needs §8.3 control) |
| QC4 | Quantum fine-tuning for sim→real transfer: classical encoder pretrained in sim and frozen; only a small VQC is trained in the target environment | adaptation layer | adaptation ↑, transfer payload ↓, fine-tuning steps ↓ | 10¹–10² | low | must beat classical frozen-encoder control |
| QC5 | Quantum reservoir / extreme learning machine forecaster: fixed random circuit as temporal feature map, ridge readout solved in closed form; forecasts of `λ(t+h)` added to the DInos state | workload predictor | predictions ↑, training time ↓ | readout only | medium | must beat a classical echo-state network |
| QC6 | Regime detector from QuantuML (swap-test similarity / quantum k-means over workload windows); regime ID as state feature or to pick a policy from a library | context module | adaptation ↑ | ~0 trainable (clustering) | low–medium | ties all three thesis contributions |
| QC7 | Direction B as written: swap-test similarity as attention weights over the window | attention | predictions? | small | very high (O(k²) circuits per step) | stretch goal / second paper |

Coordinator's recommendation to discuss: screen QC1, QC3, QC4, QC5, QC6 (QC2 light version if time allows);
QC4 + QC1 are the most likely publishable pair, because they map directly onto the "faster adaptation" and
"smaller model" claims and have clean classical controls.

Implementation notes: keep PennyLane (already used) with `lightning.qubit` + adjoint differentiation for
training, analytic expectations; shot noise and device-noise models as separate experiments; Qiskit only where
needed for IBM execution. Vectorise the replay update (F3.4) before any timing comparison.

### 8.5 Screening (one week)
Sim v2, W0 + W1, 3 seeds, fixed budget of environment steps, same hyper-parameter search budget per candidate.
Report: final evaluation reward, SLA violation rate, p95 latency, env steps to 90 % of final reward, trainable
parameters, checkpoint bytes, update wall-clock, circuit evaluations per decision. The researcher picks 2–3.

### 8.6 Full evaluation
≥ 5 seeds (10 if cheap), W0–W3, ablations (encoding, layers, re-uploading, output scaling, entanglement on/off),
bootstrap 95 % CIs, the controls of §8.3.

### 8.7 Real environment
Same K8s/Redis setup as DInos (YAMLs on the VM, discovered in the inventory). VQC evaluated on a local
simulator on the VM; the decision loop must fit in the 15 s step. Every run approved separately (§6).

### 8.8 IBM Quantum hardware `[DECISION PENDING: plan and QPU minutes available]`
Validation, not training: run the trained circuit on recorded states, report action agreement with the
simulator, circuit depth after transpilation, shots, QPU seconds, latency incl. queue. Quantum wall-clock
speed-up is **not** claimed from simulator timings.

---

## 9. Metrics and publication gate (draft — the researcher sets the thresholds)

**Space:** trainable parameters; checkpoint bytes; transfer payload (bytes of fine-tuned parameters); peak
training RAM (measured, reported separately from model size); qubits, depth, gates, two-qubit gates.
**Time:** env steps to target reward (hardware-independent sample efficiency); training wall-clock to target;
inference latency per decision (classical measured; quantum: simulator measured + hardware estimate stated as
an estimate).
**Quality:** reward and its decomposition, SLA violation rate, p95/p99 latency, mean pods, scaling actions,
stability across seeds.

Gate (proposal):
- G1 Sim v2 passes the sanity gates of §8.1.
- G2 Convergence: moving-average reward changes < 2 % over the last 10 % of training, all seeds (≥ 5).
- G3 Non-inferiority to DInos+T (fixed) on SLA violations and p95 latency within δ = 5 % (95 % bootstrap CI), W1 and W2.
- G4 At least one superiority result with CI excluding zero: ≥ 10× fewer trainable parameters with G3, or fewer
  env steps to target, or faster adaptation under W3 / sim→real.
- G5 The parameter-matched classical control does not explain the gain. If it does, the honest claim changes
  to "small models suffice" and the paper is reframed.
- G6 The real cluster reproduces the ranking (not necessarily the absolute numbers).
- Nice to have: IBM hardware action agreement reported.

---

## 10. Paper and venues

**Primary candidate (deadline fits R8):** IEEE CCGrid 2027 (27th IEEE International Symposium on Cluster,
Cloud and Internet Computing), Dallas-Fort Worth, May 24–27 2027.
Abstract **Nov 24 2026**, paper **Dec 1 2026** (AoE); up to 10 pages incl. references, IEEE template;
Track 1 covers quantum and emerging systems, Track 2 covers resource management incl. autoscaling;
the 1st IEEE International Conference on Quantum Systems (QSys 2027) is co-located.
`[VERIFIED 2026-10-15 from the EasyChair CFP]` CORE rank and QSys 2027 deadlines `[TO VERIFY by scholar]`.

Scholar maintains `docs/VENUES.md`: venues with deadlines between 2026-11-15 and 2026-12-31, official CFP link,
deadline with timezone, ranking with its source (CORE 2023/2026, CCF), fit for both audiences, page limit,
blind/double-blind, travel/registration notes. Dates only from official CFPs.

**Scaffold.** `paper/sections/*.tex` shared by all venues; thin `main-ieee.tex`, `main-acm.tex`, `main-lncs.tex`.
Every number comes from `paper/generated/results.tex` (macros written by a script from `lab.db`); figures from
scripts. A claim → evidence table (`paper/claims.md`) links each claim to runs. Related work: every citation
verified by DOI/arXiv/DBLP link; nothing from memory.
Style (researcher's preferences): short and varied sentences, concrete examples, direct academic tone; no
symmetric "not X but Y" constructions, no generic punchlines, no self-promotion.

---

## 11. Timeline to CCGrid (status updated by the coordinator)

| Week | Dates (2026) | Work | Status |
|---|---|---|---|
| 0 | Oct 15–18 | VM setup, smoke tests S1–S6, read-only inventory, confirm baseline, decisions D1–D8 | open |
| 1 | Oct 19–25 | Sim v2 + calibration + sanity gates; fix F2/F3 in `qrl-dev`; dashboard v1; scaffold + related work start | open |
| 2 | Oct 26–Nov 1 | DInos+T (fixed) on Sim v2; screening of quantum candidates; researcher picks 2–3 | open |
| 3 | Nov 2–8 | Full simulation evaluation + ablations + controls | open |
| 4 | Nov 9–15 | Real-cluster runs; IBM hardware validation | open |
| 5 | Nov 16–22 | Results freeze (Nov 17), figures, writing; Codex adversarial review | open |
| 6 | Nov 23–Dec 1 | Abstract Nov 24, polish, submit Dec 1 | open |

Risk: Sim v2 may change the ranking of the classical baselines. If DInos+T (fixed) does not beat HPA on Sim v2,
the coordinator stops and brings it to the researcher before any quantum work continues.

---

## 12. Setup and smoke tests

Done by the researcher on the VM with the coordinator's guidance (see chat for the exact commands):
1. `tools/vm_check.sh` (read-only) → paste the output.
2. Claude Code on the VM + `/login`; Node LTS via nvm (user-local); Codex CLI; `codex login --device-auth`
   (device-code login must be enabled in ChatGPT settings → Security) `[TO VERIFY]`.
3. Create `~/qrl-lab` from this kit; `/plugin marketplace add openai/codex-plugin-cc`,
   `/plugin install codex@openai-codex`, `/codex:setup`; `pyright-lsp@claude-plugins-official` + pyright.
4. `tools/start-coordinator.sh`, enable push notifications in the Claude app.

Smoke tests (pass before touching research code):
- **S1** `/codex:setup` reports Codex installed and authenticated.
- **S2** In `sandbox/` (dummy file, no private data): `/codex:rescue --wait` read-only review → `/codex:result`.
- **S3** `/mcp` shows `codex` connected; coordinator starts a thread with `codex`, continues it with `codex-reply`.
- **S4** `council` dry run on a toy question; decision card appears in `.lab/requests.jsonl`.
- **S5** `python3 tools/labq.py say "ping"` → coordinator reacts without being prompted (monitor works);
  `PushNotification` reaches the phone.
- **S6** a subagent task produces lines in `.lab/events.jsonl` with `SubagentStart/SubagentStop`.

Then: read-only inventory of the VM (Explore) → `docs/INVENTORY.md` with evidence for the latest version
(git history, job scripts, logs, checkpoints, configs, timestamps — not folder dates alone) → the researcher
confirms the baseline → `git worktree add` for `qrl-dev`.

---

## 13. Decisions and open questions

| ID | Question | Status |
|---|---|---|
| D1 | Coordinator on the VM in tmux, accessed via Remote Control (not on the laptop) | proposed |
| D2 | Simulation v2 design and reward weights (§8.1) | pending |
| D3 | Workloads W0–W3 (§8.2) | pending |
| D4 | Baselines (§8.3) | proposed; researcher agreed on DInos+T as main |
| D5 | Quantum candidates to screen (§8.4) | pending |
| D6 | Publication gate thresholds (§9) | pending |
| D7 | Target venue CCGrid 2027 + alternatives from scholar | pending |
| D8 | How to handle F1/F5 with respect to published work and the public repo | researcher only |
| D9 | IBM Quantum plan / QPU minutes | pending |
| D10 | Kubernetes version, namespace and context for real runs | from inventory |

Accepted decisions are copied to `docs/DECISIONS.md` with date and who decided.

---

## 14. Data formats

`.lab/requests.jsonl` (agents → researcher), one object per line:
`{"id":"R-20261015-001","ts":"...","from":"coordinator","kind":"approval|question|proposal|info",
  "title":"...","body":"markdown","options":["approve","reject","changes"],"blocking":true,
  "cost":"est. CPU-h / QPU-s / tokens","links":["runs/...","council/..."]}`

`.lab/inbox.jsonl` (researcher → agents):
`{"id":"I-...","ts":"...","reply_to":"R-...|null","decision":"approve|reject|changes|null","text":"..."}`

`.lab/events.jsonl` (hooks, no secrets, truncated):
`{"ts":..., "hook_event_name":"PreToolUse", "agent_type":"engineer", "tool_name":"Edit", "summary":"code/sim/env_v2.py"}`

Runs: `.lab/runs/<run_id>/` with `spec.yaml` (code commit, config hash, seed, workload, model),
`metrics.jsonl` (step-level), `summary.json`; registered in `lab.db`.
