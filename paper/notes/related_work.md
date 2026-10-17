# Related-work notes (verified 2026-10-16; abstracts only)

Format: key. Shows / Relation to us.

- lorido2014review. Surveys auto-scaling techniques for elastic cloud apps. / Background for learning-based autoscaling; frames DInos.
- harcholbalter2013performance. Textbook on queueing-based performance modelling (abstract-level: scheduling, heavy tails). / Basis for capacity-dependent latency in the simulator.
- little1961proof. Proves L = lambda W under stationarity conditions. / Sanity relation for simulator queue/latency consistency.
- dean2013tail. Techniques that keep latency tails low while raising utilization. / Motivates checking tails, not means, on the real cluster.
- hochreiter1997lstm. Gated recurrent unit for long time lags. / History-window agent baseline (classical LSTM).
- vanhasselt2016ddqn. Double DQN reduces Q overestimation on Atari. / Defines the true DDQN target we compare to.
- taylor2009transfer. Survey/taxonomy of transfer in RL. / Frames transfer vs training from scratch.
- jerbi2021parametrized. Hybrid quantum RL with few qubits on benchmarks; separation proof under discrete-log hardness. / Quantum policy baseline; the separation result is for constructed tasks, not ours.
- skolik2022quantum. VQC deep Q-learning; ablations; finds architecture/hyperparameters matter more than parameter count. / Directly supports needing parameter-matched classical controls.
- mari2020transfer. Pre-trained classical net plus final variational circuit; image and state classification, run on hardware. / Quantum transfer learning precedent; not RL, not autoscaling.
- calheiros2011cloudsim (metadata only). Standard cloud simulation toolkit for evaluating provisioning algorithms. / Cite only as the common simulator; we make no claim on its validation.
- mansouri2022fragmented (2026-10-17). Redis 6.0.11 cluster of 2/4/8 small VMs under YCSB: 8 nodes give at most 2x the 2-node throughput. / Only independent open-source datum suggesting theta < 1; testbed differs, so theta is calibrated, not imported.
- zhang2025kiss (2026-10-17). RL (PPO) autoscaler trained on a K8s GPU-inference simulator, beats CPU-HPA on P95; no simulator-vs-real validation shown. / Shows sim-trained RL autoscalers without a fidelity check; our calibration plus held-out check differs.
- sivko2022coroot (2026-10-17, blog). Default HPA took 2 min 5 s from CPU crossing target to scale-out on one EKS cluster, 30 s with 10 s metrics resolution. / Observation lag must be in the HPA baseline of Sim v2.
- Full Sim v2 realism review: paper/notes/sim_realism_review.md.
- chen2020qlstm. Hybrid VQC LSTM; reports faster convergence/accuracy in some tests (preprint). / QLSTM precedent; abstract claims are test-case specific, no matched-control claim.
