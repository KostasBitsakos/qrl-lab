# QRL-Lab — Plan and Operating Manual

Version 0.2 · 2026-10-16 · owner: the researcher (Kostas). Maintainer: the coordinator (Claude Opus).
Changes since 0.1: see `CHANGELOG.md` (Codex only through the official plugin; dashboard v1 with two-way messaging;
approval enforced by the run launcher; F7).

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
`vm_check` (2026-10-15) lists candidate directories: `~/simulations` (git repo `redisk8s`), `~/redis`
(git repo `autoscaling-redis-cluster-hpa-kubernetes`), `~/k8s`, `~/prometheus-grafana`, and `~/all.zip` (2024-04).
Which of them produced the published runs is `[TO VERIFY]` in the inventory. ChatGPT independently confirmed
F1–F5 at code level on the same commit (2026-10-16).

### F7. The Kubernetes API server is not reachable `[VERIFIED 2026-10-15, vm_check]`
`kubectl` (client v1.28.2, context `kubernetes-admin@kubernetes`) gets `connection refused` from
`10.0.1.28:6443`. The cluster must be brought back up (by the researcher, or by an agent with per-item
approval) before any real-environment work. Simulation work does not depend on it.

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
                  │   ├─ Codex: plugin codex@openai-codex (codex-rescue)     │
                  │   ├─ lab-bridge monitor ← .lab/lab.db (new messages)     │
                  │   └─ hooks → .lab/events.jsonl (agent timeline)          │
                  │ launch_run.py (checks approval) → runs → .lab/runs/      │
                  │ Dashboard (Streamlit, 127.0.0.1:8501) ↔ .lab/lab.db      │
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
- researcher → coordinator: the dashboard writes the message to `.lab/lab.db` (status `new`). The `lab-bridge`
  plugin monitor (`tools/lab_bridge_watch.py`, runs for the whole interactive session) prints one `QRL-INBOX` line
  per new message, which Claude Code delivers to the session as a notification; status becomes `delivered`.
  Messages delivered but never taken are re-delivered when the session restarts. Chat on any surface also works.
- coordinator → researcher: `labq.py post` writes the reply into the same thread (visible in the dashboard),
  sets the status (`in_progress` / `waiting_approval` / `done` / `failed`); `PushNotification` for blocking items.
- decisions: the researcher decides in the dashboard (validated in `labdb.py`); the monitor prints `QRL-DECISION`.
- The dashboard heartbeat (`.lab/bridge_heartbeat`, written by the monitor) shows whether the coordinator is online.
- Channels (`--channels`) are not used: custom channels need a development flag during the research preview.

**Directory layout on the VM** (`~/qrl-lab`, a new local git repo; nothing pushed without approval):

```
~/qrl-lab/
  CLAUDE.md  AGENTS.md  CHANGELOG.md  SETUP.md  .claude/ (settings, agents, skills)  .streamlit/
  docs/      PLAN.md  INVENTORY.md  VENUES.md  DECISIONS.md
  code/      git worktree of K8s_Redis_DeepRL on branch qrl-dev (from the confirmed baseline)
  sim/       Simulation v2 (if kept outside code/)
  dashboard/ Streamlit app
  paper/     LaTeX scaffold (sections/, generated/, refs.bib, venue mains)
  tools/     scripts, hooks, lab-bridge plugin
  tests/     test_lab.py (plumbing tests)
  .lab/      lab.db  events.jsonl  bridge_heartbeat  specs/  outbox/  council/  runs/   (not in git)
```
Original VM directories are added read-only through `permissions.additionalDirectories` after the inventory.

---

## 4. Agents and model routing

| Agent | Engine (default → escalation) | When | Writes to |
|---|---|---|---|
| **coordinator** (main session) | Opus 5.5, effort medium → high for design decisions | always | PLAN §11 §13, dashboard threads and requests (`labq.py`), task routing |
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
3. **Delegate**: a self-contained task goes to Codex through the `codex:codex-rescue` subagent (background).
4. **Adversarial review** at milestones (method, experiment protocol, paper claims): the coordinator asks Codex
   through `codex-rescue` with a read-only adversarial prompt; the researcher can also type
   `/codex:adversarial-review` himself. The automatic review gate stays **off** (it can loop and drain limits).

Every Codex contribution that reaches the researcher is shown in the dashboard thread as **Codex**, separate from
the coordinator's synthesis. The ChatGPT web chat is not part of the system; it stays available to the researcher
for independent second opinions (connecting it would need a paid API and is out of scope).

Interfaces `[VERIFIED 2026-10-16 from the plugin source, v1.0.6]`:
- Official OpenAI plugin `codex@openai-codex`, the only Codex interface. `codex mcp-server` is deprecated since
  codex-cli 0.149.1 and is not used (the v0.1 `.mcp.json` is removed).
- The coordinator calls Codex through the Agent tool with `subagent_type: "codex:codex-rescue"`, which forwards to
  the plugin's `task` runtime: `--fresh` / `--resume` (continue the latest Codex thread in this repo), `--model`,
  `--effort`. Without `--write` the Codex sandbox is **read-only**; the forwarder adds `--write` unless the prompt
  asks for read-only, so every non-implementation prompt says `READ-ONLY`.
- `/codex:review`, `/codex:adversarial-review`, `/codex:status`, `/codex:result`, `/codex:cancel` have
  `disable-model-invocation: true`: only the researcher can type them (terminal or app). The coordinator gets
  reviews through `codex-rescue` with a read-only review prompt.
- Shared rules: `AGENTS.md` (Codex reads it natively; `CLAUDE.md` imports it with `@AGENTS.md`).

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

**Enforcement, not only instructions.**
- Experiments start only through `tools/launch_run.py`. It refuses unless the request is an approved `approval`
  whose frozen spec (`.lab/specs/R-….json`, read-only, sha256 recorded) is unchanged, the entry has attempts left,
  and, for scope `real`, the current kubectl context equals `real.kube_context`. A detached supervisor enforces
  `limits.wall_clock_hours` and the dashboard's stop requests.
- `.claude/settings.json`: auto permission mode with the classifier; `deny` for kubectl mutations, Helm, force
  push, edits to the original directories, edits to `.lab/lab.db` and `.lab/specs/`, `sqlite3`, and the researcher-only
  `labq.py decide/say`; `ask` for push, worktrees, sudo, installs, `rm -rf`, context switches.
- Decisions are validated in `tools/labdb.py` (allowed options per kind, text where required, researcher only,
  once). The dashboard never executes typed commands.
- Residual risk: all of this runs as the same Unix user, so it is a guard against mistakes, not an OS security
  boundary. For real-cluster runs, a namespace-scoped kubeconfig/service account is the next step (D11).

---

## 7. Dashboard

**v1 (implemented, `dashboard/app.py`, tested by `tests/test_lab.py`).** Streamlit + Plotly on `127.0.0.1:8501`,
state in `.lab/lab.db`; auto-refresh every 3–30 s (no LLM tokens). Text inputs are never inside auto-refreshing
parts, so typing is never lost. Greek UI.
1. **💬 Συνομιλία** — one ongoing chat, like a chat app: it opens on the most recently active thread («Κύρια συζήτηση»;
   created by the first message if none exists), messages oldest to newest with the newest at the bottom, and a
   `st.chat_input` at the bottom (Enter sends, Shift+Enter = new line; files are attached through the same input and
   saved under `docs/uploads/<message id>/`, max 200 MB each, listed in the body as `Συνημμένα:`; each attachment has a
   download button and a 📁 Αρχεία link, the QRL-INBOX line lists the paths, and files are never executed). New messages reply to the
   latest message of the current thread; a new thread only via «➕ Νέο θέμα»; the topic list is a collapsible
   expander. While your latest message is acknowledged/in_progress an isolated auto-refreshing fragment shows
   «⏳ ο συντονιστής δουλεύει…» plus the active agents; the input is never inside a fragment. Types: μήνυμα, πρόταση
   ιδέας, ερώτηση για τον κώδικα. Warns when a delivered message is not taken within 3 minutes. Every agent message
   shows its author and model («Codex · gpt-6-sol»); agents pass `labq.py post --model <free text>`.
   **Voice input** — `st.audio_input` («🎙️ Φωνητικό μήνυμα», outside any fragment) transcribes locally with
   faster-whisper (`tools/voice.py`; model `small`, env `QRL_WHISPER_MODEL=medium`; cpu, int8; Greek first, auto-language
   fallback; first use downloads the model from Hugging Face, no account). The text appears in an editable box with
   «Αποστολή» (same model/effort selectors, normal send path); the recording is kept as `docs/uploads/<M-id>/voice.wav`.
   Needs `av<17` with faster-whisper 1.2.1.
   **Codex deputy** — when health is `limit` (or `down` > 10 min) `health_watch` files one proposal «Να αναλάβει ο Codex
   μέχρι …;» (author `system`, de-duplicated: none while one is open or answered < 6 h ago). Only after the researcher
   approves it, `tools/deputy.py` (tmux window `deputy`, started by health_watch) takes new researcher messages as
   `codex-deputy`, runs `codex exec` read-only (sandbox read-only, approval never, gpt-6-sol, medium), and posts the
   Greek answer as «gpt-6-sol · αναπληρωτής». Answers needing execution set the message to `waiting_approval` and go to
   `.lab/deputy_queue.jsonl` for Claude. It stops (note in the threads, approval consumed) when health is `ok`.
0. **Health banner** — `tools/health_watch.py` (tmux window `health`, no LLM, every 20 s) classifies the coordinator pane
   (usage limit with reset time, permission prompt, API error/overloaded, coordinator not running) with a regex table,
   writes `.lab/health.json` and state changes to `.lab/events.jsonl`; the dashboard shows an exact Greek banner on
   every tab with the time since the state began.
2. **✅ Αποφάσεις** — open requests (blocking first) with body, attached files, the frozen run spec and its hash;
   Approve / Reject / Request changes (comment required for changes), Answer for questions; history.
3. **🤖 Πράκτορες** — who is working now (active subagents), timeline of actions per agent (fixed colour per agent,
   labelled lanes), counts, table of recent actions; banner when the coordinator waits for a permission prompt.
4. **📈 Πειράματα** — runs with status, progress bar, duration, approval id, code commit; metric curves from
   `metrics.jsonl` (up to 8 runs); stop request with confirmation.
5. **⚖️ Council** — brief, decision card, Claude's and Codex's proposals side by side.
6. **🖥️ Πόροι** — CPU, RAM, disk, load, GPU.
   **☸️ Kubernetes** — read-only (`tools/k8s_view.py`, verbs `get`/`version`/`config current-context` only, 5 s timeout, 10 s cache): KPI tiles, health badges, failing items with reasons, pods/deployments/services/nodes/HPAs; clear Greek message when the API server is down.
   **📡 Prometheus** — live, read-only (`tools/prom_view.py`: GET only on `query`, `query_range`, `label/__name__/values`;
   base URL `QRL_PROM_URL`, default `http://10.0.1.28:30000`). Curated PromQL catalogue by category (Node via cAdvisor
   root cgroup because the cluster has no node-exporter, Redis pods in `default`/`qrl-calib`, Kubernetes, Prometheus),
   9 default charts, per-category multiselects (entries without data are marked ⚠), an «Advanced» search over all
   metric names (counters shown as `rate(…[5m])`), range 15 m/1 h/6 h/24 h, Plotly, isolated fragment refreshing every 15 s
   with the selectors outside it.
   **📊 Grafana** — `st.iframe` (800 px) to `http://localhost:32000` (env `QRL_GRAFANA_URL`; VS Code → Ports → Forward 32000,
   login once in the frame; no credentials stored or guessed), «Άνοιγμα σε νέα καρτέλα» link, Explore quick links for the
   9 default Prometheus panels (default datasource). Importing a Redis/K8s dashboard needs the researcher's login: not done.
7. **🎓 Συνέδρια** (split from the former «Paper & συνέδρια» tab) — deadlines with countdown (`docs/deadlines.json`,
   verified sources only), `docs/VENUES.md`, `paper/claims.md`.
   **📝 Paper** — the «Paper — συγγραφή» chat with writer/reviewer selection, plus the manuscript tools (`tools/paper_build.py`, outside auto-refresh fragments): venue selector
   (IEEE/ACM/LNCS) + «Μεταγλώττιση» (latexmk, 120 s timeout, `-interaction=nonstopmode -halt-on-error`, output
   `paper/build/<venue>/`, last 40 log lines on failure), PDF viewer + download + build time, LaTeX source view over
   `paper/**/*.tex|.bib|.md` (read-only; «Επεξεργασία» + «Αποθήκευση» write only under `paper/`, realpath and
   deny-list checked, commit "paper: edit <file> from dashboard"), and status (`\todo` per section, `[TBD]` macros in
   `generated/results.tex`, claims.md rows). `llncs.cls` is not in Ubuntu TeX Live: the LNCS build needs Springer's
   author kit (`llncs.cls`, `splncs04.bst`) placed in `paper/`.
8. **🧾 Ιστορικό** — audit log of every send, take, decision, launch and stop.
9. **📁 Αρχεία** — read-only file browser (`tools/file_view.py`) over `~/qrl-lab`, `~/simulations`, `~/redis`, `~/k8s`, `~/prometheus-grafana`: realpath-confined, credential deny list, previews (text/csv/image/pdf/binary sha256); deep link `?path=<abs>&line=N`; paths in chat messages render as links. Not inside a fragment.
Planned for v2 (when data exists): quantum resource panel (qubits, depth, gates, shots, circuit calls per decision),
compare view with bootstrap CIs, budget/usage notes.

**Experiment telemetry contract.** A run writes to `$QRL_RUN_DIR`: `metrics.jsonl` (one JSON object per line with
`step` and numeric metrics such as `reward`, `loss`, `sla_violation_rate`, `p95_latency`, `pods`) and optionally
`progress.json` (`{"step": n, "total": N}`). The launcher writes `spec_entry.json`, `output.log`, `launcher.json`.

**Notifications.** Phone: `PushNotification` from the coordinator via Remote Control (best effort). In the browser:
sidebar counters and toasts while the tab is open. The stored request state in the database is the source of truth.

**Security.** Bound to localhost; reached only through the SSH tunnel. Exposing it beyond the VM needs a
security review and the researcher's approval.

**Sudo tab (🔐, `tools/sudo_ui.py`).** Requests with scope `sudo` (the `sudo ...` lines of the body are the commands; programs are
derived from them with `sudo_gate.sudo_programs`, never typed in the UI). «Έγκριση» runs `sudo_grant.py open <R-id> --programs … --minutes N`
(default 30, max 240) from the dashboard process, which needs `sudo -n`; without it the exact command is shown for the ⌨️ Terminal tab.
The tab also shows `sudo_grant.py status`, a «Κλείσιμο» button and the last 50 entries of `.lab/sudo_audit.jsonl`. **Residual risk:**
the dashboard and the agents run as the same Unix user, so an agent that can reach the dashboard port (or run `sudo -n`
itself where sudoers allows it) is not isolated from the approval path; the protections are the root-owned grant file, the
`NEVER` program list, the PreToolUse hook, the audit log and the localhost-only binding, not a privilege boundary.

**Health watchdog.** `health_watch.py` logs its own exceptions and start/exit to `.lab/health_watch.log` and writes
`.lab/health_watch.heartbeat` each cycle; `tools/watchdog.sh` (user crontab, every minute) recreates the tmux windows
`health` (also when the heartbeat is older than 180 s) and `dashboard` if missing; it never starts the coordinator.
Codex usage limits (`tools/codex_health.py`, pattern table; called by `deputy.py`, or by the coordinator for failures seen
through the plugin) are stored under the `codex` key of `.lab/health.json` and shown as a separate banner.

**Terminal tab (⌨️, `tools/web_terminal.py`).** A full bash login shell in `~/qrl-lab`, i.e. full control of the VM for
whoever can reach the port, which means whoever holds the SSH tunnel / VS Code port forward. Mitigations: on demand only
(started by «Άνοιγμα terminal» in tmux window `terminal`, stopped by «Κλείσιμο»); listens on 127.0.0.1:8502 only; every
request and the websocket need a random token generated at each start (`.lab/terminal_token`, mode 600, removed at exit);
websocket origin restricted to localhost; exits after 30 min without input. Shell commands typed there bypass the
launcher, hooks and approvals, so the golden rules still apply to the person typing. xterm.js is loaded from
cdn.jsdelivr.net (pinned 5.3.0), the browser needs internet for it.

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
7 tracks (CFP checked 2026-10-16; likely fit Track 3 Systems for AI/ML or Track 5 Performance, see docs/VENUES.md);
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
| 0 | Oct 15–18 | VM setup, acceptance tests T0 and A1–A8 (§12), read-only inventory, confirm baseline, decisions D1–D8 | open |
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

Steps for the researcher: `SETUP.md` (Greek). Acceptance tests (adopted from the ChatGPT handoff of 2026-10-16).
Nobody claims the system works until the relevant tests pass on the VM:

| Test | Pass when | Status |
|---|---|---|
| T0 | `.venv/bin/python tests/test_lab.py` → `ALL PASSED (6)` on the VM (plumbing without Claude) | pass 2026-10-16 (now 7 tests) |
| A1 | `codex login status` on the VM says logged in; `/codex:setup` passes | pass 2026-10-16 (researcher) |
| A2 | Coordinator sends a read-only task on `sandbox/demo.py` to Codex (`codex-rescue`), gets the answer, and a `--resume` follow-up works | pass 2026-10-16 (thread M-20261016-001) |
| A3 | One coordinator session in tmux, reachable from claude.ai/code and the phone; no duplicate sessions | open |
| A4 | "hello dashboard" sent from the dashboard gets a visible reply in its thread, including a Codex contribution when asked | pass 2026-10-16 on redo (thread M-20261016-001); first attempt failed |
| A5 | A test approval request appears in the dashboard; reject → `launch_run.py` refuses; approve → a toy run starts and shows in Πειράματα | open |
| A6 | Coordinator offline → dashboard says offline and keeps the message `new`; after restart it is delivered | open |
| A7 | Every run directory has spec, code commit, seed, metrics; originals untouched (`git status` clean in original repos) | open |
| A8 | Dashboard reachable only through the SSH tunnel; no secrets in git or `.lab/events.jsonl` | open |

Until A4–A5 pass, the terminal/app remain the primary interface. Until A1–A3 pass, the Claude–Codex link is not
claimed to work.

Then: read-only inventory of the VM (Explore) → `docs/INVENTORY.md` with evidence for the latest version
(git history, job scripts, logs, checkpoints, configs, timestamps — not folder dates alone) → the researcher
confirms the baseline → `git worktree add` for `qrl-dev`.

---

## 13. Decisions and open questions

| ID | Question | Status |
|---|---|---|
| D1 | Coordinator on the VM in tmux, accessed via Remote Control (not on the laptop) | proposed |
| D2 | Simulation v2 design and reward weights (§8.1) | design accepted 2026-10-16 (C-20261016-01, option 1); weights/SLO pending |
| D3 | Workloads W0–W3 (§8.2) | accepted 2026-10-17 (R-20261017-008): W0+W1 train, W2 test, W3 adaptation |
| D4 | Baselines (§8.3) | proposed; researcher agreed on DInos+T as main |
| D5 | Quantum candidates to screen (§8.4) | accepted 2026-10-17 (R-20261017-006): screen QC4 + QC1, keep the better |
| D6 | Publication gate thresholds (§9) | pending |
| D7 | Target venue CCGrid 2027 + alternatives from scholar | pending |
| D8 | How to handle F1/F5 with respect to published work and the public repo | decided 2026-10-17 (R-20261017-007): not mentioned in the paper; DInos claims unchanged |
| D9 | IBM Quantum plan / QPU minutes | accepted 2026-10-16: account exists; hardware only when models are ready, per-job approval |
| D10 | Kubernetes version, namespace and context for real runs | from inventory |
| D11 | Bring the K8s cluster back up (F7); namespace-scoped credentials for agent-launched real runs | pending |
| D13 | Planning-chat handoff 2026-10-16: environment facts and standing rules (`docs/DECISIONS.md`) | accepted by the researcher |
| D12 | ChatGPT handoff 2026-10-16 adopted: codex mcp-server dropped, approvals enforced in the launcher, acceptance tests A1–A8 | accepted by the researcher (applied the .mcp.json change) |

Accepted decisions are copied to `docs/DECISIONS.md` with date and who decided.

---

## 14. Data formats

`.lab/lab.db` (SQLite, WAL; schema and transitions in `tools/labdb.py`; CLI `tools/labq.py`):
- `messages(id M-YYYYMMDD-NNN, thread_id, reply_to, author researcher|coordinator|codex|agent:<name>,
  kind message|proposal|code_question|reply|contribution|status, body, status, delivered_count)`;
  status of researcher messages: new → delivered → acknowledged → in_progress | waiting_approval → done | failed.
- `requests(id R-…, kind approval|question|proposal|info, scope sim|real|qpu|research|external|other, title, body,
  options, blocking, cost, links, thread_id, spec_path, spec_hash, state open|approved|rejected|changes_requested|
  answered|acknowledged|withdrawn, decision_text, decided_at, decision_delivered)`.
- `runs(run_id, request_id, spec_hash, entry, attempt, scope, cmd, cwd, run_dir, code_sha, status
  starting|running|done|failed|stopped, pid, exit_code, stop_requested, …)`.
- `audit(ts, actor, action, target, detail)`.

Run spec (attached to an approval with `labq.py ask --spec`; frozen at filing):
`{"name", "scope": "sim|real|qpu", "cwd" (relative to ~/qrl-lab), "entries": [{"name", "seed", "cmd": [argv…]}],
  "max_parallel": 1, "max_attempts": 1, "limits": {"wall_clock_hours": h},
  "real": {"kube_context", "namespace", "rollback"}}` (`real` required for scope real).

`.lab/events.jsonl` (hooks, whitelisted fields, truncated, never tool outputs):
`{"ts":..., "hook_event_name":"PreToolUse", "agent_type":"engineer", "tool_name":"Edit", "summary":"code/sim/env_v2.py"}`

Runs: `.lab/runs/<run_id>/` with `spec_entry.json` (request, spec hash, entry, seed, code commit, limits),
`output.log`, `metrics.jsonl`, `progress.json`, `launcher.json`; registered in `lab.db`.
