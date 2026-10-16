# Related work: outline (codex-researcher, gpt-6.1-sol, 2026-10-16)

All references here are CANDIDATES. Each one must be verified by DOI or arXiv before it enters refs.bib.
DERP, DInos and QuantuML are already verified in refs.bib.

1. **Learning-based cloud autoscaling.** From elastic provisioning to transferable autoscaling. Kubernetes/Redis is the evaluation setting. Separate the corrected DInos retraining from historical results affected by simulator defects.
   - Lorido-Botran, Miguel-Alonso, Lozano, *A Review of Auto-scaling Techniques for Elastic Applications in Cloud Environments*, J. Grid Computing 2014
2. **Queueing models and simulator validity.** Why the simulator needs capacity-dependent latency, startup delay and calibration on the real cluster.
   - Harchol-Balter, *Performance Modeling and Design of Computer Systems*, CUP 2013
   - Little, *A Proof for the Queuing Formula: L = λW*, Oper. Res. 1961
   - Dean, Barroso, *The Tail at Scale*, CACM 2013
3. **Temporal value learning and transfer.** History windows, a true DDQN, and transfer measured against training from scratch.
   - Hochreiter, Schmidhuber, *Long Short-Term Memory*, Neural Computation 1997
   - van Hasselt, Guez, Silver, *Deep RL with Double Q-learning*, AAAI 2016
   - Taylor, Stone, *Transfer Learning for RL Domains: A Survey*, JMLR 2009
4. **Quantum agents and hybrid adaptation.** Parameter efficiency is an empirical hypothesis that needs parameter-matched classical controls.
   - Jerbi et al., *Parametrized Quantum Policies for RL*, NeurIPS 2021 (arXiv 2103.05577)
   - Skolik, Jerbi, Dunjko, *Quantum agents in the Gym*, Quantum 2022 (arXiv 2103.15084)
   - Mari et al., *Transfer learning in hybrid classical-quantum neural networks*, Quantum 2020
   - Chen, Yoo, Fang, *Quantum Long Short-Term Memory*, arXiv 2009.01783 (2020)

**Positioning risks**
1. Reviewers will ask about quantum advantage. Simulator timings cannot establish a hardware speed-up.
2. A matched small classical agent may explain every gain. That would falsify any quantum-specific efficiency claim.
3. A simulator calibrated on mean behaviour may miss Redis latency tails and contention. Held-out workloads and replicating the ranking on the real cluster are essential.
