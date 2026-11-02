# KB vs grep evaluation (J314)
Questions and expected pointers: `tools/kb_eval.py` (fixed before running, except Q6/Q9/Q10/Q11 widened after run 1 to every file that truly
contains the answer; run 1: KB 9/15). Raw: `.lab/j314/eval_final.md`. Tokens = bytes/4 estimate of TOOL OUTPUT ONLY (no reasoning,
no follow-up reads). Baseline = uncapped `grep -rnI -F <keyword>` over tools/dashboard/tests/docs/prompts with the RIGHT keyword
given (best case for grep; a real agent often needs several greps/reads). Author wrote both questions and KB: bias possible.
| # | cat | question | KB tok≈ | KB ok | grep tok≈ | grep lines | grep ok |
|---|---|---|---|---|---|---|---|
| 1 | code | where is def overlaps in work.py | 227 | Y | 59 | 3 | Y |
| 2 | code | where is finish_run defined | 216 | Y | 63 | 2 | Y |
| 3 | code | who calls finish_run | 218 | Y | 177 | 7 | Y |
| 4 | code | how does pin_plan choose the CPUs | 184 | Y | 271 | 10 | Y |
| 5 | code | history ablation shuffle newest option V.2 Q-net | 339 | Y | 1086 | 35 | Y |
| 6 | dashboard | race view job lanes | 437 | Y | 64 | 3 | Y |
| 7 | dashboard | dispatcher save_limits utilization | 341 | Y | 463 | 12 | Y |
| 8 | experiments | Stage 1b caps sandbox CPU-h 24 runs | 365 | Y | 475 | 9 | Y |
| 9 | experiments | R-20261029-001 budget 160 CPU-h | 295 | Y | 894 | 17 | Y |
| 10 | decisions | approved model names LSTM Dinos Dinos+Transfer V | 382 | Y | 2205 | 39 | Y |
| 11 | decisions | which cores run experiments DEFAULT_SIM_CPUS | 380 | Y | 2774 | 33 | Y |
| 12 | external | redis hpa autoscale cluster yaml | 336 | Y | 250 | 7 | N |
| 13 | incident | cycle3 false 3 failed val_stats total_ticks | 272 | Y | 516 | 7 | Y |
| 14 | id | M-20261102-020 | 195 | Y | 232 | 7 | Y |
| 15 | experiments | Stage 1b results Dinos shuffle newest mlp_a1h me | 386 | Y | 1859 | 10 | Y |
| | | TOTAL | 4578 | 15/15 | 11392 | 201 | 14/15 |

Reading: KB total ≈4.6k vs grep ≈11.4k tokens (-60%), but per-question KB output is a flat 180–480 tokens, so for exact-symbol
lookups (Q1–4, Q6) grep is smaller (37–250). Biggest KB wins: Q9–Q11, Q15 (docs/decisions/results; grep 0.9–2.8k). Q12: grep matched
content, not the file name, so it missed the yaml file. NOT measured: end-to-end tokens of a full answer, savings in real sessions.
Earlier code-only graphify trial: `.lab/c224/report.md` (graph alone, no win on 3 questions) — consistent: the gain here comes from the
docs/section FTS index; the graph only adds `callers`.

Codex blind review (J314, `.lab/j314/` peer answer): no leakage observed but flagged symlink-following, weak SECRET_RE, size/mtime reuse, non-atomic refresh, same-name dedupe, dev-set evaluation. Fixed: symlinks skipped, quoted/`token=` patterns (3 files conservatively skipped: tools/web_terminal.py, tools/access.py, tests/test_kb.py), content-compare staging, lock + atomic DB publish, scan prints no secret text, `tests/test_kb.py`. NOT fixed: coverage of other worktrees (code-poisson-astra etc.), lab.db messages, duplicate-name collisions across worktrees, held-out independently authored questions.
