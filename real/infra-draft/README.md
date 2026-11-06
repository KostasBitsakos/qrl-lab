# Real infrastructure — offline draft J352

Εγκεκριμένη προετοιμασία: R-20261106-002(δ), brief `.lab/j345/brief_infra.md`.
**Calibration PAUSED** (`docs/rules/paused.md`). Δεν έχει γίνει deployment,
cluster query, εκτέλεση φορτίου ή βαθμονόμηση. Δεν υπάρχει online sender.

- `manifests/copied/`: αυτούσια αντίγραφα των τεσσάρων Redis YAML από `code/real/`.
  Το `COPY_MANIFEST.json` καταγράφει πηγές και SHA-256· προέλευση originals:
  `code/real/PROVENANCE.md`, `code/real/COPY_MANIFEST.json`.
- `manifests/kustomization.yaml`: ξεχωριστή πρόταση namespace `qrl-calib`,
  χωρίς αλλαγή των copied YAML. Τα copied αρχεία μόνα τους **δεν** ορίζουν namespace.
- `manifests/isolated/`: namespace και policy για επικοινωνία αποκλειστικά εντός του.
- `REDIS_TOPOLOGY.md`: τι τεκμηριώνεται από τις πηγές και τι παραμένει άγνωστο.
- `loadgen/generate.py`: seeded offline χρονοδιάγραμμα Redis RESP SET αιτημάτων,
  JSONL και metadata. Δεν ανοίγει σύνδεση, δεν περιέχει διεύθυνση Redis ή credentials.
- `loadgen/sim_poisson_ms.py`: αυτούσιο snapshot του simulator του J350
  (`code-poisson-c345/tuning/poisson_ms.py`, hash στο manifest).
- `RUNBOOK.md`: offline έλεγχοι και προϋποθέσεις μελλοντικού launch/rollback.

Η απομόνωση namespace αφορά namespaced resources, όχι εγγύηση δικτυακής
απομόνωσης. Η policy απαιτεί CNI με υποστήριξη NetworkPolicy· η λειτουργία του
πραγματικού CNI είναι άγνωστη. Οι policies είναι προσθετικές και αφορούν
επιλέξιμη pod κίνηση, με εξαιρέσεις node/host· απαιτείται έλεγχος και άλλων
policies πριν από οποιονδήποτε ισχυρισμό απομόνωσης. Πηγές:
[Kubernetes multi-tenancy](https://kubernetes.io/docs/concepts/security/multi-tenancy/),
[NetworkPolicy](https://kubernetes.io/docs/concepts/services-networking/network-policies/).
Το draft δεν πιστοποιεί εκδόσεις API, images, RBAC, DNS ή cluster readiness.

## Διαδικασία αιτημάτων

Ακριβώς η `poisson_ms` του snapshot: ανά tick,
`λ = base × (1 + amp sin(2πt/period + phase)) × burst × exp(x)`.
Ο burst state μεταβαίνει στα όρια tick με πιθανότητα `1-exp(-r)`· πρόκειται
για διακριτή αλυσίδα, όχι συνεχή CTMC. Το `x` είναι AR(1) log-noise.
`N ~ Poisson(λ)` και οι χρόνοι εντός tick είναι ταξινομημένα `Uniform(0,1)`.
Υπό δεδομένη διαδρομή ρυθμών είναι NHPP με σταθερό ρυθμό ανά tick· συνολικά
είναι Cox process με διακριτή Markov διαμόρφωση. Δεν προσθέτουμε θόρυβο στα counts.
Όλοι οι αριθμητικοί defaults προέρχονται από `Params` του snapshot, και γράφονται
στα metadata. CPU/memory measurement noise δεν είναι request noise.

Το seed χρησιμοποιεί το stream `STREAM_LOAD` της πηγής. Η γεννήτρια δημιουργεί
`PoissonMSEnv(...)`, καλεί ρητά `reset()` όπως το `run_fixed` της πηγής,
και χρησιμοποιεί το `.wl`, χωρίς queue steps ή policy. Κάθε trace αντιστοιχεί
σε αυτό το episode entry point· πρόσθετα resets αλλάζουν το trace του ίδιου seed.
Το `--tick-seconds` είναι υποχρεωτικό: μετατρέπει `t+offset` σε δευτερόλεπτα,
δεν επαναδειγματοληπτεί το count. Το λ σε req/s είναι `λ/tick_seconds`.
Η αντιστοίχιση αυτή είναι επιλογή draft, όχι μετρημένη φυσική βαθμονόμηση.

Το payload είναι synthetic `SET qrl-calib:<seed>:<id> x`· δεν ισοδυναμεί με
microservice call graph ή ρεαλιστικό Redis command mix. Κλειδιά χωρίς TTL·
μελλοντικό run απαιτεί memory budget, πλήθος requests και cleanup plan.
Το πρόγραμμα παράγει μόνο προγραμματισμένους χρόνους. Δεν μετρά achieved rate,
client backlog, Redis latency, CPU/memory ή performance scaling.
