"""Cycle-2 staged competition (J269): Opus lane (code-poisson) vs Astra lane (code-poisson-astra), no idle until 2/11.

ONE pre-registered plan, executed by a script (no LLM). Stages, all on the VAL split only, under the existing sandbox
R-20261029-006 (cap 136 CPU-h, cores 8-39, <=8 active, per-run <=2.5 h, seeds from its allowed ranges):
  S0  lstm_transfer screen gap (5k ticks, 2 seeds): Opus runs c0, Astra runs c1; both lanes' pools use both.
  W   3 lane-specific candidates per arm (derp_hist10: 2, derp: 0), 5k ticks, seeds 15010/15011 (same as the screen).
  E   per lane and arm: best pool candidate (val mean return) at 19968 ticks (transfer source 9984), seeds 15010/15011/15000.
  F   per arm: the lane-winner with the higher E mean; 10 fresh seeds 15100-15109 (Opus 15100-04, Astra 15105-09),
      19968 ticks, val split, weights saved. test12 / shift-test are NOT touched (separate joint freeze + approval).
  A   optional ablation (longer transfer source) only with leftover budget, after all F tasks are submitted.
Gates are fixed below (GATES). Any budget/hash/approval/forbidden-seed violation, >=3 failed runs, or any failed F run
STOPs both lanes (no retry, no cap increase). A failed W/E run drops that candidate (ranked last), no retry.
Usage (from ~/qrl-lab):  cycle3.py dry-run | start | drive | watch | status
"""
import hashlib, json, math, os, sqlite3, statistics as st, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
OUT = ROOT / '.lab/j269'
PARENT = 'R-20261029-006'
THREAD = 'M-20261029-006'
VENV_PY = str(ROOT / '.venv/bin/python')
LANES = {'opus': ('code-poisson', 'j119'), 'astra': ('code-poisson-astra', 'j120')}
SCREEN_DIR = {'opus': 'tuning/results/cycle2-j119', 'astra': 'tuning/results/cycle2-j120'}
ARMS = ['derp', 'derp_hist10', 'rppo', 'dinos', 'lstm', 'v2', 'lstm_transfer']
TUNE_SEEDS = [15010, 15011]
E_SEEDS = [15010, 15011, 15000]
F_SEEDS = {'opus': [15100, 15101, 15102, 15103, 15104], 'astra': [15105, 15106, 15107, 15108, 15109]}
TICKS_W, TICKS_E, SRC_E = 4992, 19968, 9984            # multiples of 128 like the screen's 4992
MARGIN, SELF_CAP, SLOTS_PER_LANE, MAX_FAILED = 1.25, 132.0, 4, 3
DEADLINE_SUBMIT = '2026-11-02T10:00:00+00:00'   # after this only F tasks are still submitted (W/E/A are dropped)
GATES = {'cap_check': 'used + active reservations + new reserve + 1.25*remaining mandatory nominal <= 132 (launcher hard 136)',
         'select': 'highest mean val return over the pool seeds; tie lowest SLO-violation rate, then candidate id',
         'F': 'per arm, lane winner with higher E mean (3 seeds) over its E runs; tie as above; both lanes E done first',
         'stop_both': 'approval/hash mismatch, cap check fails, forbidden seed, >=3 failed runs, any failed F run, STOP file',
         'idle': 'watch posts an alarm if a lane has queued-releasable work but 0 active for >10 min or the driver died'}
# rates (s/tick) from the immutable ledger of R-20261029-010 (review.ledger.rates)
RATES = {'lstm': (0, .1794253729961939, 189.29228945900013), 'lstm_transfer': (.1767853045833333, .1631976015344551, 161.09644767799978),
         'dinos': (0, .1004526531191907, 135.93019870600006), 'v2': (.0996972275040064, .09853604697916667, 128.95047811100005),
         'derp': (0, .03299614867608173, 73.15516656500003), 'derp_hist10': (0, .03369165099138622, 68.21142510199999),
         'rppo': (0, .007778662295673079, 224.31646295700003)}
S0_PLAN = (('opus', 0), ('opus', 1), ('astra', 1))      # c0 is identical in both lanes: run once; c1 differs by lane
FIXED = ('dinos', 'lstm', 'v2', 'lstm_transfer')
# Lane-specific W candidates: extra flags appended to the arm's screen-c0 command (n-step 3 base).
W_CANDS = {
    'opus': {a: [('lr2e-4', ['--lr', '2e-4']), ('lr5e-5', ['--lr', '5e-5']), ('gc1', ['--grad-clip', '1.0'])] for a in FIXED},
    'astra': {a: [('ns5', ['--n-step', '5']), ('ns2', ['--n-step', '2']), ('ts100', ['--target-sync', '100'])] for a in FIXED}}
W_CANDS['opus'].update({'rppo': [('lr1e-4', ['--lr', '1e-4']), ('lr1e-3', ['--lr', '1e-3']), ('ent3e-3', ['--ent-coef', '0.003'])],
                        'derp_hist10': [('h5', ['--derp-history', '5']), ('h20', ['--derp-history', '20'])], 'derp': []})
W_CANDS['astra'].update({'rppo': [('gl90', ['--gae-lambda', '0.9']), ('gm95', ['--gamma', '0.95']), ('ep5', ['--n-epochs', '5'])],
                         'derp_hist10': [('h3', ['--derp-history', '3']), ('h15', ['--derp-history', '15'])], 'derp': []})


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def log(msg):
    line = f'{now()} {msg}'
    print(line, flush=True)
    with open(OUT / 'driver.log', 'a') as f:
        f.write(line + '\n')


def nominal(arm, ticks, src=0):
    s, t, v = RATES[arm]
    return (s * src + t * ticks + v) / 3600.0


def wall(arm, ticks, src=0):
    return round(min(2.5, 1.6 * nominal(arm, ticks, src) + 0.1), 2)


def flag(cmd, name, value):
    cmd = list(cmd)
    if name in cmd:
        cmd[cmd.index(name) + 1] = str(value)
    else:
        cmd += [name, str(value)]
    return cmd


def screen_cmds():
    """lane -> arm -> {c: cmd} from the frozen screen manifests of EACH lane (c1 differs between the lanes)."""
    sw = json.loads((ROOT / '.lab/specs/R-20261029-010.json').read_text())['review']['screen_waves']
    out = {}
    for lane, (cwd, _) in LANES.items():
        d = {}
        for w in sw[cwd]:
            for e in w['entries']:
                if e['seed'] != 15010:
                    continue
                arm, c = e['name'].split('-screen-')[1].rsplit('-s', 1)[0].rsplit('-c', 1)
                d.setdefault(arm, {})[int(c)] = e['cmd']
        out[lane] = d
    return out


def retarget(cmd, arm, seed, out, ticks, src):
    c = flag(cmd, '--seed', seed)
    c = flag(c, '--out', out)
    c = flag(c, '--total-ticks', ticks)
    if '--checkpoints' in c:
        c = flag(c, '--checkpoints', ticks)
    if '--pretrain-ticks' in c:
        c = flag(c, '--pretrain-ticks', src)
        c = flag(c, '--finetune-ticks', ticks)
        c = flag(c, '--total-ticks', src + ticks)   # tool requires total == pretrain + finetune (J274 fix)
    return c


def cand_extra(base, extra):
    c = list(base)
    for i in range(0, len(extra), 2):
        c = flag(c, extra[i], extra[i + 1])
    return c


def task(lane, stage, arm, cid, cmd_base, seed, ticks, src):
    cwd = LANES[lane][0]
    name = f'c3-{lane}-{stage}-{arm}-{cid}-s{seed}' + ('-r2' if stage == 'S0' else '')   # r2: S0 rerun after the total-ticks fix (J274)
    out = f'tuning/results/cycle3-{lane}/{name}.json'
    cmd = retarget(cmd_base, arm, seed, out, ticks, src)
    w = wall(arm, ticks, src)
    return dict(name=name, lane=lane, stage=stage, arm=arm, cid=cid, seed=seed, cwd=cwd, out=out, ticks=ticks, src=src, nominal=nominal(arm, ticks, src),
                wall=w, cmd=cmd)


def child_spec(t):
    return {'name': t['name'], 'scope': 'sim', 'repo': t['cwd'], 'cwd': t['cwd'], 'max_parallel': 1, 'cpu_affinity': '8-39',
            'limits': {'wall_clock_hours': t['wall']},
            'entries': [{'name': t['name'], 'seed': t['seed'], 'cpus': 1, 'wall_clock_hours': t['wall'], 'cmd': t['cmd']}]}


def pretrain_of(cmd):
    """Pretrain ticks in a task command (0 if none); ledger records from before J274 carry no 'src' field."""
    return int(cmd[cmd.index('--pretrain-ticks') + 1]) if '--pretrain-ticks' in cmd else 0


def val_stats(path, seed=None, ticks=None, ck_key=None):
    """(mean return, mean SLO-violation rate) of the last checkpoint on val; raises on any provenance/shape mismatch."""
    x = json.loads(Path(path).read_text())
    if x.get('eval_splits') != ['val'] or (seed is not None and x.get('seed') != seed) or \
            (ticks is not None and x.get('total_ticks') != ticks):
        raise ValueError('provenance mismatch')
    ck = list(x['checkpoint_results'].items())[-1]
    if ticks is not None and ck[0] != str(ck_key if ck_key is not None else ticks):
        raise ValueError('wrong checkpoint')
    ep = ck[1]['val']['episodes']
    if len(ep) != 20:
        raise ValueError('not 20 val episodes')
    r, v = [e['ret'] for e in ep], [e['slo_viol_rate'] for e in ep]
    if not all(math.isfinite(t) for t in r + v):
        raise ValueError('non-finite metric')
    return st.mean(r), st.mean(v)


OK = set()      # names of cycle-3 runs whose launcher record is done/exit 0 (set by the driver)


def load(path):
    p = Path(path)
    if 'cycle3-' in str(p) and p.stem not in OK:
        return None
    try:
        return val_stats(p)
    except Exception:
        return None


def pool(lane, arm, sc):
    """candidate id -> (base cmd, [result files]) for W-stage selection of one lane."""
    p = {}
    sdir = ROOT / LANES[lane][0] / SCREEN_DIR[lane]
    for c in (0, 1):
        files = [sdir / f'{LANES[lane][1]}-screen-{arm}-c{c}-s{s}.json' for s in TUNE_SEEDS]
        if arm == 'lstm_transfer':   # screen gap: S0 runs of both lanes
            l = 'opus' if c == 0 else lane
            files = [ROOT / LANES[l][0] / f'tuning/results/cycle3-{l}/c3-{l}-S0-{arm}-c{c}-s{s}-r2.json' for s in TUNE_SEEDS]
        p[f'c{c}'] = (sc[lane][arm][c], files)
    for cid, extra in W_CANDS[lane][arm]:
        base = cand_extra(sc[lane][arm][0], extra)
        p[cid] = (base, [ROOT / LANES[lane][0] / f'tuning/results/cycle3-{lane}/c3-{lane}-W-{arm}-{cid}-s{s}.json' for s in TUNE_SEEDS])
    return p


def rank(cands):
    """cands: id -> (base, files). Returns best id by the pre-registered rule, or None if no candidate has results."""
    scored = []
    for cid, (_, files) in cands.items():
        r = [load(f) for f in files]
        if r and all(x is not None for x in r):
            scored.append((-st.mean(x[0] for x in r), st.mean(x[1] for x in r), cid))
    return min(scored)[2] if scored else None


def all_tasks_static(sc):
    """S0 and W tasks (known upfront)."""
    ts = []
    for lane, c in S0_PLAN:
        for s in TUNE_SEEDS:
            ts.append(task(lane, 'S0', 'lstm_transfer', f'c{c}', sc[lane]['lstm_transfer'][c], s, TICKS_W, TICKS_W))
    for lane in LANES:
        for arm in ARMS:
            for cid, extra in W_CANDS[lane][arm]:
                for s in TUNE_SEEDS:
                    src = TICKS_W if arm in ('v2', 'lstm_transfer') else 0
                    ts.append(task(lane, 'W', arm, cid, cand_extra(sc[lane][arm][0], extra), s, TICKS_W, src))
    return ts


def e_tasks(lane, arm, sc):
    p = pool(lane, arm, sc)
    best = rank(p)
    if best is None:
        return None, []
    src = SRC_E if arm in ('v2', 'lstm_transfer') else 0
    return best, [task(lane, 'E', arm, best, p[best][0], s, TICKS_E, src) for s in E_SEEDS]


def e_score(lane, arm, best):
    r = [load(ROOT / LANES[lane][0] / f'tuning/results/cycle3-{lane}/c3-{lane}-E-{arm}-{best}-s{s}.json') for s in E_SEEDS]
    if any(x is None for x in r):
        return None
    return (-st.mean(x[0] for x in r), st.mean(x[1] for x in r))


def f_tasks(arm, sc, winners):
    """winners: lane -> (best cid). Picks the lane winner with the better E score; splits the 10 seeds by lane."""
    sc_ = {l: e_score(l, arm, winners[l]) for l in LANES}
    ok = [l for l in LANES if sc_[l] is not None]       # a lane whose E lost a seed to a failure is out for this arm
    if not ok:
        return None, []
    lane_win = min(ok, key=lambda l: (sc_[l], winners[l], l))
    base = pool(lane_win, arm, sc)[winners[lane_win]][0]
    src = SRC_E if arm in ('v2', 'lstm_transfer') else 0
    ts = [task(l, 'F', arm, f'{lane_win}-{winners[lane_win]}', base, s, TICKS_E, src) for l in LANES for s in F_SEEDS[l]]
    return (lane_win, winners[lane_win]), ts


def planned_nominal():
    sc = screen_cmds()
    w = sum(t['nominal'] for t in all_tasks_static(sc) if t['stage'] == 'W')
    s0 = sum(t['nominal'] for t in all_tasks_static(sc) if t['stage'] == 'S0')
    e = sum(nominal(a, TICKS_E, SRC_E if a in ('v2', 'lstm_transfer') else 0) * len(E_SEEDS) for a in ARMS) * 2
    f = sum(nominal(a, TICKS_E, SRC_E if a in ('v2', 'lstm_transfer') else 0) * 10 for a in ARMS)
    return dict(S0=s0, W=w, E=e, F=f)


# ---------------- DB / launcher ----------------
def db():
    c = sqlite3.connect(f'file:{ROOT}/.lab/lab.db?mode=ro', uri=True, timeout=30)
    c.row_factory = sqlite3.Row
    return SimpleNamespace(conn=c)


def runs(d, pattern):
    return d.conn.execute('SELECT * FROM runs WHERE request_id=? AND (name LIKE ? OR name=?)', (PARENT, '%' + pattern, pattern)).fetchall()


def lane_active(d, lane):
    return d.conn.execute("SELECT name FROM runs WHERE request_id=? AND status IN ('starting','running') AND name LIKE ?",
                          (PARENT, f'%c3-{lane}-%')).fetchall()


def approval_ok():
    from labdb import canonical_hash
    spec = json.loads((OUT / 'plan-spec.json').read_text())
    rid = (OUT / 'request_id.txt').read_text().strip()
    row = db().conn.execute('SELECT state, spec_hash FROM requests WHERE id=?', (rid,)).fetchone()
    me = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return bool(row and row['state'] == 'approved' and row['spec_hash'] == canonical_hash(spec) and spec['plan_sha256'] == me)


def post(body, status='in_progress'):
    p = OUT / 'post.md'
    p.write_text(body + '\n\n— Πάρις')
    subprocess.run(['python3', 'tools/labq.py', 'post', '--reply-to', THREAD, '--kind', 'status', '--status', status,
                    '--author', 'coordinator', '--body-file', str(p)], cwd=ROOT, check=False)


def write_state(**kw):
    s = json.loads((OUT / 'state.json').read_text()) if (OUT / 'state.json').exists() else {}
    s.update(kw, ts=now(), pid=os.getpid() if kw.get('driver') else s.get('pid'))
    (OUT / 'state.json').write_text(json.dumps(s, indent=1))


def stop(reason):
    log(f'STOP: {reason}')
    write_state(state='STOPPED', reason=reason, driver=True)
    post(f'Κώστα, ο κύκλος J269 ΣΤΑΜΑΤΗΣΕ και στα δύο lanes: {reason}. Κανένα retry/αύξηση ορίου. Log: .lab/j269/driver.log', 'done')
    sys.exit(2)


def a_tasks(lane, sc, winners):
    """Optional ablation: longer transfer source (19968) for the lane's E-winner of v2 (opus) / lstm_transfer (astra)."""
    arm = 'v2' if lane == 'opus' else 'lstm_transfer'
    if arm not in winners[lane]:
        return []
    base = pool(lane, arm, sc)[winners[lane][arm]][0]
    return [task(lane, 'A', arm, f'{winners[lane][arm]}-src20k', base, s, TICKS_E, TICKS_E) for s in E_SEEDS]


def drive():
    import sandbox_guard as G
    sc = screen_cmds()
    queue = {l: [] for l in LANES}
    TASKS, seen, failed, checked = {}, set(), set(), set()
    submitted_nom = 0.0
    done_e, done_f, winners, a_added = set(), set(), {l: {} for l in LANES}, False
    mandatory = sum(planned_nominal().values())
    static_by_name = {}
    for t in all_tasks_static(sc):
        queue[t['lane']].append(t)
        static_by_name[t['name']] = t
    import fcntl
    lock = open(OUT / 'driver.lock', 'w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        sys.exit('another driver holds driver.lock')
    ledger = OUT / 'submitted.jsonl'
    if ledger.exists():                    # resume after a restart: never resubmit, keep accounting
        for line in ledger.read_text().splitlines():
            r = json.loads(line)
            if r['stage'] == 'S0' and not r['name'].endswith('-r2'):
                continue                   # 6 S0 runs failed on the total-ticks bug (J274): superseded by the -r2 reruns, charged via DB usage
            r = {**static_by_name.get(r['name'], {}), **r}   # ledger lines keep only a summary: restore cmd/out/cwd for the checks
            TASKS[r['name']] = r
            seen.add(r['name'])
            if r['stage'] != 'A':
                submitted_nom += r['nominal']
            if not runs(db(), r['name']):   # intent written but no launcher record: do not guess
                stop(f'resume: intent without DB row for {r["name"]} (reconcile manually)')
    log(f'drive start mandatory_nominal={mandatory:.2f} resumed={len(seen)}')
    while True:
        if (OUT / 'STOP').exists():
            stop('STOP file')
        if not approval_ok():
            stop('approval/hash/plan mismatch')
        d = db()
        for name in sorted(seen - checked):          # finished runs: success check, no retry
            rows = runs(d, name)
            if not rows:
                if time.time() - TASKS[name].get('t0', time.time()) > 900:
                    stop(f'no launcher DB row for {name} 15 min after submission')
                continue
            if rows[0]['status'] in ('starting', 'running'):
                continue
            x, tk = rows[0], TASKS[name]
            checked.add(name)
            outp = ROOT / tk['cwd'] / tk['out']
            if x['status'] == 'done' and x['exit_code'] == 0 and outp.exists():
                try:
                    val_stats(outp, tk['seed'], tk['ticks'] + pretrain_of(tk['cmd']), tk['ticks'])    # provenance + 20 val episodes + finite, else a declared failure
                    OK.add(name)
                except Exception as ex:
                    log(f'check {name}: {ex!r}')
            if name not in OK:
                failed.add(name)
                log(f'FAILED {name} status={x["status"]} exit={x["exit_code"]}')
                if tk['stage'] == 'F':
                    stop(f'failed F run {name}')
                if len(failed) >= MAX_FAILED:
                    stop(f'{len(failed)} failed runs')
        for lane in LANES:                            # stage releases (pure functions of result files)
            for arm in ARMS:
                if (lane, arm) in done_e:
                    continue
                wdone = all(f"c3-{lane}-W-{arm}-{cid}-s{s}" in checked for cid, _ in W_CANDS[lane][arm] for s in TUNE_SEEDS)
                s0done = arm != 'lstm_transfer' or all(f'c3-{l}-S0-{arm}-c{c}-s{s}-r2' in checked
                                                       for l, c in S0_PLAN for s in TUNE_SEEDS)
                # a failed run is in `checked` too (it is marked failed and its candidate ranks last: no result file)
                if not (wdone and s0done):
                    continue
                best, ts = e_tasks(lane, arm, sc)
                if best is None:
                    stop(f'no valid candidate for {lane} {arm}')
                done_e.add((lane, arm))
                winners[lane][arm] = best
                queue[lane] += ts
                log(f'E release {lane} {arm}: {best}')
        for arm in ARMS:
            if arm in done_f or not all((l, arm) in done_e for l in LANES):
                continue
            if not all(f'c3-{l}-E-{arm}-{winners[l][arm]}-s{s}' in checked for l in LANES for s in E_SEEDS):
                continue
            w, ts = f_tasks(arm, sc, {l: winners[l][arm] for l in LANES})
            if w is None:
                stop(f'no valid E result for {arm}')
            done_f.add(arm)
            for t in ts:
                queue[t['lane']].append(t)
            log(f'F release {arm}: {w}')
        if len(done_f) == len(ARMS) and not a_added and not any(q['stage'] == 'F' for l in LANES for q in queue[l]):   # optional ablation, lowest priority, appended last
            a_added = True
            for lane in LANES:
                queue[lane] += a_tasks(lane, sc, winners)
        used = G.used_cpu_hours(d, PARENT, strict=True)
        active = [r['name'] for r in d.conn.execute("SELECT name FROM runs WHERE request_id=? AND status IN ('starting','running')", (PARENT,))]
        for lane in LANES:
            while queue[lane] and len(lane_active(d, lane)) < SLOTS_PER_LANE:
                t = queue[lane].pop(0)
                if t['name'] in seen:
                    continue
                if t['stage'] != 'F' and now() > DEADLINE_SUBMIT:
                    log(f'deadline: dropped {t["name"]}')
                    continue
                remaining = 0.0 if t['stage'] == 'A' else max(0.0, mandatory - submitted_nom - t['nominal'])
                projected = used + t['wall'] + MARGIN * remaining      # `used` already counts active reservations
                if projected > SELF_CAP:
                    if t['stage'] == 'A':      # optional work is dropped silently when the budget is not there
                        queue[lane] = [q for q in queue[lane] if q['stage'] != 'A']
                        log(f'A dropped: projected {projected:.2f} > {SELF_CAP}')
                        break
                    stop(f'cap check {projected:.2f} > {SELF_CAP} before {t["name"]}')
                sp = OUT / 'children' / f'{t["name"]}.json'
                sp.parent.mkdir(exist_ok=True)
                sp.write_text(json.dumps(child_spec(t), indent=1))
                rec = {k: t[k] for k in ('name', 'lane', 'stage', 'arm', 'cid', 'seed', 'cwd', 'out', 'ticks', 'nominal', 'wall')}
                with open(ledger, 'a') as f:          # durable intent BEFORE the launch (reconciled with the DB on resume)
                    f.write(json.dumps(dict(rec, ts=now())) + '\n')
                    f.flush()
                    os.fsync(f.fileno())
                p = subprocess.run(['python3', 'tools/launch_run.py', 'sandbox-start', '--request', PARENT, '--spec', str(sp)],
                                   cwd=ROOT, capture_output=True, text=True)
                log(f'sandbox-start {t["name"]} rc={p.returncode} {p.stdout.strip()[-160:]} {p.stderr.strip()[-300:]}')
                if p.returncode != 0:
                    stop(f'sandbox-start failed for {t["name"]}')
                rec['t0'] = time.time()
                TASKS[t['name']] = dict(rec, cmd=t['cmd'])    # the ledger line is a summary; the check needs cmd (pretrain ticks)
                seen.add(t['name'])
                if t['stage'] != 'A':
                    submitted_nom += t['nominal']
                time.sleep(2)
                d = db()
                used = G.used_cpu_hours(d, PARENT, strict=True)
        pending = sum(len(q) for q in queue.values())
        write_state(state='RUNNING', driver=True, used=used, active=len(active), queued=pending, submitted=len(seen),
                    failed=sorted(failed), e_released=len(done_e), f_released=len(done_f),
                    lane_queued={l: len(queue[l]) for l in LANES}, lane_active={l: len(lane_active(d, l)) for l in LANES})
        active = [r['name'] for r in d.conn.execute("SELECT name FROM runs WHERE request_id=? AND status IN ('starting','running')", (PARENT,))]
        if (a_added or now() > DEADLINE_SUBMIT) and pending == 0 and not active and seen <= checked:
            complete = len(done_f) == len(ARMS) and len(done_e) == 2 * len(ARMS) and not any(
                n.split('-', 2)[2].startswith('F-') and n not in OK for n in ())
            nF = sum(1 for n in OK if '-F-' in n)
            complete = complete and nF == 10 * len(ARMS)
            write_state(state='DONE' if complete else 'INCOMPLETE', driver=True, f_ok=nF)
            post(f'Κώστα, ο κύκλος J269 {"ολοκληρώθηκε" if complete else "ΤΕΛΕΙΩΣΕ ΧΩΡΙΣ να ολοκληρωθεί (deadline/αποτυχίες)"}: '
                 f'F επιτυχή {nF}/{10 * len(ARMS)}, χρήση R-006 {used:.2f}/136 CPU-h, {len(seen)} runs, {len(failed)} αποτυχίες. '
                 f'Test12 δεν αγγίχτηκε. Αποτελέσματα: tuning/results/cycle3-*', 'done')
            return
        time.sleep(30)


def drive_safe():
    try:
        drive()
    except SystemExit:
        raise
    except Exception as e:           # never die silently: announce and stop (state file lets watch/status see it)
        stop(f'driver exception {type(e).__name__}: {e}')


def watch():
    """Idle alarm (script, no LLM): driver dead, or a lane with queued work and no active run for >10 min."""
    idle_since, last_alarm = {}, 0.0
    while True:
        time.sleep(120)
        try:
            s = json.loads((OUT / 'state.json').read_text())
        except Exception:
            s = {}
        if s.get('state') in ('DONE', 'STOPPED'):
            log(f'watch exit: {s.get("state")}')
            return
        problems = []
        try:
            os.kill(int(s.get('pid') or 0), 0)
        except Exception:
            problems.append('driver process is not running')
        try:
            if (datetime.now(timezone.utc) - datetime.fromisoformat(s['ts'])).total_seconds() > 420:
                problems.append('driver heartbeat older than 7 min')
        except Exception:
            problems.append('no driver heartbeat')
        for l in LANES:
            if (s.get('lane_queued') or {}).get(l) and not (s.get('lane_active') or {}).get(l):
                idle_since.setdefault(l, time.time())
                if time.time() - idle_since[l] > 600:
                    problems.append(f'lane {l} has queued work but 0 active runs for >10 min')
            else:
                idle_since.pop(l, None)
        if problems and time.time() - last_alarm > 3 * 3600:
            last_alarm = time.time()
            log('ALARM ' + '; '.join(problems))
            post('Κώστα, ΣΥΝΑΓΕΡΜΟΣ αδράνειας J269: ' + '; '.join(problems) + '. Δες .lab/j269/driver.log και state.json.', 'in_progress')


def start():
    """One-shot detached start (run by the coordinator job after the researcher approves). Receipt: .lab/j269/receipt.json."""
    if not approval_ok():
        sys.exit('NOT approved / hash mismatch: nothing started')
    if (OUT / 'receipt.json').exists():
        sys.exit('already started (receipt exists)')
    pids = {}
    for role in ('drive', 'watch'):
        lf = open(OUT / f'{role}.out', 'a')
        p = subprocess.Popen([sys.executable, '-u', str(Path(__file__)), role], cwd=ROOT, stdout=lf, stderr=lf, stdin=subprocess.DEVNULL,
                             start_new_session=True)
        pids[role] = p.pid
    (OUT / 'receipt.json').write_text(json.dumps(dict(pids=pids, started=now(), plan_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()), indent=1))
    print('STARTED', pids)


def dry_run():
    """No run is started: builds every static task + E/F with screen results as stand-ins, validates each child spec with the
    sandbox guard against the parent sandbox (cap 2.5 h) and prints the nominal budget projection."""
    import sandbox_guard as G
    sc = screen_cmds()
    parent = json.loads((ROOT / '.lab/specs/R-20261029-006.json').read_text())
    parent['sandbox']['per_run_wall_clock_hours'] = 2.5
    ts = all_tasks_static(sc)
    for lane in LANES:                      # synthetic E/F tasks (best = c0) just to validate commands/seeds
        for arm in ARMS:
            src = SRC_E if arm in ('v2', 'lstm_transfer') else 0
            ts += [task(lane, 'E', arm, 'c0', sc[lane][arm][0], s, TICKS_E, src) for s in E_SEEDS]
            ts += [task(lane, 'F', arm, 'x', sc[lane][arm][0], s, TICKS_E, src) for s in F_SEEDS[lane]]
            if arm in ('v2', 'lstm_transfer') and ((lane == 'opus') == (arm == 'v2')):
                ts += [task(lane, 'A', arm, 'x', sc[lane][arm][0], s, TICKS_E, TICKS_E) for s in E_SEEDS]
    bad = 0
    names = set()
    for t in ts:
        assert t['name'] not in names, t['name']
        names.add(t['name'])
        try:
            G.check_child(child_spec(t), parent)
        except Exception as e:
            bad += 1
            print('INVALID', t['name'], e)
    by = {}
    for t in ts:
        by[t['stage']] = by.get(t['stage'], 0) + t['nominal']
    pn = planned_nominal()
    print(f'tasks={len(ts)} invalid={bad}')
    print('nominal CPU-h by stage (dry set, E/F for both lanes):', {k: round(v, 2) for k, v in by.items()})
    print('planned mandatory nominal:', {k: round(v, 2) for k, v in pn.items()}, 'sum', round(sum(pn.values()), 2),
          'x1.25 =', round(1.25 * sum(pn.values()), 2), '+ used ~11.5 vs cap', SELF_CAP)
    print('max wall per run:', max(t['wall'] for t in ts))
    print('sample cmd:', ' '.join(next(t for t in ts if t['stage'] == 'W' and t['lane'] == 'astra' and t['arm'] == 'v2')['cmd'][1:]))
    return bad


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'dry-run'
    OUT.mkdir(exist_ok=True)
    {'dry-run': dry_run, 'start': start, 'drive': drive_safe, 'watch': watch,
     'status': lambda: print((OUT / 'state.json').read_text() if (OUT / 'state.json').exists() else 'no state')}[cmd]()
