# Claims -> evidence

| ID | Claim | Evidence (run ids / macro / file:line) | Control | Status |
|---|---|---|---|---|
| I1 | HPA sets replicas from current/target metric ratio, default 15 s loop, tolerance, scale-down stabilization, CPU initialization period | `k8sdocs_hpa`; notes/load_metrics_literature.md 2.4 | n/a (citation) | cited, grade A |
| I2 | A new pod serves only after scheduling, image pull and readiness; image pull is a large part of container start-up | `k8sslos`, `harter2016slacker`; notes 4.6 | n/a | cited |
| I3 | Redis Cluster moves hash slots online; keys locked briefly during MIGRATE | `redisdocs_scaling`, `redisdocs_clusterspec`; notes 4.1 | n/a | cited, grade A |
| I4 | DInos: LSTM over metric window, 3 actions every 15 s, pre-trained in sim, fine-tuned incl. real K8s/Redis; DERP: deep RL for elastic provisioning | `bitsakos2025dinos`, `bitsakos2018derp`; docs/papers/dinos_claims.md C1, C2, C7 | n/a | cited; no DInos numbers repeated |
| I5 | DInos implementation has `\resParamsDInos` parameters, almost all in the LSTM encoder; fine-tuning updates all | PLAN §2 F5 (334,211 total, LSTM 333,824); macro to be filled by script | n/a | code fact; macro [TBD] |
| I6 | VQCs used as RL policies / Q-functions; hybrid transfer with pre-trained classical net + circuit; QLSTM preprint | `jerbi2021parametrized`, `skolik2022quantum`, `mari2020transfer`, `chen2020qlstm`; notes/related_work.md | n/a | cited (abstract level) |
| I7 | Architecture/hyperparameters matter more than parameter count in VQC Q-learning | `skolik2022quantum`; notes/related_work.md | motivates parameter-matched control | cited (abstract level; verify in full text) |
| I8 | Sim v2: queueing latency, start-up delay, rebalance dip; trivial policies must lose to tuned threshold; oracle bound | code/sim_v2/README.md, gates.py; PLAN §8.1 | tuned threshold, oracle | design; gate results pending |
| I9 | Sofia vs DInos/threshold/matched control: SLA violations, params, seeds | `\resSLAViolQuantum`, `\resSLAViolDInos`, `\resParamsQuantum`, `\resParamsDInos`, `\resParamsControl`, `\resNumSeeds` | parameter-matched classical control | [TBD], no runs yet |
| I10 | No quantum speed-up claimed; circuits on classical simulator | PLAN §8.8, AGENTS.md | n/a | design statement |
| R1 | AHPA models pod response time with M/M/1 and M/M/c; M/M/c better with few pods | `zhou2023ahpa` (preprint); notes 1.4 | n/a | cited, grade B |
| R2 | Server tails worse than queueing models; interference sources; queueing/scheduling delay breaks sub-ms QoS; tail > mean | `li2014tales`, `leverich2014reconciling`, `dean2013tail`; notes 1.1-1.3 | n/a | cited (abstract level) |
| R3 | Workload refs: Memcached traces, spike model, MMPP, Azure daily/weekly patterns, Rocksteady low-latency migration | `atikoglu2012workload`, `bodik2010spikes`, `fischer1993mmpp`, `shahrad2020serverless`, `kulkarni2017rocksteady`; notes 4.4, 5.1-5.4 | n/a | cited; fischer metadata only |
| R4 | No published queueing model validated against Redis latency was found | notes/load_metrics_literature.md "Not found" | n/a | search result, not proof of absence |
| R5 | Queueing theory links load/capacity/response time; Little's law | `harcholbalter2013performance`, `little1961proof` | n/a | cited |
| R6 | QuantuML ran ML algorithms incl. k-means on a quantum cloud offering | `bitsakos2025quantuml` (title) | n/a | cited |
