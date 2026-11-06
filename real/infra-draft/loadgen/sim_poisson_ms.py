"""Cycle 2: Poisson microservice workload + queue env (docs/cycle2_plan.md §2, docs/expert/poisson_workloads.md).

Workload (per tick t, length 1):
  lambda_t = base * diurnal(t) * burst(t) * exp(x_t)
    diurnal(t) = 1 + amp * sin(2 pi t / period + phase)          phase ~ U(0, 2 pi) per episode
    burst(t)   = burst_factor in the "burst" state, else 1: a 2-state Markov chain switched at tick boundaries
                 (P(normal->burst) = 1 - exp(-r_nb), P(burst->normal) = 1 - exp(-r_bn)), so sojourns are geometric
                 (mean 1 / (1 - exp(-r)) ticks), the discrete-time analogue of MMPP-2
    x_t        = AR(1) log-noise, x_t = phi x_{t-1} + sqrt(1 - phi^2) sigma eps_t (stationary sd sigma)
  N_t ~ Poisson(lambda_t). Noise is on the rate, never on the counts. Within a tick the rate is constant, so given N_t
  the arrival times are N_t sorted U(0,1) draws: conditional on the rate path, a piecewise-constant NHPP; overall a
  discrete-time Markov-modulated Cox process (exponential inter-arrivals globally only for constant rate).
  The whole workload is drawn from its own Generator stream: arrivals never depend on the actions.

Service (request level, FIFO, work-conserving): capacity cap = mu * active pods requests per tick. W = outstanding
requests (fluid work). Between arrivals W drains at rate cap. An arrival is dropped if W + 1 > q_max (strict bound),
else admitted with virtual sojourn (W + 1) / cap + l0, and W += 1. The sojourn is a latency PROXY fixed at admission
at the current capacity (never revised when pods change later), not an observed response time. Conservation per tick:
W_end = W_start + admitted - served (tests). mean / p95 latency = over the tick's admitted requests (l0 + W/cap if
the tick has no arrival). cpu % = 100 * served / cap + N(0, cpu_sd); mem % = 100 * min(1, m_base + m_k * W / pods)
+ N(0, mem_sd); measurement noise uses a second stream (it never changes the trace).

Pods, actions, delay and bounds are those of the cycle-1 env orig:<v>_d<D> (tuning/legacy/orig_variants.py): actions
0 down / 1 stay / 2 up; pods 1..20 on active + pending; a pod requested at step n serves from step n + D on; action 0
cancels the newest pending pod first. Start: 6 active pods, done after ep_ticks steps.

State (7, same slots as orig:spike300_d5 so the transfer arms keep their input size):
  [arrivals, capacity, cpu %, mem %, p95 latency, active pods, pending pods]
SLO miss in a tick = p95 > l_slo OR any drop (docs/expert/poisson_workloads.md:26).
Reward = served - pod_cost * (active + pending) - w_slo * [SLO miss] - w_drop * drops. At the last tick the
unfinished backlog W counts as dropped (w_drop * W in drop_cost, info backlog_end), so no work vanishes at reset.
Partial observability: noisy memory and admission p95 do not identify the backlog exactly; every arm gets the same
features and history window.
info: served, vm_cost, slo_cost, drop_cost (sum == reward), arrivals, drops, queue, p95, mean_lat, lam.
"""
import copy
import dataclasses
import math

import numpy as np

STREAM_LOAD, STREAM_MEAS = 21, 22
COMP = ("served", "vm_cost", "slo_cost", "drop_cost")
FEATURES = ("arrivals", "capacity", "cpu", "mem", "latency_p95", "pods", "pending")
OBS_SCALE = np.array([100.0, 100.0, 100.0, 100.0, 2.0, 20.0, 20.0])
MAX_PODS = 20


SPIKY_BASE = 48.94  # calibrated: mean lambda = poisson_ms (71.6 req/tick), .lab/j291/calib_v1.json


@dataclasses.dataclass(frozen=True)
class Params:
    base: float = 60.0            # mean rate (req/tick) before modulation
    amp: float = 0.4              # diurnal amplitude
    period: float = 1000.0        # ticks
    burst_factor: float = 2.5
    r_nb: float = 1 / 600         # normal -> burst rate (per tick); mean normal sojourn 600
    r_bn: float = 1 / 80          # burst -> normal; mean burst 80
    phi: float = 0.98             # AR(1) log-noise
    sigma: float = 0.15
    mu: float = 10.0              # requests per pod per tick
    q_max: float = 200.0          # queue bound (requests)
    l0: float = 0.1               # base processing latency (ticks)
    cpu_sd: float = 2.0
    mem_sd: float = 1.0
    m_base: float = 0.35
    m_k: float = 0.02
    delay: int = 5
    pod_cost: float = 3.0
    l_slo: float = 1.0
    w_slo: float = 20.0
    w_drop: float = 1.0
    ep_ticks: int = 5000
    start_pods: int = 6
    # --- poisson_ms_spiky event overlay (J291; off by default: every field below is inert when events=False) ---
    events: bool = False
    rate_cap: float = 0.0         # >0: lambda_t is clipped to this value (keeps spikes inside max capacity MAX_PODS*mu)
    ab_rate: float = 1 / 450      # abrupt flash-crowd onsets per tick (Poisson process)
    ab_lo: float = 1.8            # extra multiplier amplitude ~ LogUniform(ab_lo, ab_hi) on the background
    ab_hi: float = 3.5
    ab_hold_med: float = 40.0     # plateau length ~ LogNormal(median ab_hold_med, sd 0.5), then exp decay tau ab_tau
    ab_tau: float = 15.0
    rp_rate: float = 1 / 600      # gradual ramps per tick: linear up (rp_up ticks), plateau, linear down
    rp_amp_lo: float = 0.8        # extra amplitude ~ U(rp_amp_lo, rp_amp_hi)
    rp_amp_hi: float = 1.8
    rp_up: tuple = (15, 60)       # ramp length ~ U{rp_up}
    rp_hold: tuple = (20, 80)
    tr_rate: float = 1 / 900      # burst trains (recurring spikes): n pulses of width tr_w every tr_period (+- jitter)
    tr_n: tuple = (3, 6)
    tr_period: float = 45.0
    tr_jitter: float = 4.0
    tr_w: int = 12
    tr_amp_lo: float = 1.0
    tr_amp_hi: float = 2.0
    tr_skip: float = 0.1          # each pulse is dropped with this probability


VARIANTS = {
    "poisson_ms": Params(),
    # held-out shift (plan §2 H-shift): more frequent bursts and more noise; never used in tuning
    "poisson_ms_shift": Params(r_nb=1 / 300, sigma=0.30),
    # test-only helper: homogeneous Poisson (no diurnal, burst or noise)
    "poisson_hom": Params(amp=0.0, burst_factor=1.0, sigma=0.0),
    # test-only helper: burst chain alone (no diurnal, no noise)
    "poisson_burst": Params(amp=0.0, sigma=0.0),
    # J291: spiky workload (docs/spiky_workload.md). The 2-state burst chain is replaced by an explicit event overlay;
    # base is calibrated so that the mean offered load equals poisson_ms (tests/test_spiky.py, SPIKY_BASE).
    "poisson_ms_spiky": Params(events=True, burst_factor=1.0, base=SPIKY_BASE, rate_cap=190.0),
}


def _seed(seed, stream):
    return np.random.default_rng(list(seed) + [stream] if isinstance(seed, (list, tuple)) else [int(seed), stream])


class Workload:
    """Rate path and arrival times; one Generator; advances one tick per call."""

    def __init__(self, p, rng):
        self.p, self.rng = p, rng
        self.reset()

    def reset(self):
        self.t = 0
        self.phase = self.rng.uniform(0, 2 * math.pi) if self.p.amp else 0.0
        self.burst = False
        self.x = self.rng.normal(0, self.p.sigma) if self.p.sigma else 0.0
        self.ev = self._draw_events() if self.p.events else None

    def _draw_events(self):
        """Event multiplier path m_t = 1 + sum of event shapes over one episode (drawn once at reset, from the
        workload Generator, so it never depends on actions). Abrupt: instant onset, plateau, exp decay. Ramp: linear
        up, plateau, linear down. Train: n equal pulses every tr_period (+- jitter), each skipped w.p. tr_skip."""
        p, rng, n = self.p, self.rng, self.p.ep_ticks
        m = np.ones(n)
        for _ in range(rng.poisson(p.ab_rate * n)):
            t0 = int(rng.integers(0, n))
            a = math.exp(rng.uniform(math.log(p.ab_lo), math.log(p.ab_hi))) - 1.0
            hold = int(round(math.exp(rng.normal(math.log(p.ab_hold_med), 0.5))))
            tt = np.arange(n - t0)
            m[t0:] += a * np.where(tt < hold, 1.0, np.exp(-(tt - hold) / p.ab_tau))
        for _ in range(rng.poisson(p.rp_rate * n)):
            t0, a = int(rng.integers(0, n)), rng.uniform(p.rp_amp_lo, p.rp_amp_hi)
            up, hold = int(rng.integers(p.rp_up[0], p.rp_up[1] + 1)), int(rng.integers(p.rp_hold[0], p.rp_hold[1] + 1))
            tt = np.arange(n - t0)
            m[t0:] += a * np.clip(np.minimum(tt / up, (2 * up + hold - tt) / up), 0.0, 1.0)
        for _ in range(rng.poisson(p.tr_rate * n)):
            t0, k = int(rng.integers(0, n)), int(rng.integers(p.tr_n[0], p.tr_n[1] + 1))
            for i in range(k):
                a, skip = rng.uniform(p.tr_amp_lo, p.tr_amp_hi), rng.uniform() < p.tr_skip
                s = t0 + int(round(i * p.tr_period + rng.normal(0, p.tr_jitter)))
                if not skip and 0 <= s < n:
                    m[s:min(n, s + p.tr_w)] += a
        return m

    def rate(self):
        p = self.p
        d = 1 + p.amp * math.sin(2 * math.pi * self.t / p.period + self.phase)
        lam = p.base * d * (p.burst_factor if self.burst else 1.0) * math.exp(self.x)
        if self.ev is not None and self.t < len(self.ev):
            lam *= self.ev[self.t]
        return min(lam, p.rate_cap) if p.rate_cap else lam

    def next_tick(self):
        """-> (lambda_t, sorted arrival offsets in [0, 1)) for the current tick; then advances the state."""
        p, rng = self.p, self.rng
        lam = self.rate()
        n = rng.poisson(lam)
        u = np.sort(rng.uniform(0, 1, n))
        if p.burst_factor != 1.0:
            r = p.r_bn if self.burst else p.r_nb
            if rng.uniform() < 1 - math.exp(-r):
                self.burst = not self.burst
        if p.sigma:
            self.x = p.phi * self.x + math.sqrt(1 - p.phi ** 2) * p.sigma * rng.normal()
        self.t += 1
        return lam, u


def serve_tick(W, u, cap, p):
    """FIFO fluid server for one tick. -> (W_end, served, admitted, drops, latencies of admitted)."""
    served, prev, lat, drops = 0.0, 0.0, [], 0
    for a in u:
        d = min(W, cap * (a - prev))
        W -= d
        served += d
        prev = a
        if W + 1 > p.q_max:
            drops += 1
            continue
        lat.append((W + 1) / cap + p.l0)
        W += 1
    d = min(W, cap * (1 - prev))
    return W - d, served + d, len(lat), drops, lat


class PoissonMSEnv:
    def __init__(self, variant="poisson_ms", seed=0, params=None):
        self.variant = variant
        self.p = params or VARIANTS[variant]
        self.seed = seed
        self.delay = self.p.delay
        self.wl = Workload(self.p, _seed(seed, STREAM_LOAD))
        self.meas = _seed(seed, STREAM_MEAS)
        self.reset()

    def reset(self):
        self.wl.reset()
        self.time, self.num_vms, self.pending, self.W = 0, self.p.start_pods, [], 0.0
        cap = self.p.mu * self.num_vms
        return np.array([0.0, cap, 0.0, 100 * self.p.m_base, self.p.l0, self.num_vms, 0.0])

    def _apply(self, action):
        """Same mechanics as orig_variants.OrigEnv._delay_action + the verbatim scale step (bounds 1..20)."""
        left = [c - 1 for c in self.pending]
        self.num_vms += sum(1 for c in left if c <= 0)
        self.pending = [c for c in left if c > 0]
        if action == 2 and self.num_vms + len(self.pending) < MAX_PODS:
            if self.delay:
                self.pending.append(self.delay)
            else:
                self.num_vms += 1
        elif action == 0:
            if self.pending:
                self.pending.pop()
            elif self.num_vms > 1:
                self.num_vms -= 1

    def step(self, action):
        p = self.p
        self._apply(int(action))
        cap = p.mu * self.num_vms
        lam, u = self.wl.next_tick()
        W0 = self.W
        self.W, served, adm, drops, lat = serve_tick(self.W, u, cap, p)
        if lat:
            p95, mean_lat = float(np.percentile(lat, 95)), float(np.mean(lat))
        else:
            p95 = mean_lat = self.W / cap + p.l0
        cpu = max(0.0, 100 * served / cap + self.meas.normal(0, p.cpu_sd))
        mem = max(0.0, 100 * min(1.0, p.m_base + p.m_k * self.W / self.num_vms) + self.meas.normal(0, p.mem_sd))
        n_pend = len(self.pending)
        vm_cost = -p.pod_cost * (self.num_vms + n_pend)
        done = self.time + 1 >= p.ep_ticks
        backlog_end = self.W if done else 0.0
        slo_cost = -p.w_slo if (p95 > p.l_slo or drops or backlog_end > 0) else 0.0
        drop_cost = -p.w_drop * (drops + backlog_end)
        reward = served + vm_cost + slo_cost + drop_cost
        self.time += 1
        state = np.array([len(u), cap, cpu, mem, p95, self.num_vms, n_pend], dtype=float)
        info = {"served": served, "vm_cost": vm_cost, "slo_cost": slo_cost, "drop_cost": drop_cost,
                "arrivals": len(u), "admitted": adm, "drops": drops, "queue": self.W, "queue0": W0, "p95": p95,
                "mean_lat": mean_lat, "lam": lam, "backlog_end": backlog_end}
        return state, reward, done, info

    def clone(self):
        return copy.deepcopy(self)

    @property
    def n_pending(self):
        return len(self.pending)


def make(variant, seed):
    return PoissonMSEnv(variant, seed)


def run_fixed(variant, seed, pods, ticks=None):
    """Hold `pods` pods (reached by scale actions, delay included) for one episode -> per-episode metrics."""
    env = make(variant, seed)
    env.reset()
    ticks = ticks or env.p.ep_ticks
    tot = {"return": 0.0, "slo_viol": 0, "drops": 0, "pod_ticks": 0, "served": 0.0, "arrivals": 0, "backlog_end": 0.0}
    for _ in range(ticks):
        have = env.num_vms + env.n_pending
        a = 2 if have < pods else (0 if have > pods else 1)
        _, r, done, info = env.step(a)
        tot["return"] += r
        tot["slo_viol"] += info["slo_cost"] < 0
        tot["drops"] += info["drops"]
        tot["pod_ticks"] += env.num_vms + env.n_pending
        tot["served"] += info["served"]
        tot["arrivals"] += info["arrivals"]
        tot["backlog_end"] = env.W
        if done:
            break
    return tot
