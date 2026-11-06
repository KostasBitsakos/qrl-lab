# Redis topology — απογραφή draft

| Αντικείμενο | Πηγή | Τεκμηριωμένο περιεχόμενο |
|---|---|---|
| Redis data plane | `code/real/redis-autoscale-cluster-deployment.yaml` | Stateless Deployment `redis-autoscale-cluster`, replicas 6, selector `redis: redis-cluster-pods-lbl`, nodeSelector `role: redis-workers`, image `capitanodocker/redis-autoscale-cluster:0.1` |
| Πόροι data pod | ίδιο YAML, `resources` | requests 150m CPU / 8Mi memory, limits 200m / 16Mi· ιστορικές τιμές, όχι εγκεκριμένο νέο budget |
| Data Service | `code/real/redis-autoscale-all-service.yaml`, πρώτο document | ClusterIP service `redis-cluster-service`, TCP 6379 προς data pods |
| Coordinator | `code/real/redis-cluster-coordinator-deployment.yaml` | Ένα replica, image `capitanodocker/redis-cluster-controller:0.1`, κανένα resource request/limit |
| Coordinator Service | `code/real/redis-autoscale-all-service.yaml`, δεύτερο document | TCP 6379, selector `app: redis-cluster-coordinator-lbl` |
| HPA | `code/real/redis-autoscale-cluster-hpa.yaml` | autoscaling/v2, ίδιο Deployment target, min 4 / max 20, memory 60%, CPU 50% utilization· δεν συνιστά νέο frozen control |

Προτεινόμενο namespace: `qrl-calib` (`docs/rules/paused.md`, R-20261016-018).
Τα ίδια ονόματα Service μπορούν να υπάρχουν εκεί ως διαφορετικά namespaced
objects· τα copied manifests παραμένουν χωρίς namespace. Το overlay είναι
ο μόνος προβλεπόμενος τρόπος σύνθεσης του draft.

`code/real/docker/redis-autoscale-cluster/entrypoint.sh`: καταχωρεί pod IP:6379
στην queue `REDIS_CLUSTER_REGISTRATION_QUEUE` μέσω του coordinator Service
(environment variables), κατόπιν ξεκινά Redis με protected mode off.
`docker/redis-autoscale-cluster/redis.conf`: cluster-enabled, port 6379,
appendonly, nodes.conf. Δεν υπάρχει PVC στο Deployment. Η απώλεια test data
είναι αποδεκτή μόνο στο μελλοντικά εγκεκριμένο calibration (paused rule).

`code/real/docker/redis-cluster-controller/entrypoint.sh`: εκκινεί Redis και
τρέχει `go install ...@latest` πριν από τον coordinator. Τα YAML χρησιμοποιούν
mutable tags· δεν έχει επιβεβαιωθεί ότι αυτά τα scripts αντιστοιχούν στα images.
Η εσωτερική-only egress policy σκοπίμως δεν επιτρέπει το download. Απαιτούνται
reviewed, pinned images πριν από λειτουργικό deployment· εδώ δεν χτίζονται.

Άγνωστα: cluster membership/roles/replication, slot assignment, cluster-bus
port που πράγματι χρησιμοποιούν τα images, image digests, recovery semantics,
client redirects, pod churn readiness, ενεργό CNI, διαθέσιμοι nodes και metrics
server. Το Service δεν είναι cluster-aware Redis client· μελλοντικός sender
χρειάζεται υποστήριξη redirects και διευθύνσεων εντός namespace.

Το draft policy επιτρέπει όλη την επικοινωνία μεταξύ pods του namespace,
χωρίς υπόθεση συγκεκριμένου cluster-bus port. Περιορίζει την επιλέξιμη κίνηση pods εντός namespace όταν το CNI το
εφαρμόζει και δεν υπάρχουν πρόσθετες policies που διευρύνουν την πρόσβαση.
Οι NetworkPolicies είναι προσθετικές· υπάρχουν εξαιρέσεις κίνησης node/host.
Δεν αποτελεί πλήρη εγγύηση δικτυακής απομόνωσης. Δεν επιτρέπει DNS/API/Internet. Οποιαδήποτε
εξαίρεση χρειάζεται νέα τεκμηριωμένη πρόταση, όχι γενικό άνοιγμα egress.
Δεν αντιγράφουμε dashboard admin RBAC, PV/StorageClass ή install scripts του
`code/real/k8s/`: είναι εκτός namespaced Redis draft και όχι επιτρεπτή εγκατάσταση.
