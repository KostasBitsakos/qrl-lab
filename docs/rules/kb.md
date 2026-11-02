# Knowledge base (`tools/kb.py`) — retrieve before you read (J314, M-20261102-020)

One local index over: `~/qrl-lab` (tools, dashboard, tests, prompts, docs, paper, deploy), `.lab/**/*.md|txt` notes,
worktrees `code-poisson-spiky` (current cycle-2 code) and `code-tuning` (cycle-1 final), and the read-only
`~/simulations ~/redis ~/k8s ~/prometheus-grafana`. Plain CLI, no LLM, no network, no keys; works identically for Claude and Codex.

## Use
```
python3 tools/kb.py query "<question, symbol, or id such as M-20261102-020>"   # ≤~500 tokens: file:line pointers
python3 tools/kb.py callers <symbol>                                           # callers / dependencies (graphify AST graph)
python3 tools/kb.py stats | scan                                               # sizes + freshness | secret scan
python3 tools/kb.py refresh [--full]                                           # ~30 s, taskset 4-7 inside; run after big merges
```
1. Ask `kb.py query` FIRST for «where is / who calls / what was decided / what happened to <id>»; then read ONLY the
   returned file:line windows (`Read` with offset/limit), never the whole file or all of `docs/`.
2. When you know the exact symbol and the directory, plain `grep -n` is cheaper (see numbers below): use it.
3. Pointers are REAL paths. Chunk line = the best-matching line inside the section. Verify before quoting a number:
   the index is a locator, not a source of truth. Stale-index risk: run `refresh` if the file you need changed in the last
   hours (the `built` time is in `kb.py stats`).
4. Not indexed: the other branch worktrees (`code-poisson`, `code-poisson-astra`, `code-tuning-*`, `code`), run
   outputs/checkpoints/logs, `lab.db`/`dispatch.db` messages (use `labq.py show`), files >400 KB, non-text. Files that match a secret pattern or
   secret-looking name are skipped at staging (`kb.py scan` must print 0 hits).

## Measured (tools/kb_eval.py, 15 questions, tokens = bytes/4 ESTIMATES of tool output, not model tokens)
See `docs/kb_eval.md`. KB 14–15/15 answered with ~4.6k tokens total vs plain `grep -rn` (given the right keyword) ~11.4k, 14/15.
KB wins on docs/decisions/ids/fuzzy questions (3–7× smaller); grep wins on exact-symbol lookups (37–250 vs 190–460 tokens).
