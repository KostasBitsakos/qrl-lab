# Cycle 2 aggregate sandbox — J41

Implementation task: M-20261029-030, coordinator brief `.lab/c38/launcher.md`.
No run authorization is supplied by this document. R-20261029-001 is an answered budget question with no spec/hash
(`python3 tools/labq.py request R-20261029-001`), not an approved sandbox.

Use ONE `kind: sandbox`, `scope: sim` parent with the existing normal spec envelope (`name`, `cwd`, `entries`,
`limits.wall_clock_hours`). Its `sandbox` block has:

```json
{
  "worktrees": [
    {"repo": "code-poisson", "branch": "dinos-poisson"},
    {"repo": "code-poisson-astra", "branch": "dinos-poisson-astra"}
  ],
  "frozen_env_commit": "238003f58a7ae547c9ff03b05f5484ea5a1c342b",
  "frozen_harness_commit": "b609b939085ee3e07c334b94d2cd79929938df9b",
  "frozen_entry_sha256": "1b5a6f2922422e26b15f6729969f5870e994f1922d867cfa7f5ac880117d000e"
}
```

Also supply the existing sandbox fields `cpu_hours_budget`, `max_parallel`, `cpu_affinity`,
`per_run_wall_clock_hours`, `expires`, `seed_ranges_allowed`, `seed_ranges_forbidden`. The example intentionally
omits those fields: it is a schema illustration, not an executable frozen spec. Do not add top-level `repo` or
`branch` inside this aggregate block. Each child selects a top-level `repo` and a matching relative `cwd`, for
example `code-poisson-astra`. Commands must resolve inside that selected worktree. Submit child specs only using
`tools/launch_run.py sandbox-start --request <approved-parent-id> --spec <child.json>`.

Both branches debit the SAME request id: budget, active cap and CPU allocations are checked under the existing
`LabDB.tx()` BEGIN IMMEDIATE lock. Independent parents would be independent budgets; do not create them.
Aggregate budget validation caps the parent at 160 CPU-h. Missing or invalid accounting refuses new reservations;
unknown failed-run duration retains its reservation. Completed runs use elapsed wall time times reserved cores,
the existing conservative accounting convention. JSONL ledger is an audit aid; DB rows and spec_entry metadata
supply accounting. A supervisor failing to spawn may leave a starting reservation; escalate rather than deleting it.
SQLite concurrency reference: https://www.sqlite.org/lang_transaction.html (checked 2026-10-29).

The reviewed environment is the peeled commit above (`cycle2-env-v1`). Cycle2 checks all tracked files in
`sim_v2/` and `experiments/dinos_simv2/`, plus `tuning/poisson_ms.py`, against that commit, and the shared harness
files `tuning/{pms_adapter,rppo,pms_reference}.py`, `tuning/legacy/{c5_protocol,orig_variants,run_legacy,env_orig}.py` against the peeled
`cycle2-harness-v1` commit (J40, Codex APPROVE r3; J48 added this pin; a branch needing other code in these files needs a new reviewed harness commit). Missing reference/working
bytes, altered bytes, wrong branch, extra Python sources in protected directories, and root Python startup
customizations fail closed. The supervisor repeats the check immediately before spawning; working files must
remain frozen throughout active runs. Legacy cycle1 parents retain their original qrl-dev checks. These guards
prevent operational mistakes; they do not isolate hostile Python code or provide an immutable filesystem.

J60 adds a separate digest pin for `tuning/cycle2_entry.py`, whose reviewed bytes postdate the harness freeze
(`cc83534:tuning/cycle2_entry.py`, identical in both branches). Both the parent digest and working file must
match the guard's reviewed constant. Missing/changed bytes refuse reservation and are checked again before spawn.
The environment and harness commit pins remain unchanged. J60's implementation/review status is recorded in
`.lab/j60/handoff.md`; this documentation is not an approval and the guard change requires independent review.

## Remaining approval dependency and budget contract

C46 instructed J41 to finish review/commit then hand off, with no idle monitoring. J40 must provide the actual
reviewed shared harness tag/CLI and trace/arm manifest. The next coordinator/worker then constructs ONE complete
parent, validates it against the real CLI, obtains Claude review of that concrete spec, checks pending requests
for duplicates and calls `labq.py ask --kind approval --scope sim --spec ... --thread M-20261029-006`.
Do not freeze an invented command or an unreviewed harness hash. No request has been filed by J41.

The concrete manifest must reconcile seven learning arms (plan §3) with the six-arm arithmetic in §5; J25's
`.lab/cycle2-codex/preparation.md` details the shortfall. Requested maximum is 160 CPU-h over seven days, cores
8-39, with at least 15% headroom: planned work at most 136 CPU-h, unallocated headroom at least 24 CPU-h
(arithmetic from the task's bound, not measured costs). Charge smoke, transfer-source pretraining, tuning,
validation, retries, final training and all evaluations. Retain at least 10 final seeds per learning arm, equal
tuning budgets and paired traces. Preserve test12 for one joint final freeze; smoke must not access it.

Actual costs are unknown until approved launcher smoke. Predeclare a measured cost gate for all seven arms,
including recurrent PPO and transfer source, then apply the same permitted scaling rule across arms/branches.
No tuning/final jobs may proceed unless the measured projection including final costs fits the planned envelope.
If it cannot fit while retaining final seeds, escalate the concrete shortfall; do not silently drop arms/seeds.
Exact seed ranges, stage allocation, retry policy, checkpoint rule, scaling rule and CLI are pending J40's manifest.

Engineering evidence: focused tests in `tests/test_cycle2_sandbox.py` and `tests/test_sandbox_worktrees.py`;
legacy regression `tests/test_lab.py::test_sandbox`. All use temporary fixtures, no experiment. Review transcripts
and handoff: `.lab/cycle2-launcher/` (key `cycle2-launcher`).

## Frozen amendment του ίδιου sandbox (J109 — εκκρεμεί Claude review)

Το `R-20261029-009` εγκρίνει την επιλογή σχεδιασμού, χωρίς frozen spec/hash· δεν εξουσιοδοτεί runs.
Το νέο `kind: sandbox-amendment` υποβάλλεται ως ξεχωριστό **approval**, χωρίς `entries`, `cwd` ή dummy command.
Το envelope έχει ακριβώς `kind`, `name`, `scope: sim`, `parent_request`, `parent_spec_hash`, `changes`, `review`.
Το `review` παγώνει ledger, stage stop rules, όρια και concrete screening manifests. Το `changes` επιτρέπει
ακριβώς `per_run_wall_clock_hours` (θετικό, έως 2.5h) και `cpu_hours_budget` (θετικό, έως136 και όχι μεγαλύτερο
του αρχικού). Όλα τα υπόλοιπα πεδία του αρχικού sandbox αντιγράφονται χωρίς αλλαγή. Δεν δημιουργείται δεύτερο
λογιστικό sandbox και δεν αλλάζουν αρχικό approval/spec, seeds, pins, expiry, affinity ή parallelism.

Workflow μετά τον ανεξάρτητο Claude έλεγχο του launcher, του ledger και του static RPPO audit:

1. Επαλήθευση draft με `taskset -c 4-7 .venv/bin/python .lab/j109/verify_draft.py`, έλεγχος pending για διπλό αίτημα,
   και υποβολή του συγκεκριμένου `.lab/j109/amendment-spec.json` με `labq.py ask --kind approval --scope sim --spec ...`.
   Η υποβολή παγώνει νέο hash. Καμία εκκίνηση/ενεργοποίηση πριν από την έγκριση του ερευνητή.
2. Με το πραγματικό νέο εγκεκριμένο request id: `python3 tools/launch_run.py sandbox-activate-amendment
   --request R-20261029-006 --amendment <new-approved-request-id>`. Η εντολή είναι μία γραμμή. Επανελέγχει και τα δύο
   frozen approvals/hash, protected bytes, expiry, μηδενικά starting/running runs και ήδη χρεωμένο κόστος ≤ νέο budget.
   Αποτυχία δεν καταγράφει μερική ενεργοποίηση. Δεν εφαρμόζει νέα όρια σε ήδη ενεργά runs.
3. Η ενεργοποίηση προσθέτει μόνο μία εγγραφή audit `sandbox-amendment`, με original parent hash και νέο request/hash.
   Επόμενα `sandbox-start` **και** `sandbox-status` χρησιμοποιούν πάντα `--request R-20261029-006` και επιλύουν αυτόματα
   το effective sandbox. Δεν υπάρχει flag παράκαμψης. Άμεσο `start` ή `sandbox-start` στο amendment απορρίπτεται.
4. Κάθε νέα κράτηση καταγράφεται αποκλειστικά στο αρχικό request. Μετρημένα παλιά κόστη, άγνωστα failed-run κόστη
   και πλήρεις active reservations συνυπολογίζονται στην ίδια `BEGIN IMMEDIATE` συναλλαγή με effective-spec resolution,
   budget check και insert. Το νέο run metadata κρατά parent hash, amendment request/hash και effective sandbox hash.
   Ο supervisor επανελέγχει το frozen effective sandbox πριν spawn.

Περιορισμοί: η υλοποίηση επιτρέπει μόνο ένα amendment ανά parent. Δεν υποστηρίζει chaining, rollback ή αλλαγές
ορίων ενώ υπάρχουν ενεργά runs. Αλλοιωμένο/άγνωστο/διπλό activation, αλλαγμένο hash ή μη εγκεκριμένο request
μπλοκάρει νέες εκκινήσεις. Τα ανά arm/stage όρια και τα scientific release gates είναι χειροκίνητη πολιτική,
όπως το smoke gate J64· ο launcher επιβάλλει συνολικό budget/parallelism, global per-run cap, pins/seeds/expiry.
Τα tests παραμένουν κλειδωμένα. Extension/final, original-HPA/probes και evaluators απαιτούν concrete manifest
και κοινό stage release· άγνωστα κόστη δεν γίνονται μετρήσεις επειδή έχουν δεσμευμένο pool.

Κατάσταση και στοιχεία: `.lab/j109/{GATES.md,gates.log,amendment-spec.json,snapshot.json,handoff.md}`.
Η τεκμηρίωση περιγράφει τον μηχανισμό· δεν αποτελεί έγκριση ή καταγραφή ενεργοποίησης.
