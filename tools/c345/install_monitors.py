#!/usr/bin/env python3
"""Print host setup commands; --install creates only the two requested transient user timers."""
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
import shlex
import subprocess
try:
    from . import monitor_common as C
except ImportError:
    import monitor_common as C


def commands(started):
    # Round upward so a fractional receipt timestamp cannot skip the first due slot.
    start = datetime.fromisoformat(started).astimezone(timezone.utc)
    if start.microsecond:
        start = (start + timedelta(seconds=1)).replace(microsecond=0)
    hours = ','.join(f'{h:02d}' for h in sorted((start.hour + n * 6) % 24 for n in range(4)))
    calendar = f'*-*-* {hours}:{start.minute:02d}:{start.second:02d} UTC'
    shared = ['systemd-run', '--user', '--property=KillMode=process', '--property=CPUAffinity=4-7',
              '--property=Restart=on-failure', '--property=RestartSec=120', '--service-type=exec',
              f'--working-directory={C.ROOT}', '--timer-property=AccuracySec=1s']
    python = str(C.ROOT / '.venv/bin/python')
    return [shared + ['--unit=qrl-c345-alert', '--on-active=1s', '--on-unit-active=2min', python,
                      str(C.ROOT / 'tools/c345/watch_alert.py')],
            shared + ['--unit=qrl-c345-progress', '--on-calendar=' + calendar,
                      '--timer-property=Persistent=true', python,
                      str(C.ROOT / 'tools/c345/progress_report.py'), '--due']]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install', action='store_true')
    args = parser.parse_args()
    cmds = commands(C.read(C.OUT / 'receipt.json')['started'])
    for cmd in cmds:
        print(shlex.join(cmd), flush=True)
    if args.install:
        if Path('/proc/1/comm').read_text().strip() != 'systemd':
            raise SystemExit('Host PID namespace required; no timers installed.')
        # Check both names before any mutation, to avoid creating duplicate monitoring services.
        for name in ('qrl-c345-alert.timer', 'qrl-c345-progress.timer'):
            p = subprocess.run(['systemctl', '--user', 'show', name, '--property=LoadState', '--value'],
                               check=True, capture_output=True, text=True)
            if p.stdout.strip() != 'not-found':
                raise SystemExit('Already exists: ' + name + '; inspect it instead of installing twice.')
        for cmd in cmds:
            subprocess.run(cmd, check=True)
        subprocess.run([str(C.ROOT / '.venv/bin/python'), str(C.ROOT / 'tools/c345/watch_alert.py')], check=True)


if __name__ == '__main__':
    main()
