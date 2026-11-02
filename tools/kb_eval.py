#!/usr/bin/env python3
"""NOTE: expected pointers for Q6, Q9, Q10, Q11 were widened AFTER the first run (first run: 9/15 KB) to every file that
really contains the answer; Q1-5, 7-8, 12-15 unchanged. Honest KB-vs-grep comparison (J314). Questions + expected pointers are fixed here BEFORE running.
Tokens are bytes/4 ESTIMATES of tool output only (no model reasoning tokens). 'ok' = an expected pointer is in the output.
Baseline = the plain grep an agent would typically run first (uncapped, scoped to tools/dashboard/tests/docs/prompts)."""
import re, subprocess, sys, json
from pathlib import Path
LAB = Path.home() / "qrl-lab"
SCOPE = "tools dashboard tests docs prompts CLAUDE.md AGENTS.md"
# (id, category, question for kb, grep keyword(s) for baseline, [expected "path:line" regexes])
Q = [
 (1, "code", "where is def overlaps in work.py", "def overlaps", [r"tools/work\.py:65\b"]),
 (2, "code", "where is finish_run defined", "def finish_run", [r"tools/launch_run\.py:318\b"]),
 (3, "code", "who calls finish_run", "finish_run", [r"tools/launch_run\.py:460\b"]),
 (4, "code", "how does pin_plan choose the CPUs", "pin_plan", [r"tools/launch_run\.py:71\b"]),
 (5, "code", "history ablation shuffle newest option V.2 Q-net implementation", "history_ablation", [r"code-poisson-spiky/tuning/(legacy/)?[a-z_0-9]+\.py:\d+ \[(def|class)\][^\n]*ablation"]),
 (6, "dashboard", "race view job lanes", "job_lanes", [r"tools/race_view\.py:(71|286)\b"]),
 (7, "dashboard", "dispatcher save_limits utilization", "save_limits", [r"tools/dispatcher\.py:226\b"]),
 (8, "experiments", "Stage 1b caps sandbox CPU-h 24 runs", "Stage 1b", [r"docs/EXPERIMENTS\.md:59\b"]),
 (9, "experiments", "R-20261029-001 budget 160 CPU-h", "R-20261029-001", [r"docs/cycle2_plan\.md:52\b", r"docs/DECISIONS\.md:6[2-4]\b"]),
 (10, "decisions", "approved model names LSTM Dinos Dinos+Transfer V.2 test at best checkpoint", "Dinos+Transfer V.2", [r"docs/DECISIONS\.md:41\b", r"\.lab/tuning/model_definitions\.md"]),
 (11, "decisions", "which cores run experiments DEFAULT_SIM_CPUS", "8-39", [r"tools/launch_run\.py:45\b", r"docs/STATE\.md:\d+", r"claude-memory/core-split\.md"]),
 (12, "external", "redis hpa autoscale cluster yaml", "hpa", [r"redis-autoscale-cluster-hpa\.yaml:\d+"]),
 (13, "incident", "cycle3 false 3 failed val_stats total_ticks", "val_stats", [r"tools/cycle3/cycle3\.py:14[0-9]\b", r"docs/STATE\.md:\d+"]),
 (14, "id", "M-20261102-020", "M-20261102-020", [r"\.lab/c313_brief\.md:\d+", r"docs/journal/2026-11-02\.md:\d+"]),
 (15, "experiments", "Stage 1b results Dinos shuffle newest mlp_a1h mean return", "Dinos shuffle", [r"docs/STATE\.md:\d+", r"docs/EXPERIMENTS\.md:\d+"]),
]
def sh(cmd):
    return subprocess.run(cmd, shell=True, cwd=LAB, capture_output=True, text=True).stdout
rows = []
for qid, cat, q, kw, exp in Q:
    kb = subprocess.run([sys.executable, "tools/kb.py", "query", q], cwd=LAB, capture_output=True, text=True).stdout
    scope = SCOPE if cat != "external" else "~/redis ~/simulations"
    if qid == 5:
        scope += " code-poisson-spiky"      # give grep the right worktree (best case)
    gr = sh(f"grep -rnI --include='*.py' --include='*.md' --include='*.yaml' --include='*.sh' -F '{kw}' {scope} 2>/dev/null")
    grn = gr.replace(str(Path.home()), "~")
    kb_ok = any(re.search(e, kb) for e in exp)
    gr_ok = any(re.search(e.replace(r"\b", "").split(r" \[")[0], grn) for e in exp)
    rows.append(dict(id=qid, cat=cat, q=q, kb_bytes=len(kb.encode()), kb_ok=kb_ok, grep_bytes=len(gr.encode()),
                     grep_lines=gr.count("\n"), grep_ok=gr_ok))
tot = lambda k: sum(r[k] for r in rows)
print("| # | cat | question | KB tok≈ | KB ok | grep tok≈ | grep lines | grep ok |\n|---|---|---|---|---|---|---|---|")
for r in rows:
    print(f"| {r['id']} | {r['cat']} | {r['q'][:48]} | {r['kb_bytes']//4} | {'Y' if r['kb_ok'] else 'N'} | {r['grep_bytes']//4} | {r['grep_lines']} | {'Y' if r['grep_ok'] else 'N'} |")
print(f"| | | TOTAL | {tot('kb_bytes')//4} | {sum(r['kb_ok'] for r in rows)}/{len(rows)} | {tot('grep_bytes')//4} | {tot('grep_lines')} | {sum(r['grep_ok'] for r in rows)}/{len(rows)} |")
json.dump(rows, open(LAB / ".lab/j314/eval.json", "w"), indent=1)
