# Load -> metrics literature for Sim v2 (verified 2026-10-17)

Scope: how input load shapes latency, CPU, memory, scale-out cost and traffic in Redis/Memcached and K8s microservices.
Everything below was opened by the scholar via the URL in `refs.bib`. Reading limits: the fetch tool cannot decode PDFs,
so for several papers only the abstract (publisher/S2/author page) was read; this is stated per item ("abstract only").
Evidence grades: **A** = read in a primary source for exactly this claim (docs, abstract, HTML full text);
**B** = real measurement but on other hardware/system, or vendor benchmark; **C** = my inference from the source,
or a source I could only verify at metadata level. No number below is from memory.
Keys refer to `paper/refs.bib`. Sim v2 refers to `code/sim_v2/README.md` and `params.py`.

## 1. Latency vs load, tail growth, queueing models

**1.1 Queueing models are a lower bound; real KV tails are worse.**
Claim: servers (null RPC, Memcached, Nginx) show much worse tail latency than queueing models predict; after removing
interference (background processes, request reordering, interrupt routing, power saving, NUMA) Memcached reaches
median 11 us and p99.9 32 us at 80 % utilisation on four cores, versus 100 us median and 5 ms p99.9 for a naive single-core deployment.
Source: `li2014tales` (abstract via research.google; PDF not readable). Grade A (abstract), B for transfer to Redis.
Sim v2 shaping: the per-pod M/M/1 tail `P(S>x)=exp(-mu(1-rho)x)` is the "ideal" curve. Add a calibratable excess-tail
factor `kappa >= 1` (tail_scale) multiplying the sojourn quantile, and fit it in the calibration pilot. Keep `v(rho)` increasing in rho
(oracle proof needs it).

**1.2 Queueing delay, scheduling delay and thread imbalance cause QoS violations of sub-ms services when utilisation is high.**
Source: `leverich2014reconciling` (abstract only). Grade A/B. Memcached is the workload; abstract names queueing delay explicitly.
Sim v2: supports using utilisation-driven queueing as the load-to-latency link; no number to import.

**1.3 Tail at scale: tail latency matters more than mean.** `dean2013tail` (already in bib, abstract level). Supports p95 SLO, not mean.

**1.4 M/M/1 per pod + additive base latency, M/M/c when pods are few.**
Claim: an industrial K8s autoscaler (AHPA, Alibaba Cloud) models average response time as
`RT(M/M/1) = (u - QPS/N)^-1 + otherlatency` (u = per-pod rate, N = pods) and `RT(M/M/c) = f(QPS,u,N) + otherlatency`
with f "given by Erlang's C formula" and Little's law; it reports M/M/c better with few pods, M/M/1 better with many pods.
Source: `zhou2023ahpa`, section "Performance Model Training" (ar5iv HTML). Grade B (preprint, industrial, the f formula is not written out).
Sim v2: (a) confirms the per-pod M/M/1 shape is a standard choice; (b) adds an additive term `other_latency` (network RTT,
client stack) to every latency; Redis docs give typical network latency 200 us on 1 Gbit/s TCP and 30 us on a Unix socket
(`redisdocs_latency`, grade A for the doc statement); (c) with few pods (1-5) a shared-queue M/M/c is the alternative to
per-pod queues. Which one fits depends on whether the real load balancer is per-connection (Redis clients keep long-lived connections,
so per-pod queues are the natural reading) - this is a calibration question, not settled by the literature.

**1.5 Single thread: one slow command blocks every other request.**
Claim: Redis serves all requests sequentially from one thread; O(N) commands (SORT, LREM, SUNION, KEYS) delay all clients;
high CPU with low traffic indicates slow commands. Source: `redisdocs_latency` (documentation, grade A).
Sim v2: service time is not exponential, so a pod is an M/G/1 with squared coefficient of variation `cs2` set by the command mix.
Add parameter `service_cv2` (default 1 = current M/M/1). The Pollaczek-Khinchine mean-wait formula is textbook
(`harcholbalter2013performance`, already in bib); I did not open the chapter, so the exact formula is NOT verified here.
Whitt (1.6) says that under overload the service-time shape beyond its mean matters little, so `service_cv2` matters mainly below saturation.

**1.6 Fluid models: justified under heavy load, and abandonment (timeout) matters more than service-time shape.**
Claim: deterministic fluid models give first-order performance of multiserver queues with abandonment under heavy load; steady-state
depends strongly on the abandonment-time distribution beyond its mean but not on the service-time distribution beyond its mean;
a discrete-time fluid model handles time-dependent arrivals.
Source: `whitt2006fluid` (abstract, IDEAS page). Grade A for the claims, with caveat: the theory is for many servers (large s);
Sim v2 has 1-30 single-server pods, so the asymptotics are weak and it is only a motivation.
Sim v2: the `timeout_s` (patience) and the failure treatment deserve calibration priority over service-time distribution.
The fluid-queue design is defensible; do not cite Whitt as proof of accuracy at 1-30 pods.

**1.7 Utilisation limit practice.** ElastiCache guidance keeps CPU under 80 % on multicore and under 50 % on single-core instances
during resharding (`awselasticache_resharding`, vendor doc, grade A for the statement). Sim v2: gives plausible target band for
threshold-policy tuning and for the CPU level at which latency starts to rise on a single-core pod; not a latency law.

## 2. CPU vs request rate; per-instance throughput

**2.1 Throughput per instance is hardware- and client-dependent; documented examples.**
`redisdocs_benchmark` (grade A as documentation, B as evidence): doc examples show 72,144 req/s (SET, 1M requests, 50 clients, random keys),
180,180 SET and 188,323 LPUSH req/s, and with pipelining P=16 on a MacBook Air 1.5M SET and 1.8M GET req/s; benchmark default is no pipelining.
"In many real world scenarios, Redis throughput is limited by the network well before being limited by the CPU."
"An instance with 30000 connections can only process half the throughput achievable with 100 connections" (rule of thumb); Redis ran at 60,000 connections sustaining 50,000 q/s.
Sim v2: `mu_ops_per_pod = 1000` is 2 orders of magnitude below these unconstrained figures; it encodes the 200m CPU limit of the real pod, so it
must be measured, not taken from docs. The connection-count penalty is negligible for tens to hundreds of connections; do not model it
unless the load generator uses thousands of connections.

**2.2 CPU is the load-coupled resource; Alibaba microservices are more sensitive to CPU than memory interference.**
`luo2021alibaba` (abstract via S2; grade A for the sentence). Sim v2: supports `cpu_pct` as the observation that carries load information and memory as
decoupled; consistent with the decision to remove memory from the observation.

**2.3 Background CPU does not follow request rate.** Fork for RDB/AOF rewrite costs about 9-13 ms per GB of RSS on bare metal/VMware, up to 239-424 ms per GB on old Xen
VMs; fork stalls the main thread (`redisdocs_latency`, grade A). Sim v2: if the real Redis uses persistence, add a periodic stall of
`fork_ms_per_gb * dataset_gb` as a capacity dip independent of lambda. Today `cpu_pct = 100*served/C` ignores this; add `cpu_baseline_pct` and an optional background term.

**2.4 K8s HPA semantics (the baseline the researcher's threshold policy should mimic).**
`k8sdocs_hpa` (grade A): control loop default 15 s (`--horizontal-pod-autoscaler-sync-period`); `desired = ceil(current * currentMetric/desiredMetric)`;
tolerance 0.1; downscale stabilization window 300 s (picks the highest recommendation within the window); initial-readiness delay default 30 s;
CPU initialization period default 5 min (CPU of starting pods ignored unless ready and sampled while ready); not-yet-ready pods assumed to consume 0 % of the desired
metric on scale-up; missing metrics assumed 100 % on scale-down. CPU utilisation is relative to the container *request*, so values above 100 % occur.
Sim v2: `control_step_s = 15` matches the default sync period. Threshold policy: add `tolerance=0.1`, `cooldown_down = 300/15 = 20` steps, ratio-based step
(proportional scale, not +-1), and treat pending pods as 0 % load on scale-up. `cpu_pct` should be allowed to exceed 100 only if defined against a request below the limit.

## 3. Memory vs dataset size, connections, request rate

**3.1 Memory follows the dataset, not the request rate.** Redis allocates up to `maxmemory`; RSS does not return to the OS when keys are deleted, so
memory must be provisioned for the peak (5 GB filled, 2 GB deleted: RSS stays about 5 GB); small hashes/lists/sets/zsets use up to 10x less memory (average 5x) with special encodings.
Source: `redisdocs_memory` (grade A). Sim v2: memory is a function of dataset size and history, not lambda. Model `mem = f(keys*avg_size) + connections*buf`, monotone non-decreasing
except for restarts. This agrees with the README note that memory could only encode the backlog.

**3.2 Connections cost memory through buffers; request rate only indirectly.** `maxclients` default 10,000; normal-client output buffers have no limit by default,
pub/sub 32 MB hard, replicas 256 MB hard; query buffer hard limit 1 GB; `maxmemory-clients` (Redis 7.0+) caps aggregate client memory, default 0 (off).
Source: `redisdocs_clients` (grade A). I found no per-connection byte figure in the docs. Sim v2: client memory grows with slow consumers, not with offered rate; if a
backlog/slow client model is wanted, tie output-buffer memory to the unserved backlog, which is what the removed observation did.

**3.3 Write rate matters for memory only during fork (copy-on-write).** With transparent huge pages, "a few event loops runs will cause commands to target a few thousand of pages,
causing the copy on write of almost the whole process memory", causing big latency and memory use (`redisdocs_latency`, grade A).
Facebook Memcached GET:SET is 30:1 (`atikoglu2012workload`, abstract, grade A), i.e. about 3 % writes in that workload, so COW pressure from writes is workload-dependent.
Sim v2: add `write_fraction` (default from DInos's real mix once measured; 0.03 is the Facebook figure, not ours) only if persistence/fork is modelled.

**3.4 Scale-in feasibility depends on memory.** ElastiCache: before scaling in, free memory on retained shards must be at least 1.5x the memory of the shards removed
(`awselasticache_resharding`, vendor doc, grade A). Sim v2: add a lower bound `min_pods(dataset) = ceil(dataset / mem_per_pod / 1.5-style headroom)` or make a scale-down below it fail with a penalty;
at present `min_pods = 1` regardless of data size.

## 4. Scale-out effects

**4.1 Resharding is online with no downtime, with a short lock per MIGRATE.**
`redisdocs_scaling`: "Moving hash slots ... requires no downtime". `redisdocs_clusterspec`: MIGRATE moves keys atomically, both instances locked for the (usually very small) time
needed; with big keys, reconfiguration "is not considered a wise procedure if there are latency constraints". Grade A.
Sim v2: a full outage is wrong; capacity dip delta is a fractional loss, as modelled. The duration k is the main error (4.2).

**4.2 Legacy key-by-key migration is slow; duration scales with data volume, not with one control step.**
Vendor benchmark (Redis 8.4, 3 GCP shards of 8 vCPU/32 GB, 10M keys x 512 B (about 5 GB), 500 connections, memtier): legacy migration took 192-219 s (21 slots/s), with up to 241.6 -MOVED/s,
latency spikes up to 127 ms; atomic slot migration (ASM, Redis 8.4) took 6.4 s (3->4 shards) and 8.6 s (4->3), average latency rose under 5 % for 2 s, throughput stayed at baseline.
Source: `redisblog2026asm` (vendor, grade B; independent replication absent). Sim v2: with T = 15 s, legacy migration of 5 GB is about 13-15 control steps, ASM under 1 step.
`rebalance_steps = 1` and `rebalance_loss = 0.3` match neither regime: expose `rebalance_steps = ceil(moved_bytes / (migration_rate * T))` with `moved_bytes` about dataset/(r+1) for a balanced scale-out
(my arithmetic, not sourced), and make `delta` smaller for ASM-like (about 0.05 effect on latency per the vendor figure, capacity effect not reported) than for legacy (unmeasured). Both are calibration targets;
this is the strongest literature-based argument that the single-step 30 % dip is unrealistic in either direction.

**4.3 Resharding costs CPU, so the dip depends on load.** "Resharding is a compute-intensive operation ... keep CPU utilization under 80 % (multicore) / 50 % (single core) during resharding";
start off-peak to reduce latency and throughput impact and to complete faster (`awselasticache_resharding`, vendor, grade A as statement, no numbers on loss).
Sim v2: make delta state-dependent: migration steals a fixed CPU amount `m` ops/s from the pods involved, so effective capacity is `C - m` (not `C(1-delta)`), and the
migration lasts longer when spare capacity is small. Grade C as a modelling inference.

**4.4 Low-impact live migration is feasible in research systems.** Rocksteady (RAMCloud, not Redis): 758 MB/s under high load, median latency under 40 us and p99.9 under 250 us during migration
vs about 6 us / 45 us normally (`kulkarni2017rocksteady`, abstract, grade A for the numbers, B for relevance). Use as an upper bound on how cheap migration can be; do not use as Redis parameters.

**4.5 New replica / shard needs a data load before it serves.** Replication: master starts a background save (fork) and buffers writes, transfers the RDB, the replica loads it; the master stays non-blocking, but the replica blocks
connections while loading ("as long as many seconds for very large datasets"); a diskless option avoids the disk (`redisdocs_replication`, grade A).
Sim v2: for a stateful Redis pod the startup delay `d` is scheduling + image pull + data load; a pending pod is not ready until loaded. `d = d_sched + d_pull + dataset_per_pod/load_rate` instead of a constant 2 steps.

**4.6 Pod startup.** K8s SLO for stateless pod startup is p99 <= 5 s per cluster-day *excluding image pull and init containers*; the stateful-pod SLI is WIP and depends on the storage provider (`k8sslos`, grade A).
Container pull is 76 % of start time and only 6.4 % of the pulled data is read (57 applications, HelloBench; 2016 Docker) (`harter2016slacker`, abstract, grade A/B, dated).
Sim v2: `startup_delay_steps = 2` (30 s) is plausible when the image is cached and well above the 5 s SLO; it is far too small for cold pulls of large images or for data loading. Make `d` random
and conditional on image cache (two modes: warm 1 step, cold 3+ steps) and calibrate on the real cluster. The HPA's own 30 s initial-readiness delay and 5 min CPU initialization period (2.4) mean the baseline policy ignores a new pod's CPU for up to 20 steps.

## 5. Workload models of real traffic

**5.1 Diurnal and weekly pattern with a constant baseline; arrivals are not Poisson.**
Azure Functions (July 2019, 14 days): "clear diurnal and weekly patterns" with a constant baseline of roughly 50 % of invocations (section 3.3, as extracted by the fetch tool from ar5iv; verify the exact wording in the PDF before quoting);
45 % of applications are invoked once per hour or less on average; 40 % of apps have IAT CV above 1 (section 3.6); only a small fraction have CV near 1; HTTP is 64 %-of-apps trigger.
Source: `shahrad2020serverless`; dataset `azurepublicdataset` (per-minute invocation counts per function, July 2019). Grade A (HTML full text), B for transfer to Redis load.
Sim v2: W1's daily profile should carry a non-diurnal floor (about half the peak-hour rate is a reasonable first sensitivity, tagged as inferred from this trace, not from Redis traffic),
and inter-arrival burstiness should be calibrated to CV > 1 at minute scale. Per-minute counts must be up-sampled to 15 s steps, which adds assumed sub-minute noise: state that when W2 uses it.

**5.2 Facebook Memcached traces.** 284 billion requests from five Memcached use cases over several days; analysis of request composition, size, rate, temporal patterns; a simple workload model is proposed;
GET:SET 30:1. `atikoglu2012workload` (abstract, grade A). The abstract does not state the diurnal amplitude or inter-arrival distribution; I could not read the full text, so those details are UNVERIFIED here.
Sim v2: use as the KV reference for workload mix; do not take diurnal amplitude from it until the PDF is read.

**5.3 Flash crowds and workload spikes.** Five real spikes vary in steepness, magnitude, duration and spatial locality (data hotspots); a model synthesizes volume and data spikes (`bodik2010spikes`, abstract, grade A).
Sim v2: W3's regime shift and W1's burst factor (x1.6) should be drawn from ranges for steepness and magnitude, with a duration distribution, rather than one fixed value.
Data hotspots mean one shard/pod can saturate while others idle, which is a mechanistic reason for `theta < 1` (capacity grows sublinearly with pods) - grade C, my inference, not stated by the abstract.

**5.4 Burstiness and MMPP.** The MMPP cookbook is the standard reference for fitting and analysing Markov-modulated Poisson processes (`fischer1993mmpp`, metadata verified only);
Mi et al. show burstiness degrades multi-tier performance and is hard for capacity-planning models (`mi2008burstiness`, metadata verified only; abstract content only from a search-engine summary - treat as C).
Sim v2: W1's 2-state MMPP is a recognised choice; fit rates and switching probabilities from a trace's index of dispersion instead of the fixed x1.6, and report it as a sensitivity.

**5.5 Public traces.**
- Wikipedia pageviews: official hourly files since May 2015 (`wikimedia_pageviews`; hourly naming `pageviews-YYYYMMDD-HH0000.gz` verified in the 2024-01 directory). Pageview = server response 200/304 rendering content under /wiki/ (readme). A web-page trace, not KV traffic; hourly resolution cannot validate 15 s burstiness.
  Older trace analysis: `urdaneta2009wikipedia` (metadata only; a listing describes a 108-day trace; not verified).
- Azure Functions 2019 (per-minute counts) and 2021 invocation trace (arrival/completion times, 2 weeks from 2021-01-31) (`azurepublicdataset`). Licensing: repository sidebar shows CC-BY-4.0 and MIT; which applies to the dataset is not stated on the page; cite `shahrad2020serverless`.
- Alibaba microservices v2021: 20,000+ microservices over 12 hours; call dependencies, response time, call rate; research/study use only; maintainers ask to be informed of publications (`alibabaclusterdata`, README; `luo2021alibaba`).
  12 hours cannot supply a diurnal cycle. A search-engine snippet mentions structural inconsistencies reported at ICPE 2024 (Huye et al.); I did not open that paper: UNVERIFIED, not in refs.bib.
Sim v2: W2 stub should record the resolution of each source and refuse to claim sub-resolution burstiness; Wikipedia hourly and Azure per-minute are suitable for the slow component only.

## Not found (gaps, do not cite around them)
- No peer-reviewed M/M/c or M/G/1 model validated against Redis latency (extended search found none; closest are `li2014tales` for Memcached and AHPA for pods). Redis-specific queueing parameters must come from our calibration pilot.
- No peer-reviewed measurement of Redis Cluster resharding impact; only vendor/ docs figures (`redisblog2026asm`, `awselasticache_resharding`).
- No per-connection memory byte figure in Redis docs; no peer-reviewed K8s pod-startup measurement study located (only the SLO and the 2016 image-pull paper).
- Unopened/UNVERIFIED (not in refs.bib): Huye et al. ICPE 2024 on Alibaba trace inconsistencies; the "Autoscaling Based on Response Time Prediction for Microservice Application in Kubernetes" (2022) paper seen only in a review table.

## Concrete recommendations for env.py / params.py (all stay provisional until calibration)
1. Latency: keep per-pod M/M/1 as the ideal; add `other_latency_s` (additive, default 0.0002 s from the 1 Gbit/s figure in the Redis docs, flagged provisional), `tail_scale kappa >= 1` and `service_cv2` (default 1). SLO derivation then must include the additive term (the current SLO ignores network).
2. Make `rebalance_steps` derived from data volume and migration rate, and `rebalance_loss` a CPU-steal `m` (ops/s) rather than a flat 30 %; run both a legacy-like (about 13-15 steps at 5 GB) and an ASM-like (under 1 step) setting as sensitivities.
3. Make `startup_delay` stochastic and state-dependent (image cached or not, data load for stateful pods); keep 2 steps as the warm median only.
4. Threshold baseline mimics the K8s HPA: ratio-proportional step, tolerance 0.1, scale-down stabilization 20 steps, new pods ignored for the initial-readiness delay (2 steps) and pending pods counted as 0 % on scale-up.
5. Memory: do not couple to lambda; model it from dataset size + client buffers; add a scale-in feasibility bound (retained shards need at least 1.5x the removed memory).
6. CPU: add `cpu_baseline_pct` and optional fork stall independent of lambda; observation noise stays.
7. Workloads: add a non-diurnal floor to W1, draw burst magnitude/duration from ranges (flash-crowd literature), fit the MMPP from dispersion; W2 must declare source resolution (hourly Wikipedia, per-minute Azure) and only drive the slow component.
8. Calibration targets to add to the pilot plan: legacy vs ASM migration duration at the real dataset size; pod ready time with warm and cold image; latency-vs-rho curve to fit kappa; slow-command share (service_cv2).
