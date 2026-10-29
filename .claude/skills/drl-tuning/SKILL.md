---
name: drl-tuning
description: Equal-budget hyperparameter and architecture tuning for DQN/DDQN, LSTM (DRQN-style) and recurrent PPO autoscaler agents in QRL-Lab. Use when designing or running a tuning batch for any arm in cycle 2.
---
# Equal-budget DRL tuning
Sources and rationale: `docs/expert/drl_tuning.md`.
1. Budget per arm is fixed in `docs/cycle2_plan.md` §5 (configs × tuning seeds × ticks, CPU-h). Transfer arms pay
   pretraining from it. Measure CPU-h per run in the smoke test first; if it differs from 1.26 CPU-h/20k ticks
   (cycle 1), scale the number of configs for ALL arms equally.
2. Start from the incumbent (reward-div 10, obs-scale on, n-step 3 for DQN-family, linear10k ε, `c24_freeze.md`).
3. Declare the search space and trial count before launching; identical trial count per arm; screening at 5k ticks
   → top-2 per arm to 20k ticks.
4. Tuning seeds ≠ final seeds; val traces only. Selection rule: across-seed mean on val at locked checkpoint rule.
5. Any idea may be tried (architecture, features, reward shaping only if common to all arms) but it is charged to
   that arm's budget and recorded in `docs/EXPERIMENTS.md`.
6. Runs only through `tools/launch_run.py` with an approved spec; experiments on cores 8-39, tests on 4-7.
