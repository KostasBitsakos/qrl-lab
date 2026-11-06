#!/usr/bin/env python3
"""One independent stop check. systemd timer calls this every two minutes; no LLM loop."""
import argparse
import json
import time
try:
    from . import monitor_common as C
except ImportError:
    import monitor_common as C


def evaluate(s, previous, stall_seconds=900):
    """No-new-task alarm only when idle: legitimate long training is not a stall."""
    now, state = s['now'], s['state']
    fingerprint = json.dumps([(r['run_id'], r['status'], r['ended']) for r in s['rows']], sort_keys=True)
    changed = fingerprint != previous.get('fingerprint')
    last_change = now if changed else previous.get('last_change', now)
    record = dict(previous, fingerprint=fingerprint, last_change=last_change, checked_at=C.stamp(now))
    if not s.get('host_namespace', True):
        key, text = 'observation_error', 'Ο έλεγχος εκτελείται σε απομονωμένο PID namespace· απαιτείται εκτέλεση από τον host.'
    elif state['state'] == 'DONE':
        if (s['counts']['running'] or s['counts']['done'] != len(s['spec']['tasks'])
                or s['counts'].get('verifying', 0) or state.get('errors')):
            key, text = 'inconsistent_done', 'Το state γράφει DONE αλλά τα runs δεν επιβεβαιώνουν πλήρη ολοκλήρωση.'
        else:
            key, text = 'done', 'Το W ολοκληρώθηκε κανονικά.'
    elif state['state'] != 'RUNNING':
        key, text = 'stopped', f"Το W σταμάτησε ή διακόπτεται: {state['state']}. Αιτία: {state.get('reason', 'άγνωστη')}."
    elif not all(s['identities'].values()):
        key, text = 'process_dead', 'Δεν επιβεβαιώνεται ζωντανός driver ή watcher: ' + str(s['identities']) + '.'
    elif any(age > 180 for age in s['heartbeats'].values()):
        key, text = 'heartbeat_stale', 'Δεν ανανεώνεται το heartbeat του driver ή του watcher για πάνω από 3 λεπτά.'
    elif s['dead_runs']:
        key, text = 'run_dead', 'Ενεργό run χωρίς τη δηλωμένη διεργασία εκτέλεσης: ' + ', '.join(s['dead_runs']) + '.'
    elif any(r['run_id'] not in '\n'.join(s['launcher']) for r in s['rows']):
        key, text = 'launcher_mismatch', 'Η λίστα του launcher δεν συμφωνεί με τη βάση· η πρόοδος δεν επιβεβαιώνεται.'
    elif not s['counts']['running'] and s['counts']['queued'] and now - last_change >= stall_seconds:
        key, text = 'stalled', f'Καμία ενεργή εργασία και καμία αλλαγή εργασιών για {stall_seconds // 60} λεπτά.'
    elif s['counts']['failed'] > 0:
        key, text = 'task_failed_' + str(s['counts']['failed']), 'Απέτυχε ή σταμάτησε εργασία του W· το συνολικό στάδιο παραμένει ενεργό.'
    else:
        key, text = 'healthy', ''
    record['failed_count'] = s['counts']['failed']
    return key, text, record


def deliver(key, text, record, previous, sender=C.post):
    """Persist only successful delivery; a failed post retries next poll."""
    previous_key = previous.get('delivered')
    if key == previous_key or (key == 'healthy' and previous_key in (None, 'healthy')):
        return record
    if key == 'healthy':
        text = 'Ο ανεξάρτητος έλεγχος επιβεβαιώνει ξανά ενεργό W μετά τον προηγούμενο συναγερμό.'
    body = ('Κώστα,\n\n' + text + '\nΈλεγχος: ' + record['checked_at'] +
            '\nΠηγή: .lab/c345run/state.json, receipt.json, lab.db και launch_run.py list. '
            'Ο έλεγχος ειδοποιεί· δεν επανεκκινεί πειράματα.\n\n— Πάρις')
    record['message_id'] = sender(body)
    record['delivered'] = key
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    with C.locked('alert'):
        path = C.MONITOR / 'alert-state.json'
        previous = C.read(path) if path.exists() else {}
        try:
            s = C.snapshot()
            key, text, record = evaluate(s, previous)
        except Exception as ex:
            key, text = 'observation_error', 'Ο ανεξάρτητος έλεγχος δεν μπορεί να επιβεβαιώσει την κατάσταση του W: ' + type(ex).__name__
            record = dict(previous, checked_at=C.stamp())
        if args.dry_run:
            print(json.dumps(dict(key=key, detail=text, record=record), ensure_ascii=False, indent=2))
        else:
            C.atomic(path, deliver(key, text, record, previous))


if __name__ == '__main__':
    main()
