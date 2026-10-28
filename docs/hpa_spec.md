---
description: Kubernetes HPA (autoscaling/v2, v1.34.0) algorithm read from source and docs - spec for the fair HPA baseline
---
# HPA baseline specification (autoscaling/v2), CPU utilization

Read 2026-10-17. Code: `kubernetes/kubernetes` tag **v1.34.0**, `pkg/controller/podautoscaler/` (`horizontal.go`, `replica_calculator.go`, `metrics/utilization.go`) and `pkg/apis/autoscaling/v2/defaults.go`. Docs: current kubernetes.io pages (version menu lists v1.33-v1.37; the page cites "stable since v1.37" for tolerance), HPA concept page and kube-controller-manager flag reference. Tags newer than v1.34.0 were not read. Tags: [D] docs, [F] flags page, [C] code. Caveat: the code was read through a summarizing fetch tool, so quoted fragments are exact but connecting prose is paraphrase (items marked *(paraphrase)* should be re-read in the raw file before the paper cites them).

URLs: [D] https://kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale/ ; [F] https://kubernetes.io/docs/reference/command-line-tools-reference/kube-controller-manager/ ; [C] https://github.com/kubernetes/kubernetes/tree/v1.34.0/pkg/controller/podautoscaler

## 1. Loop, metric, formula, tolerance
- Sync period `--horizontal-pod-autoscaler-sync-period`, default 15s [F][D].
- Metric: per-pod usage as a percentage of the pod's resource **request** (sum of container requests; a missing request is an error) [D][C `calculateRequests`]. Utilization = `int32(metricsTotal*100 / requestsTotal)` (integer truncation) over pods with metrics; ratio = `currentUtilization / targetUtilization` [C `metrics.GetResourceUtilizationRatio`].
- `desiredReplicas = ceil[currentReplicas * currentMetric/desiredMetric]` [D]. In code the plain path returns `ceil(usageRatio * readyPodCount)`, i.e. the multiplier is the number of pods that contributed metrics, not spec replicas [C `GetResourceReplicas`] *(paraphrase)*.
- Tolerance: no scaling if `(1-tolDown) <= ratio <= (1+tolUp)` [C `Tolerances.isWithin`]. Default 0.1 both ways, set by `--horizontal-pod-autoscaler-tolerance` (default 0.1) [F][D]. Per-HPA `behavior.scaleUp.tolerance` / `behavior.scaleDown.tolerance`: first available v1.33 (gate `HPAConfigurableTolerance`), docs say stable v1.37 [D]; present in v1.34.0 code, gated [C `tolerancesForHpa`]. Baseline uses 0.1 both ways.

## 2. Pod handling [C `groupPods`, `GetResourceReplicas`; D "Algorithm details"]
- Ignored: pods with DeletionTimestamp or phase Failed. Pending pods: unready. Pod without metric entry: missing.
- CPU only, pod unready if Ready condition absent or `StartTime` nil; else if `StartTime + cpuInitializationPeriod` is still in the future: unready if `Ready==False` OR `metric.Timestamp < LastTransitionTime + metric.Window`; else (past init period): unready only if `Ready==False` AND `StartTime + initialReadinessDelay` is after `LastTransitionTime` (never-ready pod) [C, exact code].
- Defaults: `--horizontal-pod-autoscaler-cpu-initialization-period` 5m, `--horizontal-pod-autoscaler-initial-readiness-delay` 30s [F][D]. Value of `metric.Window`: not found in the files read.
- Unready/ignored pods' metrics are removed; if none remain: error, no scaling.
- `scaleUpWithUnready = len(unready)>0 && ratio>1.0`. If that is false and no missing pods: tolerance check, then `ceil(ratio*readyPodCount)` *(paraphrase)*.
- Otherwise rebalance: missing pods get 100% of request (`max(100, target)`) when ratio<1 (scale-down), 0% when ratio>1; if `scaleUpWithUnready`, unready pods get 0 [C; D states the same 100%/0%/0% rule]. Recompute `newRatio` over all entries; return `currentReplicas` if `isWithin(newRatio)` or direction flipped (`ratio<1 && newRatio>1`, or the reverse) [C exact]. Else `newReplicas = ceil(newRatio * len(metrics))` [C exact], and a wrong-direction guard against `currentReplicas` *(paraphrase)*.

## 3. Behavior defaults [D "Default behavior"; C `defaults.go`]
- scaleUp: `stabilizationWindowSeconds 0`; policies Percent 100 / 15s and Pods 4 / 15s; `selectPolicy Max`.
- scaleDown: window 300s (= `--horizontal-pod-autoscaler-downscale-stabilization`, default 5m [F]); one policy Percent 100 / 15s; `selectPolicy Max`.
- `minReplicas` default 1 [C]. Docs: scale-to-zero only for object/external metrics, not CPU [D].
- If `spec.behavior == nil` (an HPA without a behavior block), the legacy path runs: scale-up cap `max(2*currentReplicas, 4)` (`scaleUpLimitFactor=2.0`, `scaleUpLimitMinimum=4`), no scale-down rate cap, scale-down stabilization = max of recommendations in the downscale window [C `calculateScaleUpLimit`, `stabilizeRecommendation`]. Docs say the defaults "match the existing behavior" [D]; they differ slightly (see section 6).
- Rate limits [C `calculateScaleUpLimitWithScalingRules`]: per policy, `periodStart = current - addedInPeriod + deletedInPeriod` (from stored scale events within `periodSeconds`); Pods: `periodStart + value`; Percent: `ceil(periodStart*(1+value/100))`; select Max picks the largest (Min the smallest, Disabled returns current). Scale-down mirrors it with Percent `int32(periodStart*(1-value/100))` (truncation) and subtracts.
- Stabilization [C `stabilizeRecommendationWithBehaviors`]: `upRec = downRec = desired`; every stored raw recommendation newer than `now - upWindow` lowers `upRec` (min); every one newer than `now - downWindow` raises `downRec` (max); `result = current`; if `result < upRec` then `upRec`; if `result > downRec` then `downRec`. The raw (unstabilized) desired value is stored afterwards, so the current step's value is not in the scanned history but is the initial bound. `recordInitialRecommendation` seeds history with current replicas on first sight.

## 4. Replica count and order [C `reconcileAutoscaler`]
`currentReplicas = scale.Spec.Replicas` (spec, not ready) is passed to the calculator, but the ratio is applied to the count of pods with usable metrics (section 2). Order:
1. `recordInitialRecommendation`; `minReplicas` (nil -> 1).
2. If `current==0 && min!=0`: scaling disabled. Else if `current>max`: desired=max. Else if `current<min`: desired=min. Else compute metrics (multiple metrics: largest proposal wins).
3. Normalize: `normalizeDesiredReplicasWithBehaviors` = stabilize, then `convertDesiredReplicasWithBehaviorRate` (rate limit; scale-up bounded by `maxReplicas`, scale-down by `minReplicas`).
4. If `desired != current`: update scale subresource and `storeScaleEvent`.

## 5. Pseudocode (one sync)
```
cur = spec_replicas
if cur > max: d = max
elif cur < min: d = min
else:
  P = pods not deleting/failed
  U = {p in P unready per section 2 rule};  M = P \ U   # no missing metrics in sim
  if M empty: return                                    # error, no scale
  usage = sum(cpu_i), req = sum(request_i) over M
  util = floor(100*usage/req); r = util/target
  if U nonempty and r>1:                                # scaleUpWithUnready
      n = |M|+|U|; r2 = floor(100*usage/((|M|+|U|)*req_pod))/target
      if within(r2) or r2<1: d = cur else d = ceil(r2*n)
  elif within(r): d = cur
  else: d = ceil(r*|M|)
  # wrong-direction guard: d>cur only if r>1, d<cur only if r<1 (paraphrase)
  # stabilize (behavior path)
  up = min(d, recs newer than now-upWin); dn = max(d, recs newer than now-dnWin)
  rec_store.append((now, d))        # raw d
  s = cur; if s < up: s = up; if s > dn: s = dn          # code order
  # rate limit (selectPolicy Max)
  if s > cur: lim = max(limit_i); s = min(s, max(lim,cur), maxReplicas)
  if s < cur: lim = min(limit_i); s = max(s, min(lim,cur), minReplicas)
  apply s; record scale event (t, s-cur)
```

## 6. Mapping to our simulator and differences
| Item | Real HPA | Simulator | Needed assumption |
|---|---|---|---|
| Step | 15s sync | 15s step | 1 step = 1 sync; windows in steps: 300s = 20 steps |
| Action size | multi-pod (up to 100%/4 pods per 15s) | ±max_delta | HPA baseline alone may exceed `max_delta`; report this, it favors HPA vs RL |
| Metric | usage / request, can exceed 100% only if limit > request | served/capacity (unclipped noisy reading) | Implemented as a busy-fraction proxy: served / effective capacity, saturating at 100 % before noise/offset. Request = limit is an ASSUMPTION; the proxy cannot distinguish moderate from extreme overload (at target 40 % a saturated reading requests about 2.5x the ready replicas, whatever the real backlog). Requests do NOT shrink during rebalancing or with theta < 1: the proxy's denominator is the reduced effective capacity, so it reads higher than usage over a fixed request would. A real request < limit needs a calibrated CPU usage/request model (future work). Arrivals/demand is offered load, not a CPU metric, and is not used |
| Readiness | Ready condition, init period 5m, window skip | ready after d steps | Pods in warm-up are U (unready, 0 on scale-up); skip first post-ready sample for `ceil(window/15s)` steps (`Window` not found) |
| Metric lag | metrics-server scrape window | none stated | Parameter (delay k steps); default value not found |
| Count in ratio | pods with metrics | ready pods | Use ready, non-terminating pods |
| Missing metrics | 100%/0% fallback | none | Not modeled (document) |
| Period history | wall-clock events | step index | `periodStart = cur` since the policy period equals one step; boundary behavior at exactly 15s not verified |
| Tolerance | 0.1 | n/a | 0.1 both ways |
| Integer rounding | int truncation of util, ceil elsewhere | n/a | replicate |
| Behavior block | nil => legacy cap `max(2c,4)` | n/a | Choose explicitly; spec uses documented defaults (100%/4 pods) |
| Pod startup/removal | graceful termination | instant | Terminating pods ignored |

## Open uncertainties
Tags above v1.34.0 unread; `metric.Window` value and metrics-server defaults not found; wrong-direction guard and pre-metrics paths paraphrased; period-boundary treatment of scale events at 15s not verified.
