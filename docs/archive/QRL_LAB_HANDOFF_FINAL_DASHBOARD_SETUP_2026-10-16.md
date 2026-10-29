# QRL-Lab — Handoff to Claude / Final Setup and Dashboard Roadmap

**Date:** 2026-10-16  
**Purpose:** Give Claude Code one accurate account of the researcher's preparations, ChatGPT's independently checked findings, outstanding verification, and the shortest safe path to **one researcher-facing dashboard** for Claude + Codex collaboration.  
**Status:** Planning and setup; **NOT a declaration that the multi-agent system or dashboard already works**.  
**Coordinator:** Claude Code (Opus for difficult decisions, economical routing for routine tasks).  
**OpenAI collaborator:** Codex CLI invoked from Claude via the official Codex plugin.  
**Researcher:** Sole approver of research changes, live-cluster experiments, publication claims and external sharing.

## 1. North-star goal and the important interface distinction

One dashboard at `http://localhost:8501` on the researcher's laptop (through an SSH tunnel) should eventually let the researcher:

- submit questions, tasks and proposals **once**;
- receive a unified response coordinated by Claude after Claude–Codex collaboration, including both agents' opinions and disagreement when material;
- review/approve/reject specific, logged requests, with the ability to ask for changes;
- view active agents, experiment progress, results, model/code versions, resource usage, paper progress and conference deadlines;
- see notifications, with reliable stored request state even if a phone push is delayed or missing.

**Do not misrepresent this integration:** The existing ChatGPT conversation does not become a resident, live ChatGPT agent in the dashboard. **Codex** is the OpenAI research/coding participant invoked by Claude. This ChatGPT conversation remains available independently for human-requested second opinions, and has a GitHub connection. A direct dashboard ↔ ChatGPT conversation connection would require a separately authorized interface/API and might incur additional cost; it is **not** a prerequisite for v1 and must not be purchased or built without approval.

A Streamlit request inbox is not automatically a fully functioning two-way chat. Deliver and test the coordinator's **response path** as well as the inbound path, then confirm the researcher can work entirely from the dashboard for ordinary instructions. Claude Remote Control on web/mobile can remain a fallback and phone-notification interface.

## 2. What the researcher has already done (evidence levels)

### Directly shown in conversations or verified with tools

- Laptop Ubuntu has VS Code extensions for Claude Code, Codex, GitHub Copilot. Laptop CLI checks previously showed `claude 2.1.300`, `codex-cli 0.162.1` and **Node.js 12.22.9**, but those measurements were **on the laptop**, not proof of VM versions.
- Researcher accesses an Ubuntu **OpenStack VM** over VPN and SSH, commonly shown as `ubuntu@kbitsak-very-large`, and maintains the DInos / Redis / Kubernetes research code there.
- SSH GitHub authentication on that VM was fixed using a **dedicated Ed25519 key** (`~/.ssh/id_ed25519_github`). The `ssh -T ... git@github.com` challenge succeeded for GitHub account `KostasBitsakos`.
- Git history was amended to exclude a large Miniconda installer from the commit; GitHub independently shows branch `evaluation` at commit **`9a32518b7438b002a346028a47089ee4d87ab473`** with message `for the multi-agents systens` (2026-10-15). Original VM source and other branches should not be overwritten.
- Connected ChatGPT **GitHub plugin** is active. ChatGPT directly read the source code in repository `KostasBitsakos/K8s_Redis_DeepRL`, branch `evaluation`, commit above. The GitHub name `redisk8s` resolves to this repository via rename resolution.
- Claude supplied `PLAN.md` v0.1 and `qrl-lab-kit.zip`. The kit contains: `CLAUDE.md`, `AGENTS.md`, agent/skill definitions, hooks, `SETUP.md`, `tools/vm_check.sh`, `tools/start-coordinator.sh`, `tools/labq.py`, a monitor plugin, `tools/sanity_trivial_policies.py` and a **legacy** `.mcp.json`.
- The archive contains **no complete implemented Streamlit dashboard**. Its JSONL queue and monitor are proposed plumbing, not a proven live user interface.

### Reported by researcher; do not silently mark as verified

- The researcher states that the latest login/setup steps were performed, including Codex device authorization. Last **pasted** VM check was `codex login status` → `Not logged in`, **before** the researcher reported completing the subsequent steps. Therefore authentication must still be confirmed with a new `codex login status` output from **the VM**.
- Do not assert that `vm_check.sh` passed, VM Node >=18.18, Claude/Codex plugin installed, `tmux` running, Remote Control activated, or any smoke test passed: **none of those outputs has been provided to ChatGPT in this conversation**.
- Do not assume which original folder/commit/checkpoint produced the previously published DInos and real-cluster measurements; provenance is open.

## 3. Confirmed source-code findings requiring careful follow-up

Independent **read-only** review against `KostasBitsakos/K8s_Redis_DeepRL@evaluation:9a32518`:

1. **F1 – simulator reward issue, confirmed at code level:** `timeseries/Pytorch/lstm_transfer/environment.py` makes latency/CPU/memory independent of replica count; `capacity` changes with replicas but is not used in reward. The replica-dependent reward component penalizes number of VMs, favoring scale-down independent of service. Claude's numerical always-down reward table is **not independently re-executed here**.
2. **F2 – fine-tuning lifecycle, confirmed at code level:** `lstm_transfer.py` reuses one environment across `[1,2,5,10,20]`; evaluation resets it and leaves it at 5,000 steps, then later `fine_tune()` stops on `done` after a first step, before enough replay transitions accumulate for an optimizer update.
3. **F3 – DDQN/replay defects, confirmed at code level:** `agentHuber.py` evaluates `max_a Q_target(s',a)` instead of the Double DQN action-selection/evaluation split; target copied on every replay call; `networks.py` preserves LSTM hidden state across shuffled samples; replay performs per-sample optimizer steps.
4. **F4 – quantum model characterization, confirmed at code level:** `Quantum/agentHuber.py` uses a PennyLane quantum sampler in the epsilon-exploration branch, **not** in the differentiable Q-value/loss path; `quantum_weights` do not receive gradients from the learning objective; `QuantumInspiredOptimizer` is classical noisy gradient descent.
5. **F5 – actual architecture confirmed:** LSTM input=6, hidden=128, layers=3, output=3; **334,211 parameters**. The version that produced historical results and consistency with text in the thesis still need verification.

Read-only supporting report: `QRL_LAB_GITHUB_VERIFICATION_2026_10_16.md` (the researcher can share it). Do **not** automatically conclude published real-cluster experiments were invalid; independently audit precise code/checkpoint/measurement lineage first. Preserve original files and paper unchanged.

## 4. Architecture — minimal, no unnecessary model/API costs

```text
 Researcher laptop/browser (VPN + SSH tunnel)        Claude mobile/web (fallback + push)
                     |                                           |
                     v                                           v
             Streamlit Dashboard                         Claude Remote Control
           127.0.0.1:8501 on VM                                 |
                     |                                           |
       approvals, proposals, requests, agent responses           |
                     +---------------------+---------------------+
                                           |
                              Claude Code coordinator
                           (one session in tmux on VM)
                                           |
                       +-------------------+-------------------+
                       |                   |                   |
                  Codex plugin      Claude subagents        Python workers
                  Codex CLI         on demand only      metrics/run tracking
                       |                   |                   |
                       +-------------------+-------------------+
                                           |
                       isolated git worktree / run DB / artifacts
                             simulation → approved real K8s runs
```

**Initial staffing:** One Claude coordinator; one Codex collaborator accessible through official plugin; lightweight Explore and engineer subagents; scholar/writer invoked only when needed. No always-on LLM polling agent. Python performs persistent monitoring and dashboards. Escalate to expensive models with justification; obey each account's actual usage limits. Start with **at most one quantum simulation at a time**, increase only after resource tests.

**Runtime choice:** VM for the coordinator is reasonable because it persists after laptop disconnect and has local access to research files; verify the VM's network access, login status and quota. `tmux` alone does not keep a process alive across VM reboot; reconnect/resume on reboot and store checkpointed experiment state separately.

**Source of truth:** `docs/PLAN.md`, `CLAUDE.md` referring to `AGENTS.md`, `docs/DECISIONS.md`, versioned experiment run specifications and a structured run/approval database.

## 5. Concrete kit corrections BEFORE launch

1. **Disable the bundled `.mcp.json`:** It specifies `codex mcp-server`; do not rely on that old interface. Use the official plugin <https://github.com/openai/codex-plugin-cc>, which delegates via Codex App Server. No extra custom Codex MCP required initially.
2. Rewrite `docs/PLAN.md` S3 and `SETUP.md` to **test the plugin directly**, not `/mcp` expecting the obsolete `codex` / `codex-reply` server.
3. Update `council` skill to use actual working plugin actions and persist independent Claude/Codex proposals, criticisms and the final human decision. Do not promise automatic consensus; preserve meaningful disagreements.
4. Ensure `CLAUDE.md` and `AGENTS.md` are consistently loaded/tested; review effective `settings.json` permissions and hook behavior. Prohibit credential dumps.
5. Make approvals enforceable **at the execution boundary** with narrowly scoped credentials and an approved run launcher (immutable run spec, approval ID, cluster context, namespace, resources, time limit, stop/rollback). Prompt-level approval wording is insufficient security.
6. Keep all original research source directories read-only for agents where feasible. Create separate `qrl-dev` worktree **only after** baseline verification and approval. A worktree is version isolation, not an OS security boundary.
7. Keep `codex` plugin auto review gate **off** initially to avoid loops exhausting quota. Avoid extra skills, MCP servers, cloud subscriptions and API credentials unless tests show a genuine requirement.
8. For the dashboard: use **SQLite transactionally for request/approval/run state**, optional JSONL for event logs. Atomic IDs, acknowledgement status and an outbound coordinator message stream are required. An open tab or phone push is not a guarantee of delivery.

## 6. Practical next steps ON THE VM (execute sequentially)

### Phase A — Verify installs and login (do not reinstall blindly)

From a **terminal connected to the OpenStack VM**:

```bash
cd ~/qrl-lab
pwd
claude --version
codex --version
codex login status
node --version
tmux -V
bash tools/vm_check.sh 2>&1 | tee ~/vm_check.txt
```

If `~/qrl-lab` is absent, extract the kit first to the researcher's home directory using the original `SETUP.md`, after inspecting its contents. **Do not paste `~/.codex/auth.json`, SSH keys, kubeconfig, passwords or tokens into chat.** Scrub sensitive details from `vm_check.txt` before sharing.

If `codex login status` is **not logged in**, complete the supported device-code login from the VM:

```bash
codex login --device-auth
codex login status
```

The device code is entered in the browser on the laptop/phone; the VM terminal must remain running until it confirms success. The latest displayed `codex login status` is what matters, not merely the browser's success screen. Official guidance: <https://developers.openai.com/codex/auth>.

If VM Node is older than **18.18**, update Node **only in the VM user environment**, e.g. via a supported Node LTS / nvm installation, without touching the older research Python environments. Verify `node --version` after activation **in the same shell/tmux environment that runs the plugin**. Official requirement: <https://github.com/openai/codex-plugin-cc>.

### Phase B — Plugin and basic cooperation

Safely disable the legacy MCP entry once, if it exists:

```bash
cd ~/qrl-lab
if [ -f .mcp.json ]; then mv .mcp.json .mcp.json.disabled; fi
```

Open Claude Code on the VM. In **Claude Code prompt** (not a shell):

```text
/plugin marketplace add openai/codex-plugin-cc
/plugin install codex@openai-codex
/reload-plugins
/codex:setup
```

The marketplace/install commands need running **only if the plugin is not already installed**. Check `/codex:setup` reports a usable Codex login. Perform one read-only task against `sandbox/demo.py` using `/codex:review` or another officially supported command; retrieve result with `/codex:result` for background tasks. Only after this smoke test run the `council` skill on an innocuous hypothetical technical question.

### Phase C — Remote Control, one persistent coordinator

Verify Claude subscription/login from VM (`/status`). Launch coordinator via the `tmux` helper only after reviewing and correcting the helper for the **installed** Claude CLI. Validate `--remote-control` syntax with `claude --help` and <https://code.claude.com/docs/en/remote-control>. Check the same named session is actually reachable from `claude.ai/code` and Claude mobile. Do not start duplicate coordinators in separate editor panels.

A working Remote Control session is **not** the dashboard; it is an alternate channel. An active VM and running Claude process are needed. Enable mobile pushes if available, but store every approval request in the database.

### Phase D — Build **working dashboard v1** BEFORE research experiments

Implement as a small Streamlit application, binding only `127.0.0.1:8501`. Minimal required features:

- **Inbox/chat view:** user message -> persistent queue -> coordinator notification/acknowledgement -> stored coordinator response -> dashboard display. Show `received`, `assigned`, `waiting approval`, `done`, `failed` and timestamps; test the full round trip.
- **Claude + Codex visibility:** agent-specific tasks/outputs with status, model when available and references, one unified coordinator reply. Show *which* findings came from each agent; don't suggest the ChatGPT web thread was automatically consulted.
- **Approvals:** structured accept/reject/request changes; state changes only after validation; never execute shell commands directly from browser textbox or trust arbitrary JSONL edits.
- **Runs:** placeholder run table then live plots from real experiment telemetry; record code SHA/config hash/workload/seed/metrics and compute resources.
- **Paper/venues:** status and citations table, not fabricated material.

For the first proof of dashboard messaging, submit `hello dashboard` in Streamlit and confirm Claude sees it and writes **an actual visible reply**. Submit an approval request and reject it; prove that no experiment starts. If automatic monitor delivery is unreliable, first implement an explicit bounded polling/worker adapter. Do not claim success until this works end-to-end.

Access **from laptop** (not from a separate shell on the VM):

```bash
ssh -N -L 8501:127.0.0.1:8501 <YOUR_EXISTING_WORKING_VM_SSH_DESTINATION>
```

Then visit `http://localhost:8501` in the laptop browser. Use the same VPN/jump-host/SSH options already needed for your ordinary VM SSH connection. Never expose dashboard port 8501 publicly.

**Mobile without VPN:** Claude Remote Control chat + best-effort pushes remains the supported alternative. The private SSH-tunneled dashboard itself is accessible on devices with a suitable tunnel/VPN, not automatically through the Claude app.

### Phase E — Research inventory, independent checks and baseline approval

Read-only inventory: enumerate actual folders for simulator code, Kubernetes/Redis, YAMLs, logs/checkpoints and worktree. Verify provenance for historical simulation and real-cluster experiments (code SHA, run commands, model checkpoint hashes, timestamps, config). Independently reproduce F1–F5 against **the version that really ran**, not only the GitHub snapshot. Give the researcher a written decision memo for a corrected simulator v2 and model changes. **Do not start a real cluster run before separate approval.**

### Phase F — Experimental method, paper and publication gate

- Start simulator v2 with a causally linked arrivals → capacity → utilization/latency/SLO → reward chain and pod startup delay, calibrated against real measurements where possible. Avoid building desired policy performance into the simulator.
- Workload families: W0 sine/noise/spikes; W1 bursty non-homogeneous Poisson/MMPP; W2 appropriately licensed real trace; W3 distribution/regime shift.
- Classical baselines: original/as-is reference (with limitations), corrected DInos+transfer, HPA, trivial/static/oracle policies, parameter-/compute-matched classical small model and frozen-encoder control.
- Quantum priority to screen **QC1 full VQC**, **QC3 GRU+VQC**, **QC4 quantum transfer adaptation**, optionally QC6 quantum similarity/regime detector. Gate quantum experiments on validated simulator/benchmarks and researcher's approval.
- Measure quality (reward decomposition, SLA violations, p95/p99, scaling churn), convergence/sample efficiency, training/inference wall-clock, peak CPU RAM/GPU RAM, disk/checkpoint/transfer bytes, trainable params, quantum qubits/circuit depth/gates/shots and number of simulator calls. Statistical uncertainty across seeds; no unsupported theoretical or empirical quantum speedup claims.
- Paper scaffold and related work run in parallel, with DOI-verified citations and claim → experiment evidence mapping; scout conferences with official CFPs, rankings and realistic deadlines. CCGrid 2027 is one candidate, **not a promised acceptance**.

## 7. Operational acceptance criteria — researcher can stop using separate chats WHEN

- **A1:** `codex login status` on VM reports logged in; `/codex:setup` passes.
- **A2:** Claude delegates a sandbox task to Codex and receives its result; a follow-up/cross-critique works in the installed version.
- **A3:** One persistent Claude session works through Remote Control; no duplicate coordinator.
- **A4:** Researcher sends a request **from dashboard** and receives a visible coordinator answer including Codex contribution when solicited.
- **A5:** Researcher receives an approval request **in dashboard**, rejects/changes/approves it and the executor obeys that specific decision.
- **A6:** Dashboard shows truthful status of jobs and agents, even when Claude/Codex calls are paused, rate-limited or VM processes restart.
- **A7:** Each run points to reproducible code/config/seed/metrics; baseline experiments and original results remain unmodified.
- **A8:** Remote/dashboard access is private, and secrets are never stored in project git or event logs.

Until **A4–A5** pass, **do not tell the researcher the dashboard can replace the CLI/chat interfaces**. Until A1–A3 pass, do not tell the researcher the Claude–Codex system is fully connected.

## 8. Coordinator's first requested reply to the researcher

Please respond in **Greek**, succinctly, with:

1. Which of A1–A3 are **verified now** versus **not yet checked**, based on actual VM outputs.
2. Exactly **one next terminal command/test at a time** if something fails; do not reinstall working tools.
3. A list of differences between your original kit and these recommendations, and what you propose changing **only after approval**.
4. A concrete plan to implement the dashboard's **two-way agent messaging**, not merely a JSONL viewer.
5. A commitment not to change original research code, run uncontrolled Kubernetes commands, buy API credits or enable automatic review loops without approval.

## 9. Reference artifacts and official documentation

- Research master plan: `~/qrl-lab/docs/PLAN.md` (from `qrl-lab-kit.zip`, original v0.1; update only with proper research approval).
- ChatGPT independent kit review: `QRL_LAB_CODEX_REVIEW_V0_2.md`.
- ChatGPT read-only GitHub verification: `QRL_LAB_GITHUB_VERIFICATION_2026_10_16.md`.
- Official Codex Claude plugin: <https://github.com/openai/codex-plugin-cc>
- Official Codex CLI authentication: <https://developers.openai.com/codex/auth>
- Claude Remote Control: <https://code.claude.com/docs/en/remote-control>
- Connected source repository: <https://github.com/KostasBitsakos/K8s_Redis_DeepRL/tree/evaluation>

**Important distinction:** Actual current VM state, successful authentication, dashboard implementation, and experimental provenance must be established by local outputs/tests. ChatGPT has **not** directly accessed the private OpenStack VM during this handoff.
