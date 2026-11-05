# Tutorial review and validation — J97

Request: M-20261029-159. Artifact: `ml_quantum_autoscaling.pdf`, **draft 1**.
Date: 2026-10-29. Owner: Codex. **Independent Claude technical review remains pending.**
This is a delivered draft, not a fully reviewed final tutorial.

## Teaching/source strategy

Read `docs/STATE.md` first, `docs/tutorial.md` and the historical request memory.
`docs/tutorial_style.md` was absent; restored it as a short pointer to `PLAYBOOK.md`.
Checked IES/WWC, Fiorella–Mayer and Mayer sources online before writing (URLs and scope in PLAYBOOK).
Used one Redis/pod example, short concept pages, intuition before notation, worked arithmetic,
local symbol explanations, causal diagrams and recall questions with answers.
Checked technical references online: Double DQN, PPO, Agarwal RL evaluation, PyTorch LSTM/GRU,
Poisson/NHPP textbook, PennyLane re-uploading/parameter-shift, and Quantum Fingerprinting.
The DRe-SCale DOI landing page blocked automated access; implementation attribution is additionally
supported by the original repository and `code-poisson/tuning/rppo.py` provenance, not a claimed paper reproduction.
No run results or rankings are introduced. Proposed quantum architectures are clearly distinguished from implementation.

## Fresh-reader editorial test (verbatim agent response)

Fresh reader `/root/beginner_read` was instructed to assume beginner knowledge, read only, and find unclear steps.
This is an editorial proxy, **not a human comprehension study**.

> **Fresh-reader verdict:** coherent running example and useful safeguards, but several mathematical jumps need small repairs.
>
> 1. **Navigation:** cover plus sections 1–20 yields 21 pages. Hardcoded page references appear one page early. Use labels/`\pageref` or unnumbered cover.
> 2. **Episode introduced late:** “episode,” “reset,” “gradient” appear before explanation. Define episode at first use; explain gradient as “how each weight should change to reduce error.”
> 3. **Workload notation overload:** φ/ϕ look similar; σ means noise strength then sigmoid; ε means random disturbance then exploration. Prefer distinct names or a small local symbol key.
> 4. **Section 3 is dense:** NHPP → Markov → MMPP → Cox in one page. Keep the practical conclusion prominent: “persistent bursts produce several difficult ticks together”; mark taxonomy optional.
> 5. **LSTM equations:** six equations arrive before any numeric intuition. Add one scalar illustration: forget gate 0.9 preserves 90% of old memory; input gate 0.1 admits little new information.
> 6. **PPO advantage:** reuses Â from arrivals; acknowledging this still makes the reader stop. Rename smoothed arrivals λ̂. Define clipping in words: reduce incentive to change action probabilities too aggressively.
> 7. **Quantum measurement leap:** “observable Z” and bra–ket expectation lack a concrete bridge. Add: Z assigns +1 to outcome 0 and −1 to outcome 1; 75% zeros gives mean 0.5.
> 8. **Quantum proposals are catalog-heavy:** give each QC a consistent one-line “input → transformation → output” summary. Explain encoder once as “compresses observations into useful features.”
>
> **Examples:** Poisson, reward, DDQN, and IQM arithmetic are understandable and correct as written. DDQN should explicitly say the example illustrates different targets, not proof that DDQN always gives a better estimate.
>
> **Comprehension answers, in order:**
> 1. Startup delay.
> 2. Different workload difficulty.
> 3. Future avoided queue/SLO penalties can outweigh present pod cost.
> 4. Opposite trends despite identical current CPU.
> 5. No; include source training and adaptation costs.
> 6. No; freeze choices, then use untouched test.
> 7. Same frozen encoder plus classical head with matched trainable parameters.
> 8. No; circuit evaluations, shots, data loading, and gradients also cost time.
>
> **Priority:** repair page references, define early terminology, and add the LSTM/Z examples before release. No edits made.

Revision: consolidated cover into the first concept page, yielding exactly 20 physical pages; page references now align.
Added early episode/reset/gradient definitions, practical burst summary and optional taxonomy signpost;
local meaning of φ/ϕ, separate λ̂ for HPA smoothed arrivals, LSTM/Z numeric intuition,
encoder definition and input→output summaries for all QC proposals. Added the DDQN example limitation.
Other symbol reuse follows standard local notation and is explained next to the equations.

## Claude review — blocked by provider availability, not researcher approval

Submitted through `tools/ask_peer.py`, explicit `--to claude`:
`P-20261029-142558-77d1`, key `j97-tutorial`.
Result: `PEER FAILED: Claude is at its usage limit until 29/10 15:16` (UTC, as reported by tool).
No Claude verdict exists; no contribution was fabricated or posted under Claude's name.
Brief: `.lab/j97/claude_review_brief.md`. After checking provider availability, retry:

```sh
python3 tools/ask_peer.py submit --to claude --key j97-tutorial --prompt-file .lab/j97/claude_review_brief.md
python3 tools/ask_peer.py wait <returned-P-id> --timeout 30
```

Post the actual answer verbatim as a Claude contribution to M-20261029-159, then resolve corrections,
rebuild/verify and remove the draft notice from the source/catalog only after approval.
No credits/limit bypass or researcher decision is needed. Coordinator received this handoff through `work.py say`.

## Build, PDF and live UI evidence

- `bash docs/tutorials/src/build.sh`: installed pdfLaTeX; no package downloads. LuaLaTeX first failed because
  luaotfload was missing; switched to installed Babel/alphabeta/CB Greek fonts. Logs: `.lab/j97/tex/`.
- Final build: **20 pages**, **19 PDF section bookmarks**, **12 hyperlinks** (`.lab/j97/pdf-check.log`).
  Final build log has no Overfull, Missing character or LaTeX warning entries.
- Greek text is extractable. Leading capital accents may extract as a separate tonos glyph;
  structural checker normalizes accent/whitespace differences. Rendered text inspected for legibility.
- Rendered all pages with Ghostscript; inspected pages 1, 6, 7, 8, 14 and 20 for layout/math/Greek.
  Screenshots `.lab/j97/page-*.png`, `lstm.png`, `quantum.png`, `sources.png`.
- Focused tests **17 passed**: tutorial library, both tab tuple modes, tab links, mobile grouping, Race
  (`.lab/j97/pytest-focused.log`). New grouping regression was corrected in `tools/mobile_view.py`.
- Added `mobile_view` and `tutorials_view` to the existing local-module reload list so updates take effect without restart.
- Real Streamlit at `127.0.0.1:8501`, desktop and 390×844 viewport: PDF downloaded and compared byte-for-byte
  with the artifact. Phone button width fits, height 44 px; single-column cards fit. Phone menu shows Tutorials under Έρευνα. Evidence:
  `.lab/j97/browser-check.log`, `desktop.png`, `phone.png`, `browser_check.py`.
  Existing Chromium and libgbm under `.venv/` were used; nothing installed outside the venv; no service restart.
- `curl -fsS http://127.0.0.1:8501/_stcore/health`: `ok`.
- By agreement with J103, applied only two Race integration lines in app.py. Real browser displayed all active
  J97/J104/C108 jobs and the Codex chat coordinator; `.lab/j97/race-browser.log`, `race-desktop.png`.
  J103 owns Race module/tests; they are excluded from J97 commit scope.

## Full-suite failures and fresh-process diagnosis

Requested `taskset -c 4-7 .venv/bin/pytest tests -q` ran once: **288 passed / 19 failed**, 230.81 s.
Full log `.lab/j97/pytest-full.log`; exact failure/error excerpts `.lab/j97/failure-summary.txt`.
Each failing test was then run in its own fresh pytest process: **17 pass / 2 fail**.
See `.lab/j97/isolation-results.json` for every exact test id, outcome and individual log.
No second full-suite run was made and no unrelated tests/code were changed.

- Tutorials mobile grouping: introduced by the new tab, fixed; isolated and focused runs pass.
- 13 dispatcher failures and 3 lab failures: all pass alone. The two test modules mutate QRL_LAB_DIR,
  sys.path and cwd at collection time. In the combined run, peer/installer/work errors point to the wrong
  test module's temporary root (missing prompts/deploy/.git). This is evidence of collection-state interaction;
  it is not proof that every timeout has that sole cause. J97 does not change those modules.
- `test_exp_view.py::test_remaining_runs`: still fails alone; expects 12 h but function returns 82 h.
  `tools/exp_view.py:23,512` has LOOP_END 24/10 21:59 UTC, while `tests/test_exp_view.py:143–144`
  uses 21/10 11:59 and expects 12 h. The same constant and assertion are present in HEAD.
  Neither file is in J97's diff. No baseline suite was executed, so no blanket “pre-existing failures” claim.
- `test_dashboard_codex_routing.py::test_agents_card_shows_current_codex_provider_role_model`:
  still fails alone on expected `Συντονιστής (Codex)`. `tools/agent_models.py:259` labels the card
  `Πάρις (Codex...)`; this label is also in HEAD, and J97 does not change identity labels.
  The test reaches rendering without an app exception. Other asserted metadata was not reached;
  broader correctness is not inferred from this first mismatch.

## Commit/handoff limitation

`python3 tools/work.py commit -m 'Add Greek ML and quantum tutorial draft and download library (J97)'`
was attempted once and failed: `.git/index.lock: Read-only file system`. No commit or push was made.
The sandbox permits reading `.git` but not writing it; no approval request or bypass was attempted.
Coordinator must commit the exact J97 files from a writable context, preserving other jobs' changes.
`docs/STATE.md` was briefly claimed/updated/released; routing decision already exists in
`docs/DECISIONS.md` (C98, M-20261029-159), so no duplicate decision was added.
