# Archive — superseded entries and history

Verbatim copies from `docs/DECISIONS.md` as it stood before the 2026-10-20 split (R-20261020-001), strict newest
first. Nothing here is an active rule; active parts were reworded into the other files in this folder (see README.md).

## Archived 2026-10-20: W0 exploratory study (superseded in part by R-20261017-017: the old-reward run is a pipeline test only)

## 2026-10-17 — W0 exploratory study (R-20261017-014, researcher chose option 1)
Both Sim v2.1 gates failed and remain failed; PLAN §8.1 amended (see there) to allow a bounded exploratory W0 study
with unchanged provisional parameters, a disclosed Kubernetes-HPA comparator, development-range evaluation seeds,
final test seeds untouched; calibration prepared in parallel. Researcher also asked (M-20261017-068) that the HPA be
reverse-engineered from the official Kubernetes docs/source.

## Archived 2026-10-20: D12 handoff (history; see PLAN §13 D12)

## 2026-10-16 — D12 (decided by: researcher)

ChatGPT handoff adopted: codex mcp-server dropped, approvals enforced in the launcher, acceptance tests A1–A8.

## Archived 2026-10-20: environment facts (history)

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

## Archived 2026-10-20: D2 Sim v2 design (reward line superseded by R-20261017-017; SLO/weights line superseded by R-20261017-018; calibration pilot paused, see paused.md)

## 2026-10-16 — D2 Sim v2 design (decided by: researcher; source: R-20261016-013, council C-20261016-01)

Option 1 of `.lab/council/C-20261016-01/card.md`: build Sim v2 now with provisional, labelled parameters.
- Design: transient fluid/cohort queue, 1–30 pods, startup delay, rebalance loss, calibrated capacity curve C(c).
- Reward: −α·pod-seconds − β·SLO failures − γ·scaling changes.
- Gates frozen before any agent run.
- A calibration pilot up to 30 pods on the real cluster follows, under a separate approval.
- SLO and weights are set by the researcher before agents are evaluated.

## Archived 2026-10-20: original file header

# Accepted decisions

Newest first. Each entry: date, who decided, source, decision.
