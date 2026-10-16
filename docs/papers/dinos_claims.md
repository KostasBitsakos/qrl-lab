# DInos DEXA 2025: claims to reproduce

Source: `docs/papers/dinos_dexa_paper2025.pdf`. The text was extracted with pypdf, and the page numbers are the PDF pages.

| # | Claim | Where |
|---|---|---|
| C1 | Agents: enhanced DERP (2 dense layers of 128 units, ReLU, Double DQN) and DInos (LSTM + transfer learning; fine-tuning with batch size 16) | p.4 §3.2 |
| C2 | State: load, CPU, memory, latency, pods. Actions: add / remove / maintain, every 15 s | p.4, p.7–8 §4.1 |
| C3 | Reward = 3.0·next_load − 5.0·next_latency − 10.0·num_pods − 0.5·next_cpu − 0.5·next_memory | p.8 eq.(2) |
| C4 | Simulator: sinusoid + Gaussian noise + spike at timesteps 1500–1600, 5000 timesteps; Huber loss | p.6 §3.4–3.5 |
| C5 | Simulation: DERP 2.2×10^5 vs DInos 3.8×10^6 cumulative reward (17.3×) | p.9 §5.3, p.11 §5.6 |
| C6 | Training checkpoints compared at 1k, 2k, 5k, 10k and 20k steps | p.10 Fig.5 |
| C7 | Real K8s/Redis: DInos 308,000 vs LSTM without transfer 56,000 (5.5×), over 2000 timesteps. DERP was not run on the real cluster | p.9 §5.4, p.12 Fig.7 |
| C8 | HPA disabled. A custom Python environment uses the K8s API and reads the Metrics Server. Redis pods are stateless | p.8 §4.2 |
| C9 | Setup: Ubuntu 20.04 VM, 191 GiB RAM, 32 vCPU, Python 3.8, PyTorch | p.9 §5.1 |
| C10 | The paper reports CPU, memory and latency averages in a table, but that table is an image (Fig.8). Its numbers are not in the extracted text | p.13 Fig.8 |

Not stated in the paper: number of seeds, number of evaluation episodes, and whether the 5000-step evaluation uses the training trace.
