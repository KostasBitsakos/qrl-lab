---
name: poisson-workload
description: How to implement and test the cycle-2 Poisson microservice workload (homogeneous Poisson, NHPP by thinning, MMPP-2 bursts, noise on the rate) and the queue-based latency/CPU/memory env. Use when writing or reviewing workload or env code.
---
# Poisson workload + microservice env
Reference: `docs/expert/poisson_workloads.md`; spec: `docs/cycle2_plan.md` §2.
- Arrivals: per tick N_t ~ Poisson(Λ_t) with Λ_t = ∫ λ(s) ds over the tick; request-level mode uses exponential
  inter-arrivals (thinning for NHPP). Never sample Poisson-distributed *gaps* (DRe-SCale's bug).
- λ(t) = base · diurnal(t) · MMPP-2 burst factor · exp(AR(1) log-noise). Noise on the rate, never on counts.
- One `numpy.random.Generator` per trace, seeded from the trace id; train/val/test trace ids disjoint (plan §4).
- Required unit tests: dispersion ≈1 and KS vs Exponential for homogeneous λ; dispersion >1 for MMPP;
  same seed → identical trace; served load and p95 latency change with pods (PLAN §2 F1).
- Env outputs per tick: arrivals, served, queue, drops, mean/p95 latency, CPU util, memory, pods, pending pods (delay D=5).
