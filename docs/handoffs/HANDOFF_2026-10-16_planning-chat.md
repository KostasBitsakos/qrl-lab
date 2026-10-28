---
description: Decisions and findings from the claude.ai planning chat after PLAN v0.2 (16/10), the project's starting brief
---
# Handoff from the claude.ai planning chat — 2026-10-16 (after PLAN v0.2)

For: the QRL-Lab coordinator. From: the researcher, via the planning chat (Claude) where the kit was designed.
This file lists what was decided or discovered **after** `docs/PLAN.md` v0.2. Process it like this:
1. Record §1 and §3 in `docs/DECISIONS.md` (date 2026-10-16, decided by: researcher).
2. Update the status columns of PLAN §12 (acceptance tests) and §13 (decisions) from §2 and §6.
3. Redo acceptance test A4 correctly (§2) **before** anything else.
4. Then implement the dashboard change requests of §4, in order, one at a time.
5. File the open questions of §6 with skill `ask-user` (dashboard), not in chat.

---

## 1. Environment facts (2026-10-16)

- **VM**: `ubuntu@10.0.1.28`, hostname `kbitsak-very-large`. (An earlier message said 10.1.1.28; that was a typo.)
- **Kubernetes**: the API server in kubeconfig (`10.0.1.28:6443`) is **this VM**; it refuses connections, so the
  cluster on this VM is stopped (PLAN F7). Bringing it up = per-item approval (D11).
- **Researcher's access**: VS Code Remote-SSH only. Plain `ssh`/`scp` from the laptop is not used.
  Dashboard = VS Code *Ports* forward of 8501 → `http://localhost:8501`. Files reach the VM by drag & drop into the
  VS Code Explorer. So: the dashboard is visible only while VS Code is connected; the Claude phone app works anyway.
- **Claude Code 2.1.300** on the VM; Node through nvm (user-local); codex-cli logged in with device auth.
- **Plugins**: `codex@openai-codex` installed at **user** scope. At first it had been installed at project scope and
  kit v0.2's `unzip -o` overwrote `.claude/settings.json`, which silently disabled it. Lesson recorded in §3 rule 4.
  Disabled for this project (local scope): `agent-memory`, `small-business`, `aws-startups`.
- **pyright-lsp not installed**: the VM's git 2.25.1 failed on `sparse-checkout` during plugin install. Optional fix:
  newer git from the `ppa:git-core/ppa` (sudo → per-item approval). Not required.
- **tmux session `lab` died once** (cause unknown) and was restarted with `tools/start-coordinator.sh`.
  If it happens again, record `uptime`, `last -x | head`, and the end of the coordinator's terminal output.
- **T0 passed on the VM** (`tests/test_lab.py` → ALL PASSED (6)); dashboard running in tmux window `dashboard`.
- Original research directories (read-only for agents): `~/simulations` (git `redisk8s`), `~/redis`
  (git `autoscaling-redis-cluster-hpa-kubernetes`), `~/k8s`, `~/prometheus-grafana`; archive `~/all.zip` (2024-04).

## 2. Acceptance tests (PLAN §12) — status

| Test | Status | Note |
|---|---|---|
| T0 | pass | on the VM, 2026-10-16 |
| A1 | pass | codex logged in, `/codex:setup` ok (researcher) |
| A2 | **open** | the coordinator has not yet called Codex |
| A3 | open | researcher to check the session in the phone app |
| A4 | **failed, redo now** | the researcher asked for Codex's opinion on `sandbox/demo.py`; the coordinator answered alone and offered to ask Codex later |
| A5–A8 | open | |

**Redo A4 (and pass A2) now**, in the existing dashboard thread:
1. Agent tool, `subagent_type: "codex:codex-rescue"`, prompt:
   `--fresh --model gpt-6-sol --effort medium READ-ONLY: review only, do not edit files. Review sandbox/demo.py:
   find bugs and edge cases, with line numbers and a minimal fix for each. Under 250 words.`
   Do **not** tell Codex what you found (blind review).
2. Post Codex's answer verbatim in the same thread: `labq.py post --author codex --kind contribution`.
3. Post your synthesis: where you and Codex agree or differ. Mark the message done.
4. Follow-up check for A2: a second Codex call with `--resume` (e.g. "which of your findings matter most and why?").

## 3. Standing rules from the researcher

1. **The dashboard is the only channel.** The terminal and phone app are fallbacks for permission prompts (🔐)
   and emergencies.
2. **Dashboard changes are requested in the dashboard.** The `engineer` implements them. Before applying: run
   `tests/test_lab.py` and add tests for the new feature. Commit. If the dashboard breaks, revert with git at once.
   Tell the researcher to press F5 after each change.
3. **When the researcher asks for Codex, Codex must actually be consulted**, and its answer is shown as Codex
   (`--author codex`). Never substitute your own answer or only offer to ask.
4. **Never overwrite settings the researcher or tools changed.** Merge edits into `.claude/settings.json`; keep
   plugins at user scope; project-only toggles go to `.claude/settings.local.json`.
5. Write to the researcher in Greek, short and direct.

## 4. Dashboard change requests (in this order)

**DR1 — one continuous conversation, like a chat app (highest priority).**
- The 💬 tab opens on one ongoing conversation ("Κύρια συζήτηση"). The researcher types at the bottom and sends;
  messages appear at the bottom in order, the view scrolls to the newest, and the input stays at the bottom
  (Enter sends; Shift+Enter makes a new line if Streamlit allows it).
- New messages go to the current conversation by default. A new topic is created only through an explicit
  "Νέο θέμα" button; the list of topics moves to a collapsible side list.
- Under the last message, show a live indicator while the researcher's latest message is acknowledged or
  in_progress: "⏳ ο συντονιστής δουλεύει…" plus the agents active right now (from `.lab/events.jsonl`).
- Coordinator side: always reply in the same thread (`labq.py post --reply-to <latest researcher message>`).
- Keep the guarantee that auto-refresh never erases text being typed. Extend `tests/test_lab.py` (AppTest) to cover
  sending two messages in a row into the same thread.

**DR2 — attach files to a message.**
- `st.file_uploader` (multiple files) next to the input. Files are saved to `.lab/uploads/<M-id>/` (size limit, e.g.
  200 MB per file; never executed), listed inside the message with download links, and their paths are included
  in the QRL-INBOX text so the agents read them. `.lab/` stays out of git.

**DR3 — who answered with what.** Show agent and model on each agent message (e.g. "Codex · gpt-6-sol",
"engineer · Sonnet"), taken from the post (add an optional `--model` field to `labq.py post`).

## 5. Research next steps (unchanged from PLAN, in order)

1. A5 and A6 with the researcher (PLAN §12; `sandbox/toy_spec.json`).
2. Read-only inventory (`Explore`, Haiku) of the directories in §1 → `docs/INVENTORY.md`, with evidence for the
   code version behind the published DInos simulation and real-cluster results (git history, run scripts, logs,
   checkpoints, configs; not folder dates alone). The researcher confirms the baseline; then the `code/` worktree
   (approval).
3. Papers: the researcher will put them in `docs/papers/` (thesis, interim thesis, DInos DEXA 2025, DERP 2018,
   QuantuML paper and thesis, the 2025 journal paper). Read them before the Sim v2 proposal.
4. Sim v2 design proposal through `council` → decision card → approval.
5. Plan to bring the K8s cluster back up (D11) as an approval request.

## 6. Open questions for the researcher (file with `ask-user`)

- D2–D9 of PLAN §13 (Sim v2 and reward weights, workloads, quantum candidates, publication gate, venue,
  F1/F5 and the public GitHub repository, IBM Quantum plan and QPU minutes).
- Optional: upgrade git for pyright-lsp (sudo).
