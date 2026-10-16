# Accepted decisions

Newest first. Each entry: date, who decided, source, decision.

## 2026-10-16 — D9 IBM Quantum (decided by: researcher; source: R-20261016-001)

The researcher has an IBM Quantum account. No IBM jobs for now. Real-hardware tests come only once the quantum
models are ready, and each job still needs per-job approval with estimated QPU seconds (PLAN §6).

## 2026-10-16 — standing rules (decided by: researcher; source: docs/handoffs/HANDOFF_2026-10-16_planning-chat.md §3)

1. **The dashboard is the only channel.** The terminal and phone app are fallbacks for permission prompts and emergencies.
2. **Dashboard changes are requested in the dashboard.** The `engineer` implements them. Before applying, run
   `tests/test_lab.py` and add tests for the new feature, then commit. If the dashboard breaks, revert with git at once.
   Tell the researcher to press F5 after each change.
3. **When the researcher asks for Codex, Codex must actually be consulted.** Its answer is shown as Codex
   (`--author codex`). Never substitute your own answer or only offer to ask.
4. **Never overwrite settings the researcher or tools changed.** Merge edits into `.claude/settings.json`, keep
   plugins at user scope, and put project-only toggles in `.claude/settings.local.json`.
5. Write to the researcher in Greek, short and direct.

## 2026-10-16 — environment facts (recorded by: researcher; source: same handoff §1)

- VM: `ubuntu@10.0.1.28`, hostname `kbitsak-very-large`. The earlier "10.1.1.28" was a typo.
- Kubernetes: the kubeconfig API server (`10.0.1.28:6443`) is this VM and refuses connections, so the cluster is
  stopped (PLAN F7). Bringing it up needs per-item approval (D11).
- Researcher access is through VS Code Remote-SSH only. The dashboard is reached as a VS Code Ports forward of
  8501 → `http://localhost:8501`, so it is visible only while VS Code is connected. Files reach the VM by drag & drop
  into the VS Code Explorer.
- Claude Code 2.1.300 on the VM. Node comes through nvm (user-local). codex-cli is logged in with device auth.
- The `codex@openai-codex` plugin is at **user** scope. At project scope, kit v0.2's `unzip -o` overwrote
  `.claude/settings.json` and silently disabled it (see rule 4). `agent-memory`, `small-business` and
  `aws-startups` are disabled for this project (local scope).
- pyright-lsp is not installed because git 2.25.1 fails on `sparse-checkout`. Optional fix: a newer git from
  `ppa:git-core/ppa`, which needs sudo and per-item approval.
- The tmux session `lab` died once (cause unknown) and was restarted with `tools/start-coordinator.sh`. If it
  happens again, record `uptime`, `last -x | head`, and the end of the coordinator's terminal output.
- Original research directories are read-only for agents: `~/simulations` (git `redisk8s`), `~/redis`
  (git `autoscaling-redis-cluster-hpa-kubernetes`), `~/k8s`, `~/prometheus-grafana`. Archive: `~/all.zip` (2024-04).

## 2026-10-16 — D12 (decided by: researcher)

ChatGPT handoff adopted: codex mcp-server dropped, approvals enforced in the launcher, acceptance tests A1–A8.
