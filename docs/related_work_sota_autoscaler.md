---
description: Scholar search (22/10) for one published autoscaler baseline - DRe-SCale, AWARE, gym-hpa/Gwydion, with verification levels
---
# Related work: one state-of-the-art autoscaler baseline for the CCGrid paper

Date: 2026-10-22 · author: scholar · status: search report, not yet in `paper/refs.bib`
Verification levels used below:
- OPENED = I read the primary page, paper text or repository file myself in this session.
- META = bibliographic metadata only (OpenAlex / DOI redirect); full text not read.
- SEARCH-ONLY = known only from a search-engine summary; marked "unverified".
Citation counts are OpenAlex `cited_by_count` on 2026-10-22 (arXiv records are counted separately from
the published version, so they under-count). Semantic Scholar returned HTTP 429, so no second source.

---

## Περίληψη για τον Κώστα (ελληνικά)

Κώστα, συνοπτικά:

- **Πρόταση για ΕΝΑ baseline:** ο **LSTM-PPO (RecurrentPPO) του DRe-SCale** (Agarwal, Rodriguez, Buyya,
  IEEE Trans. Services Computing 2024). Είναι δημοσιευμένος, με ανοιχτό κώδικα (Apache-2.0), recurrent deep RL
  για horizontal autoscaling, με Poisson αφίξεις στην αξιολόγησή του, και χτίζεται πάνω στο
  `sb3_contrib.RecurrentPPO`. Άρα περνάει σε δικό μας Gym wrapper του simulator με μικρή προσπάθεια.
- **Πρέπει να το πούμε καθαρά:** ο κώδικάς τους τρέχει μόνο σε ζωντανό cluster (OpenFaaS/MicroK8s) και έχει
  placeholders (`${PROMETHEUS_URL}` κ.λπ.). Δεν μπορούμε να «τρέξουμε τον κώδικά τους» όπως είναι· μεταφέρουμε
  τον agent (αρχιτεκτονική + hyperparameters) στο δικό μας environment. Αυτό είναι re-implementation και
  πρέπει να γραφτεί ως τέτοιο.
- **Εναλλακτικές:** (2) AWARE (ATC 2023): το πιο σχετικό με το δικό μας transfer, αλλά DDPG με συνεχείς
  ενέργειες και ~60 μέρες meta-training στο paper, άρα υψηλό κόστος. Δεν μπόρεσα να ανοίξω το repo
  (GitLab του Illinois μη προσβάσιμο από το VM). (3) gym-hpa (NOMS 2023): έχει Redis Cluster environment
  αλλά το sim του είναι replay δεδομένων και η άδεια του κώδικα δεν ορίζεται καθαρά.
- **Υποχρεωτικό δίπλα σε κάθε RL baseline:** tuned HPA με πραγματικό delay. Ένα 2026 benchmark (preprint)
  βρίσκει ότι ένας καλά ρυθμισμένος rule-based controller νικά 6 DRL αλγορίθμους σε κόστος.
- **Προσοχή:** κοντινότατο prior art με δική μας αρχιτεκτονική (DDQN + LSTM forecaster): Lipari et al.,
  IPDPSW 2025. Πρέπει να το αναφέρουμε και να εξηγήσουμε τη διαφορά.
- **Προϋπόθεση:** PLAN §2 F1. Όσο ο simulator ανταμείβει μόνο το «scale down», κάθε baseline μαθαίνει το
  ίδιο. Η σύγκριση έχει νόημα μόνο στο Sim v2.

---

## 1. Search method (what was covered)

- OpenAlex queries on RL autoscaling / Kubernetes / transfer / meta-learning / predictive autoscaling, plus a
  source-filtered query on CCGrid (IEEE and IEEE/ACM series).
- Direct checks of USENIX (ATC 2023, OSDI 2020, NSDI 2024), arXiv, DOI redirects, GitHub API (license,
  language, `pushed_at`, file tree), Zenodo API.
- DBLP is blocked for this VM (Anubis access-denied page), so DBLP-based venue sweeps were not possible.
  Coverage of SoCC, Middleware, EuroSys, NSDI, ATC, TPDS/TCC/TNSM, CLOUD, IC2E, UCC, ICSOC, INFOCOM, CNSM is
  therefore through OpenAlex keyword search and named-paper checks, not an exhaustive proceedings sweep.
  This is a limitation of this report.
- PDF full text was read through the public converter `r.jina.ai/<pdf url>` for public papers
  (AWARE, gym-hpa extended paper, Schuler, RLScale-Bench). Output was used only where it matched primary pages.

## 2. Candidate table

Legend for code: runnable-sim = can train/evaluate without a real cluster as shipped.

| # | Candidate | Venue, year | Scales | Method | Code | Runnable-sim | Cites |
|---|---|---|---|---|---|---|---|
| A | DRe-SCale (LSTM-PPO, PPO, DRQN, SAC+LSTM) | IEEE TSC 2024 | function replicas | Recurrent PPO | Apache-2.0 | no (live OpenFaaS) | 56 |
| B | AWARE | USENIX ATC 2023 | replicas + CPU/RAM limits | Meta-RL over DDPG | GitLab (unopened) | no (K8s) | not in OpenAlex |
| C | gym-hpa (+ NOMS 2025 extension) | NOMS 2023 / 2025 | pods per deployment | PPO / A2C / DS-PPO | license unclear | dataset replay only | 44 / 2 |
| D | Lipari et al. DDQN + LSTM forecast | IPDPSW 2025 | replicas | DDQN + LSTM predictor | no LICENSE file | partly (unverified) | 3 |
| E | Schuler et al. | CCGrid 2021 | Knative concurrency limit | tabular Q-learning | none stated | no | 111 |
| F | Rossi, Nardelli, Cardellini | IEEE CLOUD 2019 | replicas + container CPU | Q-learning / model-based RL | none found | unknown | not queried |
| G | COLA | arXiv 2021 (v3 2022) | pods + VMs | UCB1 bandit, offline | none found | no | 1 |
| H | FIRM | OSDI 2020 | per-container limits | DDPG | none on page | no | 146 |
| I | Autothrottle | NSDI 2024 | CPU throttle targets | bi-level, learned top level | none found | no | 5 (arXiv rec.) |
| J | Autopilot | EuroSys 2020 | tasks + limits (Borg) | ML recommender + heuristics | none (internal) | no | 304 |
| K | Chameleon (non-RL, forecast + reactive) | IEEE TPDS 2019 | VM/instance count | forecast ensemble + reactive | none found | no | 66 |
| L | Predictive HPA (jthomperoo) | open source | replicas | Holt-Winters / regression | Apache-2.0, Go | needs K8s | n/a |
| M | MagicScaler | PVLDB 2023 | instances | uncertainty-aware forecast + optimisation | not checked | unknown | 50 |
| N | PBScaler | IEEE TSC 2024 | microservice replicas | bottleneck localisation + optimiser | MIT | needs K8s + call graph | 44 |
| O | Showar | SoCC 2021 | replicas + sizes | variance sizing + control theory | only 3rd-party reimplementation seen | no | 68 |
| P | Sinan | ASPLOS 2021 | per-tier CPU | CNN + boosted trees | none found | no | 229 |
| Q | DeepScaler | IEEE/ACM ASE 2023 | microservice replicas | spatio-temporal GNN | not checked | unknown | 43 |
| R | AHPA (Alibaba) | AAAI 2023 | pods | forecast + rules | already in refs.bib (`zhou2023ahpa`) | no | 43 |

Rows I did not open beyond metadata (F, M, O, P, Q, R) are context only and are not baseline candidates.

## 3. Serious candidates in detail

### A. DRe-SCale (recommended)
- Citation: S. Agarwal, M. A. Rodriguez, R. Buyya, "A Deep Recurrent-Reinforcement Learning Method for
  Intelligent AutoScaling of Serverless Functions", IEEE Trans. Services Computing, 2024,
  DOI 10.1109/TSC.2024.3387661 (META); preprint https://arxiv.org/abs/2308.05937 (v2 Nov 2024, OPENED via HTML).
- Scales: OpenFaaS function replicas, 1..24, action = replica delta in {-2,-1,0,+1,+2} per 30 s window (OPENED, `env.py`).
- Learning: `sb3_contrib.RecurrentPPO`, "MlpLstmPolicy", 1 LSTM layer with 256 units, actor and critic MLPs
  [64,64], `n_steps=128`, `n_epochs=10`, `batch_size=128`; learning rate, gamma, clip and entropy left at SB3
  defaults; 99 x 1000 = 99,000 training steps (OPENED, `scaling-agents/LSTM-PPO/agent.py`).
- State (6 values): average execution time, throughput ratio, request count, replicas, CPU per request,
  memory per request. Reward: `0.75*T^2 + 0.125*C + 0.125*M - 0.25*(R-1)^2`, with -100 for invalid or unmet
  scaling targets (OPENED, `env.py`).
- Workload: open Azure Functions 14-day trace, inter-arrival times sampled from a Poisson distribution, Hey
  load generator, matmul function; real MicroK8s/OpenFaaS cluster (arXiv HTML, OPENED).
- Baselines in paper: PPO, DRQN (LSTM + DQN), CPU-threshold HPA at 75 %, OpenFaaS RPS scaling.
- Code: https://github.com/SidAg26/DRe-SCale (upstream; Apache-2.0, Python, 11 stars, last push 2026-02-01) and
  fork https://github.com/Cloudslab/DRe-SCale (MIT per API, last push 2024-07-11). Both via GitHub API.
  Also holds SAC and SAC+LSTM agents.
- Runnable without a cluster: **no**. `env.py` talks to the Kubernetes API, metrics.k8s.io and Prometheus and
  contains unrendered `${PROMETHEUS_URL}`, `${MODEL_NAME}` placeholders; pod readiness is not checked, only a
  fixed 30 s sleep. The agent file also has placeholders in paths. The README has no run instructions.
- Their DRQN is **not** a fair DDQN: plain max target, no `done` mask, sequence length 1, epsilon fixed at 0.1,
  target synced by episode count (OPENED, `DRQN/agent.py`). Do not use it as a stand-in for our agent, and
  do not copy its problems (our own F3 list is similar).
- Port effort: **low-medium.** Write a Gymnasium wrapper over our simulator; instantiate `RecurrentPPO` with
  the published architecture; keep their hyperparameters as the "as published" arm and add a tuned arm.
  Main work: mapping observations (their 6 values to our load, capacity, CPU, memory, latency, pods),
  mapping actions (their +-2 to our set), and the reward (see section 5).

### B. AWARE (strongest on adaptation, too costly to port)
- Citation: H. Qiu, W. Mao, C. Wang, H. Franke, A. Youssef, Z. T. Kalbarczyk, T. Basar, R. K. Iyer, "AWARE:
  Automate Workload Autoscaling with Reinforcement Learning in Production Cloud Systems", USENIX ATC 2023,
  pp. 387-402, https://www.usenix.org/conference/atc23/presentation/qiu-haoran (OPENED; page shows three
  artifact badges: Available, Functional, Results Reproduced, inferred from image file names).
- Scales: replicas **and** CPU/RAM limits (multi-dimensional pod autoscaler).
- Learning (from the PDF text via converter): DDPG base learner taken from FIRM; a bidirectional-RNN meta-learner
  producing a workload embedding fed to the actor; bootstrapping for safe exploration. State = limits,
  utilisation, SLO preservation ratio, load change. Reward as in FIRM. Evaluated on 1,000 synthetic apps
  built from 16 workload segments (800 train / 200 eval) and Azure traces on 11 physical nodes. Baselines:
  HPA/VPA, transfer learning (FIRM), TL+.
- Reported: adapts 5.5x faster than transfer learning; meta-learner training about 312 hours within a 60-day
  total runtime.
- Code: paper states an open-source implementation at https://gitlab.engr.illinois.edu/DEPEND/aware. **Not
  opened**: the host refused connections from this VM (ECONNREFUSED). README content (FIRM/DDPG, DQN, PG agents,
  MPA deployment scripts, Python 3.10) comes from a search summary only: unverified. License and last commit unknown.
- Related note: the multidimensional pod autoscaler PR to kubernetes/autoscaler (#5920) was closed unmerged on
  2023-07-29 and split into #5999 (OPENED).
- Port effort: **high.** Continuous DDPG actions vs our discrete three actions, a meta-training set of
  hundreds of applications, and no simulator. Value for us is as the transfer-learning reference point.

### C. gym-hpa and its NOMS 2025 extension (domain match: Redis)
- Citation: J. P. P. dos Santos, T. Wauters, B. Volckaert, F. De Turck, "gym-hpa: Efficient Auto-Scaling via
  Reinforcement Learning for Complex Microservice-based Applications in Kubernetes", IEEE/IFIP NOMS 2023,
  DOI 10.1109/NOMS56928.2023.10154298 (OPENED abstract on imec repository). Extension: J. Santos, E. Reppas,
  T. Wauters, B. Volckaert, F. De Turck, "Can Reinforcement Learning be Generalized for Efficient Auto-Scaling
  in Containerized Clouds?", NOMS 2025, DOI 10.1109/NOMS57970.2025.11073717 (venue and DOI from OpenAlex,
  text read through converter).
- Code: https://github.com/jpedro1992/gym-hpa (Python, 21 stars, last push 2025-01-08). The GitHub API reports
  license `NOASSERTION`; README only carries a copyright line for Ghent University and IMEC. **License unclear.**
  Dataset on Zenodo (record 7944661, license `other-nc`, two CSVs of about 7-9 MB).
- Environments: Redis Cluster (leader and follower deployments, 1-8 pods each, `MultiDiscrete([2,15])` actions)
  and Online Boutique. `run.py` offers PPO, RecurrentPPO and A2C; episodes are 25 steps (OPENED).
- Simulation mode replays recorded rows matching pod counts, not a model; no pod startup modelling
  (real mode sleeps 0.3 s, no readiness check). The extension paper trains DS-PPO (DeepSets) for 200K steps and
  compares with earlier A2C results, with no HPA baseline reported (converter text).
- Port effort: **low-medium** for the agent classes, **but** their environment is not our simulator, and a
  reviewer will ask why a Redis leader/follower, multi-deployment agent is used for a single worker pool.
  Venue is network management, not a systems venue like CCGrid. CORE rank not checked.

### D. Lipari, Proietti Mattia, Beraldi: closest prior art (must cite, weak baseline)
- Citation: "Dynamic and Forecast-Based Containers Autoscaling for Kubernetes with Reinforcement Learning",
  IEEE IPDPS Workshops 2025, DOI 10.1109/IPDPSW66978.2025.00169 (OPENED abstract via IEEE page through
  converter; OpenAlex: 3 citations). DQN agent plus LSTM request-rate forecaster; claims up to 10 % fewer
  resources and up to 30 % better performance than default Kubernetes autoscaling.
- Code: https://github.com/alfredoLipari/CustomAutoscaler-k8s (Python, last push 2025-03-07; the GitHub API
  lists no license while the README says MIT; the README cites UCC 2025 as venue, which conflicts with the IEEE
  record). Agent file implements a true Double-DQN target, Polyak tau = 1e-3, prioritised replay, epsilon decay
  applied per step. State has 5 values (CPU, rate, replicas, predicted rate, rate change). Their workload
  generator is sinusoids plus random walk, no Poisson, no spikes (OPENED).
- Weaknesses for a baseline: 1 star, `environment.py` does not compute the reward or apply actions, README
  says training can run in simulation but I did not find or run the training path. A reviewer
  comparison to it is likely because it is almost our architecture. Cite it and state the differences
  (transfer learning, quantum parts, delay model).

### E. Schuler et al., CCGrid 2021 (venue-relevant, different problem)
- Citation: L. Schuler, S. Jamil, N. Kuhl, "AI-based Resource Allocation: Reinforcement Learning for Adaptive
  Auto-scaling in Serverless Environments", IEEE/ACM CCGrid 2021, DOI 10.1109/CCGRID51090.2021.00098
  (OPENED via arXiv text; arXiv:2005.14410).
- Tabular Q-learning (alpha 0.5, gamma 0.9), state = concurrency limit, CPU and memory bins, action = change the
  Knative concurrency limit by -20/0/+20, reward = throughput relative to best seen. Two IBM Cloud clusters,
  Knative v0.12, synthetic Autoscale-go workload, baseline Knative default. No code statement found.
  Use as CCGrid-lineage related work, not as baseline (it tunes a threshold, not replica counts).

### F. Further related work (cite, do not run)
- Rossi, Nardelli, Cardellini, IEEE CLOUD 2019, pp. 329-338, DOI 10.1109/CLOUD.2019.00061 (META):
  Q-learning and model-based RL for horizontal and vertical container elasticity. TCC follow-up
  (DOI 10.1109/TCC.2022.3163357, META). No code found.
- COLA, Sachidananda and Sivaraman, arXiv:2112.14845 (OPENED via ar5iv): offline UCB1 bandit over microservice
  VM allocations, 53 of 63 workloads met target, DQN baseline inspired by FIRM. Venue not stated on the
  arXiv page. No code found. An earlier belief that this is a SoCC paper is **unverified**.
- FIRM, OSDI 2020, pp. 805-825 (OPENED): DDPG, per-container limits, no code link on the page.
- Autothrottle, NSDI 2024, pp. 149-165, arXiv:2212.12180 (OPENED): no code link found on either page.
- Autopilot, EuroSys 2020, DOI 10.1145/3342195.3387524 (META + Google Research page via search): internal,
  no public code. The right reference for "strong industrial predictive autoscaler".
- Chameleon, IEEE TPDS 2019 (30:4, pp. 800-813), DOI 10.1109/TPDS.2018.2870389 (META): forecasting ensemble plus
  reactive fallback; Wuerzburg tool page does not link any code and BUNGEE is "no longer maintained".
- Predictive HPA: https://github.com/jthomperoo/predictive-horizontal-pod-autoscaler (Apache-2.0, Go, 383
  stars, last push 2023-10-11; statistical models). A practical non-RL predictive reference, but needs a K8s
  cluster; the Holt-Winters logic would have to be re-implemented in Python.
- DRPC (TD3, container clusters), arXiv:2407.10169, IEEE TSC 2024 per arXiv record (OPENED): no code link.
- Meta-RL predictive autoscaling (Alipay), Xue et al., KDD 2022, arXiv:2205.15795 (OPENED): no code link.
- 2026 preprints with LSTM + RL: Shaikh et al. arXiv:2603.28790 (Attention LSTM-PPO, Azure traces, no code
  link), NimbusGuard arXiv:2604.11017 (LSTM + DQN, ICOIN 2026 per arXiv page, no code link on abstract page).
- Asadi et al., "Challenges in Designing Robust RL-Based Autoscalers", PACMI 2025, DOI 10.1145/3766882.3767176
  (OPENED): PPO autoscalers show policy instability under drift and delayed metrics. Supports our delay and
  Poisson experiments and the need to report seeds.
- Zhang et al., RLScale-Bench, arXiv:2605.26418 (v3 June 2026, preprint, no venue): see section 5.
- Surveys: Lorido-Botran 2014 is already in refs.bib. A 2020 RL autoscaling survey exists (Gari et al.,
  arXiv:2001.09957, search result only: unverified details).

## 4. Shortlist

1. **DRe-SCale LSTM-PPO** (A): recommended.
2. **AWARE** (B): the reference for "RL that adapts to new workloads"; discuss it, do not port.
3. **gym-hpa DS-PPO / PPO / RecurrentPPO** (C): fallback if the researcher wants a Redis-specific citation
   or a second agent family.
Lipari et al. (D) is a mandatory citation but not shortlisted as a baseline because the repo is thin.

## 5. Recommendation and the argument for reviewers

**Recommended baseline: DRe-SCale's LSTM-PPO (RecurrentPPO).**

Argument a CCGrid reviewer can accept:
- It is a recent peer-reviewed deep-RL horizontal autoscaler (IEEE TSC 2024) from the Cloud/Grid community
  that CCGrid draws on, and CCGrid itself published RL autoscaling (Schuler 2021).
- It is a **recurrent** policy, so the comparison isolates what we change (off-policy DDQN with a corrected
  target, transfer learning, quantum parts) from "has memory or not".
- Its evaluation already uses Poisson inter-arrival times and an open trace, so our Poisson cycle is not a
  stretch for it.
- Code is public under Apache-2.0, built on Stable-Baselines3, with the full architecture and hyperparameters
  readable in about 100 lines.

What it is **not**: a proven universal state of the art. Say "the most recent open recurrent deep-RL
horizontal autoscaler we could reproduce", and do not call it "the SOTA".

Mandatory companion (not counted as the "one"): a **tuned HPA** with the real stabilisation windows and sync
period. RLScale-Bench (arXiv preprint, 2026) reports that a calibrated HPA has the lowest cost on all six
workloads against PPO, DQN, A2C, SAC, TD3, DDPG, with the caveat that DDPG's cost is lower but violations are
hundreds; a reviewer who knows this will reject any RL-vs-untuned-HPA win. That benchmark gives no tuning
budget for HPA (converter text), so it also does not prove the opposite.

### Risks
1. **Simulator artefact (PLAN F1).** In the current simulator every learner converges to "scale down". The
   comparison is meaningless until Sim v2 makes served load depend on pods. Do this first.
2. **Porting artefacts.** The published code runs live only; we re-implement the environment. The
   result is "DRe-SCale agent architecture and hyperparameters in our simulator", not "DRe-SCale". State it.
   I did not run their code, so reproducing their paper numbers is **unverified**.
3. **Unequal observation.** Their agent sees single-step 6-value observations and carries LSTM state; ours uses
   a 10 x 6 window. Either give both the same window or report both settings.
4. **Action set.** Theirs is {-2..+2}; ours is three actions. Give both the same set in the main table and
   put the published set in an appendix.
5. **Tuning budget.** Their defaults come from SB3 and one live run. If we tune our agent and not theirs
   reviewers will say it is a strawman (Henderson et al., AAAI 2018, DOI 10.1609/aaai.v32i1.11694, META: seeds
   and hyperparameters change DRL rankings).
6. **Reward.** Their reward uses throughput percentage and utilisation. Use **our** reward for all agents
   (served load vs pod cost); keep theirs only as a sensitivity run.
7. **Different RL family.** On-policy PPO vs off-policy DDQN: any difference mixes algorithm and
   architecture. Add our own PPO-LSTM or a DDQN-without-transfer ablation so claims about transfer are not
   confounded.
8. **Sample-efficiency regime.** They trained on live 30 s windows, about 99k steps. Our simulator allows far
   more steps; fix the **same environment-step budget** for every learner.

### What we must report for a fair comparison
- Same simulator build, same seeds list, same train and test workloads: sinusoid + noise + spikes **and** Poisson
  (state arrival rate, spike process, horizon). Same pod startup delay and the same observation delay.
- Equal tuning budget: e.g. N random-search trials per method over learning rate, gamma, batch/rollout size,
  entropy (PPO) or epsilon schedule and target update (DDQN); report the search space, budget and selection
  split (tune on validation workloads, report on held-out ones).
- Equal environment steps and wall-clock for training; also inference time, parameter count and memory
  (requirement R10). Parameter-matched classical control for any quantum claim (project rule 7).
- At least 5-10 seeds with mean and confidence intervals; report failures (non-converged runs) too.
- Elasticity and SLO metrics beyond reward: under- and over-provisioning time, scaling actions per hour
  (oscillation), cost, SLO violation rate, tail latency. Metric definitions: Herbst, Kounev, Reussner,
  "Elasticity in Cloud Computing: What It Is, and What It Is Not", ICAC 2013 (META), and the autoscaler
  evaluation methodology of Ilyushkin et al., ICPE 2017, DOI 10.1145/3030207.3030214 (META).
- Baselines: always-scale-down, no-op, tuned HPA with delay, the recommended agent in "as published" and "tuned"
  arms, our non-transfer DDQN, our transfer DDQN.
- Disclose that DRe-SCale was re-implemented in simulation, the source commit hash, and any changes.

## 6. Items not verified (do not cite until checked)

- AWARE code content, license, last commit (GitLab unreachable); AWARE citation count (not in OpenAlex).
- Any claim that COLA appeared at SoCC 2022. The arXiv page shows no venue.
- Code for Autothrottle, COLA, Chameleon, Rossi et al.: none found; absence of a link is not proof of absence.
- Erlang (EuroSys 2024, Sachidananda and Sivaraman): only seen as a citation in an arXiv paper; not opened.
- Lipari et al.: UCC 2025 vs IPDPSW 2025 venue conflict (IEEE record says IPDPSW 2025); repo license (README MIT, no LICENSE file).
- CORE ranks of NOMS, IPDPSW, TSC: not checked in this report.
- RLScale-Bench numbers come from the converter's reading of the PDF tables; open Tables 2-4 before quoting.

## 7. Suggested next steps (for the coordinator)

1. Researcher decision: accept DRe-SCale LSTM-PPO as the single external baseline (and tuned HPA as the
   required reference).
2. After approval I add the verified entries (agarwal2024drescale, qiu2023aware, santos2023gymhpa,
   lipari2025forecast, schuler2021ccgrid, asadi2025robust, henderson2018drl, herbst2013elasticity) to
   `paper/refs.bib` with notes in `paper/notes/related_work.md`. They are not added yet.
3. Engineer task (needs approval, Sim v2 first): Gymnasium wrapper + RecurrentPPO arm + tuned-HPA arm.
