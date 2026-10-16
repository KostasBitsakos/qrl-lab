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
- chen2020qlstm. Hybrid VQC LSTM; reports faster convergence/accuracy in some tests (preprint). / QLSTM precedent; abstract claims are test-case specific, no matched-control claim.
