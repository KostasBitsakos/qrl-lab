# Tutorial notes — researcher's questions and our answers (for the final tutorial)
Collected on request (M-20261023-023). Each entry: question → short answer → source. To be turned into the tutorial later
(style guide: memory "tutorials-request").

## The experiment loop (pipeline)
Q (M-20261023-019): what is the pipeline? what are train, val, test, steps?
A: idea (Claude + Codex, rule fixed in advance) → code (engineer) + Codex review → training with many seeds → select on val only →
freeze → ONE final test on never-used data → report. train = the runs the agent learns on (one seed = one random training run);
val = 5 held-out episodes used only to choose checkpoint/settings; test9 = 20 episodes, development check; test10/test11 = 20 episodes
each, measured once for final confirmation; tick/step = one simulator step = one scaling decision; checkpoints at 1k/2k/5k/10k/20k
training ticks, the val-best one is kept.

## Episodes and ticks
Q (M-20261023-021): if an episode has 5000 ticks, how is a model trained for 1000 ticks? What is an episode?
A: an episode = one continuous simulation of 5000 ticks with one workload trace (sinusoid + noise + spike), starting from a reset.
Training is a continuous stream of ticks (20,000 = 4 episodes; at the end of an episode the env resets). The "1k checkpoint" is a copy
of the network after 1000 training ticks (1/5 of the first episode). Every checkpoint is EVALUATED on full 5000-tick episodes (greedy,
no learning). Source: code-tuning/tuning/legacy/c5_protocol.py:22,36.

Q (M-20261023-023): why "episode"? Do val/test have episodes? Is the test 2000 steps, missing the spike?
A: "episode" is the RL term for one trial from a reset to an end point: returns are summed per episode, and separate episodes are
independent repetitions (different random trace), which is what lets us average and build confidence intervals. In our protocol
val and test ARE episodes of 5000 ticks (run_legacy.py:125 EP_TICKS = 5000; every result JSON records eval_episode_ticks = 5000,
e.g. the test10 run spike300_d5-transfer_a1h-…-s60.json). The spike starts at tick 1500 (env_orig.py:19 spike_position = 1500) and
lasts 100 ticks, so every val/test episode contains the spike. The "2000 steps" was not our test length (unknown origin; possibly an
older protocol or the original code) — it does not apply to any result we report.
