"""Read-only C345 observations. No launches, experiment writes, or credential access."""
import fcntl
import json
import math
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / '.lab/c345run'
MONITOR = ROOT / '.lab/j377'
THREAD = 'M-20261102-040'
ACTIVE = ('starting', 'running')


def read(path):
    return json.loads(Path(path).read_text())


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    os.replace(tmp, path)


def epoch(value):
    return datetime.fromisoformat(value).timestamp()


def stamp(now=None):
    return datetime.fromtimestamp(time.time() if now is None else now, timezone.utc).isoformat(timespec='seconds')


@contextmanager
def locked(name):
    MONITOR.mkdir(parents=True, exist_ok=True)
    with (MONITOR / (name + '.lock')).open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def command(args, cwd=ROOT):
    return subprocess.run(args, cwd=cwd, check=True, text=True, capture_output=True, timeout=45).stdout.strip()


def post(body):
    # The only outbound channel currently implemented by labq is the lab thread.
    return command([sys.executable, str(ROOT / 'tools/labq.py'), 'post', '--reply-to', THREAD,
                    '--author', 'coordinator', '--model', 'script (χωρίς LLM)', '--kind', 'status', '--body', body])


def identity(pid, role=None, session=None, proc=Path('/proc'), expected=None):
    """Reject zombies and reused PIDs; role/session bind driver/watch to the receipt."""
    try:
        path = proc / str(int(pid))
        state = (path / 'stat').read_text().rsplit(')', 1)[1].split()[0]
        if state in ('Z', 'X'):
            return False
        args = (path / 'cmdline').read_bytes().decode().split('\0')
        if role is not None:
            return (any(a.endswith('c345/driver.py') for a in args) and role in args
                    and '--session' in args and args[args.index('--session') + 1] == session)
        if expected is not None:
            # runs.pid is the PAYLOAD pid (launch_run.supervise), not its supervisor.
            return [a for a in args if a] == expected
        return True
    except (OSError, ValueError, IndexError, TypeError):
        return False


def snapshot(now=None, out=OUT, root=ROOT):
    now = time.time() if now is None else now
    spec, state, receipt = (read(out / p) for p in ('parent-spec.json', 'state.json', 'receipt.json'))
    with sqlite3.connect(f'file:{root}/.lab/lab.db?mode=ro', uri=True, timeout=10) as db:
        db.row_factory = sqlite3.Row
        rows = [dict(r) for r in db.execute('SELECT * FROM runs WHERE request_id=?', (receipt['request'],))]
    # Cross-check the public launcher view without depending on its human display for accounting.
    listing = command([sys.executable, str(root / 'tools/launch_run.py'), 'list'], cwd=root)
    selected = [line for line in listing.splitlines() if receipt['request'] in line]
    task_rows = {}
    for row in rows:
        name = row['name'].split('/')[0]
        if name in task_rows:
            raise ValueError('duplicate task attempts: ' + name)
        task_rows[name] = row
    identities = {role: identity(receipt['pids'].get(role), cli, receipt['session'])
                  for role, cli in [('drive', 'drive'), ('watch', 'watch')]}
    heartbeats = {'drive': now - epoch(state['ts']),
                  'watch': now - epoch(read(out / 'watch-ready.json')['ts'])}
    counts = dict(done=0, running=0, queued=0, failed=0, verifying=0)
    charged = 0.0
    unknown = False
    for task in spec['tasks']:
        row = task_rows.get(task['name'])
        if row is None:
            counts['queued'] += 1
            continue
        if row['status'] in ACTIVE:
            counts['running'] += 1
        elif row['status'] == 'done' and row['exit_code'] == 0:
            counts['done'] += 1
            if state.get('checked', {}).get(task['name']) != 'ok':
                counts['verifying'] += 1
        else:
            counts['failed'] += 1
        if row.get('started'):
            entry = read(Path(row['run_dir']) / 'spec_entry.json')
            cpus = entry['sandbox']['cpus']
            charged += max(0, (epoch(row['ended']) if row.get('ended') else now) - epoch(row['started'])) * cpus / 3600
        else:
            unknown = True
    return dict(now=now, spec=spec, state=state, receipt=receipt, rows=rows, task_rows=task_rows,
                host_namespace=Path('/proc/1/comm').read_text().strip() == 'systemd',
                identities=identities, heartbeats=heartbeats, counts=counts,
                charged_cpu_h=None if unknown else charged, launcher=selected,
                dead_runs=[r['run_id'] for r in rows if r['status'] == 'running'
                           and not identity(r['pid'], expected=json.loads(r['cmd']))])


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
