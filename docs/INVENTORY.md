# Inventory of the research code and results (2026-10-16)

Read-only. Sources: Explore reports, checked by the coordinator with `ls -l`, `git log` and direct reads. No original
file was modified. Mtimes are disk times. Paper claims are numbered as in `docs/papers/dinos_claims.md`.

## 1. Simulation: `~/simulations/redisk8s` (git, `timeseries/Pytorch`)

- **Branches.** There is no `valuation` branch. There are `evaluation` (checked out, = `origin/evaluation`),
  `evaluatio_2` and `main`. `evaluation` is the newest and most complete:
  - It is 8 commits ahead of `evaluatio_2` and 17 ahead of `main`.
  - `evaluatio_2` has only 16 files in `timeseries/Pytorch` (2024-06), and `main` has none.
  - The working tree is clean.
- **Commits on `evaluation`.**
  - `9a32518`, 2026-10-15, "for the multi-agents systens": adds `Quantum/`, `Quantum_lstm/` and `lstm_transfer_quantum_compare.py`. It does not touch `final_metrics_lstm`.
  - `bf98cac`, 2025-02-28, "final versions".
  - `9c9cd61`, 2025-01-14, "final version".
- **DInos+transfer (best match to the paper, about 60% confidence).**
  - Script: `lstm_transfer/lstm_transfer.py`, which fine-tunes with batch 16 (`:139`, matching C1) and then runs 5 evaluation episodes of 5000 steps each.
  - Models: `lstm_transfer/final_metrics_lstm/modelCPU_{1,2,5,10,20}_fine_tuned.pth`, 2025-02-03 13:27–13:35.
  - Reward: `lstm_transfer/environment.py:88–96`, which is equation (2) of the paper (C3).
- **Per-episode rewards** (`final_metrics_lstm/model_*/rewards.txt`, 2025-02-03):

  | Model | Per episode | Sum of 5 episodes |
  |---|---|---|
  | model_2 | ≈723k | 3,617,616 |
  | model_5 | ≈723k | 3,616,592 |
  | model_1 | | 3,280,882 |
  | model_20 | | 3,228,498 |
  | model_10 | | 2,822,113 |

- **Earlier results.**
  - `final_metrics/model_*/rewards.txt` (2025-02-03 13:12) have a first episode of 208k–324k, then values near 0. Which agent wrote them is unknown, possibly `doubledeepCPUfinal.py`.
  - `dense/rewards2_*.txt` date from 2024-07.
- **Seeds.** None anywhere (grep for "seed" finds nothing).
- **Match with the paper.**
  - C5 (DInos 3.8×10^6, DERP 2.2×10^5): no file contains 3.8×10^6. The closest are the 5-episode sums of about 3.62×10^6.
  - 2.2×10^5 is close to a single episode in `final_metrics/model_5` (216,795).
  - Whether the paper compares a 5-episode sum against one episode is unknown. The researcher can confirm.
- **Known problems** (PLAN §2): F1–F5 apply here. In particular, "always scale down" scores 728k per episode, more than any stored model.

## 2. Real cluster: `~/redis/autoscaling-redis-cluster-hpa-kubernetes` (git)

- **Git.** Everything from 2024–25 entered git only in `f1a3f74` (2026-10-15). There is no history before that, so file dates are the only evidence.
- **`metrics-new/` (2024-10) is not the real experiments.** It holds:
  - a load generator: `stress.py`; and `stress2.py`, whose latency is `np.random.uniform` (`:76`)
  - PNG plots
  - `hpa.txt` with 4 reward totals (−126,011 / −403 / −821 / −24,822)
  It has no agent and no raw data.
- **2024 agent on the cluster.** `metrics-lstm/stress2.py` and `stresslstm.py` (2024-10). They use LSTM `modelCPU_10.pth` and scale through the Python client, namespace `default`, deployment `redis-autoscale-cluster`.
- **2025 real-world experiments** (`experiments/`). The `accumulated_rewards.txt` files are written by `real_world_experiment*.py` as `sum(rewards_data)`:

  | Path | Date | Total |
  |---|---|---|
  | `experiments/metrics/` | 2025-02-03 | −465,856 |
  | `experiments/new_metrics/` | 2025-02-05 | 563,963 |
  | `experiments/lstmtransfer/transfer_learning_metrics/` | 2025-02-05 | 532 |
  | `experiments/lstmtransfer/new_metrics/` | 2025-02-07 | 57,193 |
  | `experiments/lstmtransfer/new_metrics2/` | 2025-02-25 | 79,178 |

  The `new_metrics2` run has a 79 MB `autoscaler.log` covering 2025-02-24 to 2025-02-25, timesteps up to 1999.
- **Latest real-cluster code.** `experiments/lstmtransfer/vector_redis/vector_experiments_vs2.py` (2025-04-04) with `modelCPU_5.pth` (2025-03-31). It scales with kubectl and also covers the redis-stack/vector YAMLs of 2025-04-04 to 2025-04-08.
- **Match with C7 (DInos 308,000 vs 56,000).**
  - No measured file contains 308,000.
  - `experiments/new_metrics/real_world_rewards.py:5` has `rewards = [56000, 56000 * 5.5]`, with the comment `# 56,000 vs. 56,000 × 5.5 = 308,000`. It draws the bar chart `real_world_experiments_rewards.png` (2025-02-28).
  - `experiments/lstmtransfer/final_metrics/final2.py` (2025-02-25) builds a synthetic sinusoidal reward curve: "to achieve ~2 million total", "~3.5× bigger" (`:8–23`).
  - `final3.py` builds a synthetic curve "that sums to ~563,963", saved as `previous_results.png` (`:12–47`).
  - The measured total closest to 56,000 is 57,193 (`lstmtransfer/new_metrics`, 2025-02-07).
  - Whether the published Fig.7 and the totals in §5.4 came from these scripts is for the researcher to say (D8).

## 3. Deployment: `~/k8s`, `~/prometheus-grafana`, manifests

- **Cluster bootstrap.** `~/k8s/install.sh` (docker + kubeadm), `initialize.sh` (kubeadm init, pod CIDR 10.244.0.0/16), `config.sh` (kubeconfig) and `pod_netowrk.sh` (Calico).
- **Redis manifests** (in the redis repo):
  - `redis-autoscale-all-service.yaml` (Services)
  - `redis-cluster-coordinator-deployment.yaml`
  - `redis-autoscale-cluster-deployment.yaml`: 6 replicas, nodeSelector `role=redis-workers`
  - `experiments/lstmtransfer/coordinator-pdb.yaml`
  - The order is in `scrpit.sh:4–14`.
  - `redis-autoscale-cluster-hpa.yaml` exists but would fight the agent's scaling.
- **Unknown:** the metrics-server manifest, how nodes were labelled, and the namespace of the 2025 agent (none is set in the code).
- **Monitoring.** `~/prometheus-grafana` runs in namespace `monitoring` (NodePorts 30000/31000/32000) plus kube-state-metrics. The agent does not query Prometheus.
- **kubectl.** Client v1.28.2, one context `kubernetes-admin@kubernetes`. The API server is down (PLAN F7).

## 4. Researcher answers

- The DEXA paper was submitted in March 2025 (researcher, 2026-10-16). That fits `bf98cac` (2025-02-28) and the
  February agent in `experiments/lstmtransfer/`, not `vector_redis/` (April). The remaining questions are asked in the dashboard chat.
