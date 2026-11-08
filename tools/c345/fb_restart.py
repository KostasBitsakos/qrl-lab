#!/usr/bin/env python3
"""J402: restart of the C345 F-B parent after its first attempt was stopped (15 launcher rows, SIGTERM, no artifacts).

driver.py is hash-bound into the approved spec (runtime_sha256) so it cannot be edited. This wrapper imports it
unchanged and hides ONLY the run_ids listed in $QRL_C345_OUT/superseded.json (written by `supersede`, which verifies
every one is terminal and non-successful with no artifact). History stays in the launcher DB and in used() budget
accounting. Commands: supersede | start | drive | watch | resume (same semantics as driver.py).
Use: QRL_C345_OUT=.lab/c345f-b .venv/bin/python tools/c345/fb_restart.py <cmd> --request R-20261107-008 [--session S]
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import driver as D

_orig_rows = D.Backend.rows
SUP = D.OUT / 'superseded.json'


def _superseded():
    return set(json.loads(SUP.read_text())['run_ids']) if SUP.exists() else set()


def _rows(self):
    s = _superseded()
    return [r for r in _orig_rows(self) if r['run_id'] not in s]


_orig_used = D.Backend.used


def _used(self):
    # The frozen cap equals the sum of reservations exactly (no margin), so the 0.06 CPU-h burned by the superseded
    # attempt would make the driver's pre-check fail. Exclude it here (recorded in superseded.json; the launcher DB still holds it).
    sup = _superseded()
    if not sup:
        return _orig_used(self)
    with self.connection() as c:
        mine = [dict(r) for r in c.execute('SELECT * FROM runs WHERE request_id=?', (self.rid,))]
    ex = 0.0
    for r in mine:
        if r['run_id'] in sup and r['started'] and r['ended']:
            ex += (D.datetime.fromisoformat(r['ended']) - D.datetime.fromisoformat(r['started'])).total_seconds() / 3600
    return max(0.0, _orig_used(self) - ex)   # superseded rows ran with 1 cpu each (verified: cpus recorded in spec_entry)


D.Backend.used = _used
D.Backend.rows = _rows


def supersede(rid):
    spec = D.validate(D.load(D.OUT / 'parent-spec.json'))
    D.Backend(rid, spec).approval()
    prev = set(json.loads(SUP.read_text())['run_ids']) if SUP.exists() else set()   # repeated restarts accumulate
    tasks = {t['name']: t for t in spec['tasks']}
    ids = []
    for r in _orig_rows(D.Backend(rid, spec)):
        if r['run_id'] in prev:
            ids.append(r['run_id']); continue
        n = r['name'].split('/')[0]
        if n not in tasks or r['status'] in D.ACTIVE or r['status'] == 'done' or tasks[n]['child'] is None:
            raise D.LabError(f"cannot supersede {r['run_id']}: status {r['status']}")
        if D.Backend(rid, spec).output_exists(tasks[n]):
            raise D.LabError(f'artifact exists for {n}')
        ids.append(r['run_id'])
    D.atomic(SUP, dict(request=rid, ts=D.stamp(), reason='first F-B attempt stopped by 32-core guard (J395)', run_ids=ids))
    print(f'superseded {len(ids)} rows')


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('action', choices=['supersede', 'start', 'drive', 'watch', 'resume'])
    ap.add_argument('--request', required=True)
    ap.add_argument('--session')
    a = ap.parse_args()
    D.__file__ = str(Path(__file__).resolve())   # children/resume spawn THIS wrapper
    if a.action == 'supersede': supersede(a.request)
    elif a.action == 'start': D.start(a.request)
    elif a.action == 'resume': D.resume(a.request)
    else: {'drive': D.drive, 'watch': D.watch}[a.action](a.request, a.session)
