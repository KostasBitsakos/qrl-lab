#!/usr/bin/env python3
"""QRL-Lab supervisor (J383, M-20261107-005): one script-only check per call; a systemd --user timer calls it. No LLM.

Detects: C345 experiment drivers/watchers dead without a terminal state (a clean exit after DONE is NOT an alarm),
stalled experiments (no new output of any active run), STOP/stopped/incomplete parents, runs whose process is gone,
dead qrl-* user services, a stale dispatcher heartbeat, new `failed` dispatcher jobs (journal).
Notifies at once (labq status post in the lab thread; judgement cases also a labq `ask`). Phone push is NOT
available to scripts (PushNotification is an agent tool); the dashboard thread is the channel.

Auto-recovery, ONLY these safe cases (docs/rules/supervisor.md):
  * driver/watch dead, state RUNNING, no STOP file, seen dead on two polls  -> `driver.py resume` (re-spawns only the
    dead roles inside the SAME approved frozen spec/session; the Engine re-checks approval, hash and CPU-h caps; max 2);
  * dead qrl-dispatcher/qrl-dashboard user service -> `systemctl --user restart` (max 2 per 6 h).
Everything else (STOP file, STOPPED/INCOMPLETE, stalls, dead run payloads, exhausted retries, over-cap) = notify + ask.
Never starts a new run, never edits a spec, never touches test splits.

  python3 tools/supervisor.py [--dry-run]          one check        python3 tools/supervisor.py install   print timer command
"""
import argparse
import fcntl
import json
import os
import shlex
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get('QRL_LAB_DIR') or Path(__file__).resolve().parents[1])
LAB = ROOT / '.lab'
SUP = LAB / 'supervisor'
THREAD = 'M-20261102-040'
SERVICES = ('qrl-dispatcher.service', 'qrl-dashboard.service')
ACTIVE = ('starting', 'running')
TERMINAL = ('DONE', 'INCOMPLETE', 'STOPPED')
HEARTBEAT_MAX = 180        # s, driver state.json / watch-ready.json
CONFIRM_S = 90             # a dead role must be seen on two polls at least this far apart before any action
STALL_MIN = 60             # min without new output of every active run
MAX_RESUMES = 2
MAX_SERVICE_RESTARTS = 2   # per SERVICE_WINDOW
SERVICE_WINDOW = 6 * 3600
DISPATCHER_BEAT_MAX = 300


def now_iso(t):
    return datetime.fromtimestamp(t, timezone.utc).isoformat(timespec='seconds')


def read_json(p, default=None):
    try:
        return json.loads(Path(p).read_text())
    except (OSError, ValueError):
        return default


def atomic(p, v):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix('.tmp')
    tmp.write_text(json.dumps(v, ensure_ascii=False, indent=2))
    os.replace(tmp, p)


def pid_alive(pid):
    """Alive and not a zombie (kill -0 succeeds on zombies)."""
    try:
        stat = Path(f'/proc/{int(pid)}/stat').read_text().rsplit(')', 1)[1].split()[0]
        return stat not in ('Z', 'X')
    except (OSError, ValueError, IndexError, TypeError):
        return False


# ---------------------------------------------------------------- observation (side-effect free)
def discover(lab=LAB):
    """Every dir that holds a C345-style parent: receipt + parent-spec + (optional) state."""
    return sorted(p.parent for p in lab.glob('*/receipt.json')
                  if (p.parent / 'parent-spec.json').exists() and 'pids' in (read_json(p) or {}))


def active_rows(request, root=ROOT):
    try:
        with sqlite3.connect(f'file:{root}/.lab/lab.db?mode=ro', uri=True, timeout=10) as db:
            db.row_factory = sqlite3.Row
            return [dict(r) for r in db.execute('SELECT * FROM runs WHERE request_id=?', (request,))]
    except sqlite3.Error:
        return None


def observe(out, now, rows_fn=active_rows, alive=pid_alive):
    out = Path(out)
    receipt = read_json(out / 'receipt.json', {})
    # Order matters (clean-exit race, J380): pids first, THEN state; a driver that wrote a terminal state before
    # exiting is seen with that state.
    alive_roles = {r: alive(receipt.get('pids', {}).get(r, 0)) for r in ('drive', 'watch')}
    state = read_json(out / 'state.json')
    rows = rows_fn(receipt.get('request')) if receipt.get('request') else []
    rows = rows or []
    beat = read_json(out / 'watch-ready.json', {}).get('ts')
    outs = []
    for r in rows:
        if r.get('status') in ACTIVE and r.get('run_dir'):
            try:
                outs.append((Path(r['run_dir']) / 'output.log').stat().st_mtime)
            except OSError:
                outs.append(None)
    dead_runs = [r['run_id'] for r in rows if r.get('status') == 'running' and r.get('pid') and not alive(r['pid'])]
    return dict(out=str(out), name=out.name, receipt=receipt, state=state, alive=alive_roles,
                stop_file=(out / 'STOP').exists(),
                state_age=(now - datetime.fromisoformat(state['ts']).timestamp()) if state and state.get('ts') else None,
                watch_age=(now - datetime.fromisoformat(beat).timestamp()) if beat else None,
                n_active=sum(1 for r in rows if r.get('status') in ACTIVE),
                last_output_age=(now - max(m for m in outs if m) if any(outs) else None),
                dead_runs=dead_runs, resumes=receipt.get('resumes', 0))


def classify(o, stall_min=STALL_MIN):
    """-> (verdict, detail). Verdicts: healthy, finished, role_dead, stopped, stop_file, stalled, runs_dead, no_state."""
    st = (o['state'] or {}).get('state')
    if st is None:
        return ('role_dead', 'driver without state') if not any(o['alive'].values()) else ('healthy', '')
    if st in TERMINAL:
        if st == 'DONE':
            return 'finished', 'DONE'
        return 'stopped', f"{st}: {o['state'].get('reason', 'unknown reason')}"
    # state RUNNING / READY / STOPPING
    if o['stop_file']:
        return 'stop_file', 'STOP file present (watchdog or manual)'
    dead = [r for r, a in o['alive'].items() if not a]
    if dead:
        return 'role_dead', 'dead: ' + ', '.join(dead) + f" (state {st}, heartbeat age {o['state_age']:.0f}s)" if o['state_age'] is not None else 'dead: ' + ', '.join(dead)
    if o['dead_runs']:
        return 'runs_dead', 'active run without process: ' + ', '.join(o['dead_runs'])
    if o['state_age'] is not None and o['state_age'] > HEARTBEAT_MAX:
        return 'stalled', f"driver heartbeat {o['state_age']:.0f}s old with live pid"
    if o['n_active'] and o['last_output_age'] is not None and o['last_output_age'] > stall_min * 60:
        return 'stalled', f"no new output of any active run for {o['last_output_age'] / 60:.0f} min"
    return 'healthy', ''


# ---------------------------------------------------------------- policy (pure)
def decide(verdict, o, mem, now):
    """-> action in {None, 'resume', 'ask'}; mem is the per-target memory (mutated: suspect_since)."""
    if verdict != 'role_dead':
        mem.pop('suspect_since', None)
        if verdict == 'healthy':
            mem.pop('resume_failed', None)
        return 'ask' if verdict in ('stopped', 'stop_file', 'runs_dead', 'stalled') else None
    first = mem.setdefault('suspect_since', now)
    if now - first < CONFIRM_S:
        return None                          # wait for the second poll: rules out a clean-exit/handoff race
    if o['state'] is None or (o['state_age'] or 0) > 6 * 3600:
        return 'ask'                         # no preserved state, or abandoned long ago: never auto-resume
    if mem.get('resume_failed') or o['resumes'] >= MAX_RESUMES or mem.get('resume_attempts', 0) >= MAX_RESUMES:
        return 'ask'
    return 'resume'


def service_action(unit, active_state, hist, now):
    """-> 'restart' | 'ask' | None. hist = list of restart epochs."""
    if active_state not in ('inactive', 'failed'):
        return None
    recent = [t for t in hist if now - t < SERVICE_WINDOW]
    return 'restart' if len(recent) < MAX_SERVICE_RESTARTS else 'ask'


# ---------------------------------------------------------------- effects (injectable)
def run(cmd, **kw):
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=120, **kw)


def post(body, thread=THREAD):
    p = run([sys.executable, str(ROOT / 'tools/labq.py'), 'post', '--reply-to', thread, '--author', 'coordinator',
             '--model', 'script supervisor (χωρίς LLM)', '--kind', 'status', '--body', body])
    if p.returncode:
        raise RuntimeError(p.stderr.strip()[:200])
    return p.stdout.strip()


def ask(title, body):
    f = SUP / 'ask-body.md'
    SUP.mkdir(parents=True, exist_ok=True)
    f.write_text(body)
    p = run([sys.executable, str(ROOT / 'tools/labq.py'), 'ask', '--kind', 'question', '--scope', 'sim', '--title', title,
             '--body-file', str(f), '--thread', THREAD])
    if p.returncode:
        raise RuntimeError(p.stderr.strip()[:200])
    return p.stdout.strip()


def do_resume(out, request):
    env = dict(os.environ, QRL_C345_OUT=str(out))
    entry = 'tools/c345/fb_restart.py' if (Path(out) / 'superseded.json').exists() else 'tools/c345/driver.py'  # J402
    p = run([str(ROOT / '.venv/bin/python'), str(ROOT / entry), 'resume', '--request', request], env=env)
    return p.returncode == 0, (p.stdout + p.stderr).strip()[-300:]


def unit_state(unit):
    p = run(['systemctl', '--user', 'is-active', unit])
    txt = (p.stdout + p.stderr).strip()
    return ('unobservable' if 'Failed to connect' in txt else p.stdout.strip() or 'unknown')


def restart_unit(unit):
    return run(['systemctl', '--user', 'restart', unit]).returncode == 0


def new_failed_jobs(state, lab=LAB, now=None):
    """Dispatcher journal lines `] failed` appended since the last poll (first poll = baseline)."""
    day = datetime.fromtimestamp(now or time.time(), timezone.utc).strftime('%Y-%m-%d')
    f = ROOT / 'docs/journal' / f'{day}.md'
    if not f.exists():
        return []
    data = f.read_bytes()
    key = 'journal_off:' + day
    off = state.get(key)
    state[key] = len(data)
    if off is None:
        return []
    return [l[:160] for l in data[off:].decode(errors='replace').splitlines() if '] failed' in l]


# ---------------------------------------------------------------- orchestration
MSG = {
    'role_dead': 'Ο driver/watcher του {n} σταμάτησε χωρίς τελική κατάσταση ({d}).',
    'stopped': 'Το {n} σταμάτησε: {d}.',
    'stop_file': 'Το {n} έχει αρχείο STOP: {d}.',
    'runs_dead': 'Το {n} έχει ενεργό run χωρίς διεργασία: {d}.',
    'stalled': 'Το {n} φαίνεται κολλημένο: {d}.',
    'finished': 'Το {n} ολοκληρώθηκε κανονικά (DONE).',
}


def tick(now=None, targets=None, rows_fn=active_rows, alive=pid_alive, poster=post, asker=ask, resumer=do_resume,
         unit_fn=unit_state, restarter=restart_unit, dry=False, mem_path=SUP / 'state.json', services=SERVICES,
         journal=new_failed_jobs, beat_path=LAB / 'bridge_heartbeat'):
    now = time.time() if now is None else now
    mem = read_json(mem_path, {}) or {}
    log = []

    def notify(key, text, need_ask=None):
        """Post once per key, ask once per key. Delivery is persisted only after success (a failed post/ask retries next
        poll); an exception never aborts the poll, so counters and actions already taken stay recorded."""
        sent = mem.setdefault('sent', {})
        if dry:
            if not sent.get(key):
                log.append(('would-notify', key, text))
            return
        try:
            if not sent.get(key):
                sent[key] = poster('Κώστα,\n\n' + text + '\n\nΑυτόματος έλεγχος (script, χωρίς LLM) ' + now_iso(now) +
                                   '.\n\n— Πάρις') or True
                log.append(('notified', key, text))
            if need_ask and not sent.get('ask:' + key):
                asker(need_ask[0], need_ask[1])
                sent['ask:' + key] = True
        except Exception as ex:                                 # noqa: BLE001 - retried next poll
            log.append(('notify-error', key, type(ex).__name__ + ': ' + str(ex)[:120]))

    for out in (discover() if targets is None else targets):
        o = observe(out, now, rows_fn, alive)
        t = mem.setdefault('targets', {}).setdefault(o['name'], {})
        verdict, detail = classify(o)
        if 'seen' not in t:
            t['seen'] = True
            # History is not news: a parent that was already terminal, or whose driver died >6 h ago, when the
            # supervisor first looked is baselined silently (never auto-resumed, never alarmed).
            if verdict != 'healthy' and ((o['state'] or {}).get('state') in TERMINAL
                                         or (o['state_age'] or 0) > 6 * 3600):
                t['last'], t['baseline'] = verdict, True
                continue
        if t.get('baseline'):
            continue
        if verdict == 'healthy' and (o['state'] or {}).get('state') in ('RUNNING', 'READY'):
            t['seen_running'] = True
        action = decide(verdict, o, t, now)
        sess = o['receipt'].get('session', '')[:8]
        key = f"{o['name']}:{sess}:{verdict}:{o['resumes']}"
        if verdict == 'healthy':
            for k in [k for k in mem.get('sent', {}) if k.removeprefix('ask:').startswith(o['name'] + ':')
                      and ':finished:' not in k]:
                mem['sent'].pop(k, None)            # recovered: a later failure of the same kind alarms (and asks) again
        elif verdict in MSG:
            text = MSG[verdict].format(n=o['name'], d=detail)
            if verdict == 'role_dead' and action is None:
                notify(key + ':seen', text + ' Επιβεβαίωση σε ~2 λεπτά· αν είναι πραγματική διακοπή, θα γίνει αυτόματη συνέχιση.')
            elif action == 'resume':
                if dry:
                    log.append(('would-resume', o['name'], detail))
                else:
                    t['resume_attempts'] = t.get('resume_attempts', 0) + 1
                    atomic(mem_path, mem)                       # counter is durable BEFORE the effect
                    try:
                        ok, msg = resumer(o['out'], o['receipt']['request'])
                    except Exception as ex:                      # noqa: BLE001 - e.g. TimeoutExpired: count as failed
                        ok, msg = False, type(ex).__name__ + ': ' + str(ex)[:150]
                    log.append(('resume', o['name'], ok, msg))
                    t.pop('suspect_since', None)
                    if not ok:
                        t['resume_failed'] = True
                    notify(key + f":r{t['resume_attempts']}",
                           text + (' Αυτόματη συνέχιση (ίδιο εγκεκριμένο spec, ίδιο session): ΕΠΙΤΥΧΗΣ.' if ok else
                                   f' Αυτόματη συνέχιση ΑΠΕΤΥΧΕ: {msg}'),
                           None if ok else (f'Supervisor: αποτυχία resume {o["name"]}', text + '\n\n' + msg +
                                            '\n\nΔεν γίνεται άλλη αυτόματη ενέργεια. Χρειάζεται κρίση.'))
            elif action == 'ask':
                reason = ' Ξεπεράστηκαν οι αυτόματες συνεχίσεις.' if verdict == 'role_dead' else ''
                notify(key, text + reason + ' Δεν γίνεται αυτόματη ενέργεια· χρειάζεται δική σου απόφαση.',
                       (f'Supervisor: {o["name"]} — {verdict}', text + reason + '\n\nΔεν έγινε καμία αυτόματη ενέργεια '
                        '(κρίση: αλλαγή spec, cap, test split ή επαναλαμβανόμενη αποτυχία). Επιλογή: απάντησε τι να γίνει.'))
            elif verdict == 'finished':
                notify(key, text)
        t['last'] = verdict

    for unit in services:
        st = unit_fn(unit)
        hist = mem.setdefault('restarts', {}).setdefault(unit, [])
        if st == 'unobservable':
            notify('svc-unobservable', 'Ο supervisor δεν βλέπει το systemd user bus· δεν ελέγχονται οι υπηρεσίες.')
            continue
        act = service_action(unit, st, hist, now)
        if act == 'restart':
            if dry:
                log.append(('would-restart', unit))
            else:
                hist.append(now)
                atomic(mem_path, mem)               # the bound is durable BEFORE the effect
                try:
                    ok = restarter(unit)
                except Exception:                    # noqa: BLE001
                    ok = False
                notify(f'svc:{unit}:{len(hist)}:{int(now)}', f'Η υπηρεσία {unit} ήταν {st}· αυτόματη επανεκκίνηση: ' +
                       ('ΕΠΙΤΥΧΗΣ.' if ok else 'ΑΠΕΤΥΧΕ.'))
        elif act == 'ask':
            notify(f'svc-ask:{unit}', f'Η υπηρεσία {unit} είναι {st} και έχει ήδη επανεκκινηθεί {MAX_SERVICE_RESTARTS} φορές σε 6 ώρες.',
                   (f'Supervisor: {unit} πέφτει επαναλαμβανόμενα', 'Δεν γίνεται άλλη αυτόματη επανεκκίνηση.'))

    try:
        age = now - Path(beat_path).stat().st_mtime
        if age > DISPATCHER_BEAT_MAX and unit_fn('qrl-dispatcher.service') == 'active':
            notify('beat-stale', f'Ο dispatcher είναι active αλλά το heartbeat δεν ανανεώνεται εδώ και {age / 60:.0f} λεπτά.')
        elif age <= DISPATCHER_BEAT_MAX:
            mem.get('sent', {}).pop('beat-stale', None)
    except OSError:
        pass

    for line in journal(mem, now=now):
        notify('job:' + line[:80], 'Αποτυχημένο job του dispatcher: ' + line)

    if not dry:
        atomic(mem_path, mem)
    return log


def install_cmd():
    return ['systemd-run', '--user', '--unit=qrl-supervisor', '--property=KillMode=process', '--property=CPUAffinity=4-7',
            '--service-type=exec', f'--working-directory={ROOT}', '--timer-property=AccuracySec=1s',
            '--on-active=1s', '--on-unit-active=2min', str(ROOT / '.venv/bin/python'), str(ROOT / 'tools/supervisor.py')]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cmd', nargs='?', choices=['check', 'install'], default='check')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    if a.cmd == 'install':
        print(shlex.join(install_cmd()))
        return
    SUP.mkdir(parents=True, exist_ok=True)
    with (SUP / 'supervisor.lock').open('a') as h:
        try:
            fcntl.flock(h, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return
        for entry in tick(dry=a.dry_run):
            print(json.dumps(entry, ensure_ascii=False))


if __name__ == '__main__':
    main()
