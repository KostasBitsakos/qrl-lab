# Runbook draft και rollback — PAUSED

Εξουσιοδότηση μόνο για αρχεία και offline unit tests: R-20261106-002(δ).
Καμία εντολή cluster δεν εκτελείται ούτε παρέχεται ως script σε αυτό το draft.
Δεν υπάρχει experiment batch προς καταχώριση ή launch στο J352.

## Offline επαλήθευση

Από τη ρίζα `~/qrl-lab`, στο υπάρχον venv, χωρίς installs:

```bash
taskset -c 4-7 .venv/bin/python real/infra-draft/verify_draft.py
taskset -c 4-7 .venv/bin/python -m unittest discover -s real/infra-draft/loadgen -p 'test_*.py' -v
```

Το πρώτο επαληθεύει bytes/SHA-256, allowlist resources και τη δομή overlay.
Δεν αποδεικνύει Kustomize rendering ή αποδοχή από API server. Το δεύτερο
ελέγχει ακριβή ταύτιση με την πηγή simulator, reproducibility, χρονική κλίμακα,
RESP framing, Poisson sanity checks, metadata και άρνηση overwrite.
Οι διαγνωστικές δειγματοληψίες είναι unit tests, όχι benchmark ή calibration.
Εξαρτήσεις: τα ήδη εγκατεστημένα numpy, scipy, PyYAML στο venv.

Μικρό offline παράδειγμα (μόνο τοπικό αρχείο· seed/ticks/time scale είναι
παράμετροι παραδείγματος, όχι frozen experiment spec):

```bash
taskset -c 4-7 .venv/bin/python real/infra-draft/loadgen/generate.py --seed 17 --ticks 2 --tick-seconds 1 --output .lab/j352/example-requests.jsonl
```

Η έξοδος δεν περιέχει host και δεν αποστέλλεται. Το sidecar καταγράφει params,
seed, tick mapping, source hash και schedule hash. Δεν επαναχρησιμοποιείται ως
test12 ή άλλη ερευνητική split. Η CLI αρνείται ήδη υπάρχον output ή sidecar.
Το generator δεν περιορίζει το σύνολο requests: μεγάλα horizons απαιτούν
ξεχωριστό προϋπολογισμό δίσκου· αυτό δεν είναι έτοιμος transport driver.

## Προϋποθέσεις μελλοντικής ενεργοποίησης

1. Ρητή άρση pause, έγκριση ανά real run με frozen spec μέσω
   `tools/launch_run.py`· context και namespace ονομαστικά, διάρκεια, seeds,
   tick-seconds, offered rate, command mix, CPU/memory/disk budget και stop limits.
   Καμία παλιά έγκριση δεν θεωρείται άδεια launch τώρα (`docs/PLAN.md` §6).
2. Offline render του `manifests/kustomization.yaml` με εγκεκριμένο εργαλείο,
   review του αποτελέσματος: όλα τα namespaced resources σε `qrl-calib`,
   μοναδικό Namespace αυτό, κανένα default, RBAC, PV, StorageClass ή Node object.
   Έπειτα, με χωριστή άδεια, API compatibility και προέλεγχοι πραγματικού cluster.
3. Pinned/prebuilt coordinator/data images, επιβεβαίωση ότι δεν εγκαθιστούν
   κώδικα κατά την εκκίνηση, έλεγχος Service env discovery και Redis cluster repair.
   Η σημερινή policy αποκλείει Internet/DNS/API egress: το legacy startup δεν
   θεωρείται λειτουργικό. Το εσωτερικό client πρέπει να έχει static/ελεγμένη
   ανακάλυψη endpoints ή reviewed στενή εξαίρεση DNS.
4. Εγκεκριμένα requests/limits και για coordinator, quota/budget για namespace,
   έλεγχος ελεύθερων resources, node labels και CNI policy enforcement.
   Τα αντιγραμμένα resource settings είναι ιστορικά, όχι νέα πρόταση sizing.
   Τα YAML δεν παρέχουν readiness probes· cluster readiness απαιτεί ανεξάρτητο
   gate (slot coverage/roles/health), όχι απλώς running pods.
5. Namespace-scoped credentials/RBAC μέσω του εγκεκριμένου μηχανισμού,
   χωρίς ανάγνωση/εμφάνιση secrets από agent. Μόνο ένας autoscaler writer:
   HPA και RL δεν ελέγχουν ταυτόχρονα το ίδιο Deployment. Το copied HPA
   χρειάζεται ξεχωριστό freeze ως baseline· οι αριθμοί του δεν αλλάζουν εδώ.
6. Reviewed online sender εντός namespace με open-loop dispatch βάσει absolute
   monotonic deadlines, cluster-aware redirects, bounded in-flight requests,
   connect/response timeout και ρητή πολιτική late/dropped offers. Καταγραφή
   scheduled/actual send/completion, errors και client backlog ώστε η client
   επιβράδυνση να μη μετατρέπει το φορτίο σε closed loop.
7. Freeze payload/key TTL/cleanup, Redis memory guard, SLO και metrics πριν από
   εκτέλεση. Ο simulator latency proxy δεν θεωρείται παρατηρημένη Redis latency.
   Scale recovery/fix/rebalance μετριούνται όπως ορίζει `docs/rules/paused.md`.

## Stop και rollback (μελλοντικό, υπό χωριστή άδεια)

- Stop limits καθορίζονται στο frozen spec· επί υπέρβασης σταματά πρώτα ο
  sender και νέες scaling αποφάσεις. Κρατιούνται τα local logs, spec και hashes.
- Επιβεβαιώνεται το εγκεκριμένο context και ότι το `qrl-calib` δημιουργήθηκε
  αποκλειστικά για το συγκεκριμένο run. Αν υπάρχει ήδη namespace με ξένα
  workloads/data, το launch σταματά· δεν αναλαμβάνουμε ownership.
- Με την εγκεκριμένη διαδικασία καθαρίζεται μόνο το test namespace `qrl-calib`
  και τα δικά του namespaced resources. Αυτή είναι η σχεδιασμένη rollback
  ενέργεια του R-20261016-018, όχι άδεια εκτέλεσης στο παρόν task.
- Επαληθεύεται η απουσία test resources και ότι το `default`, cluster-wide
  resources και ξένα workloads έμειναν ανέπαφα· τα evidence προσαρτώνται στον run.
- Η απώλεια synthetic Redis data είναι αναμενόμενη· δεν υποσχόμαστε restore.
  Δεν αλλάζουν originals, context defaults, cluster nodes ή shared services.
