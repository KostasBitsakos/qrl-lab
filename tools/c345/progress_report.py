#!/usr/bin/env python3
"""C345 factual six-hour report. Default preview; --post publishes on demand, --due on schedule."""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import statistics
import time
try:
    from . import monitor_common as C
except ImportError:
    import monitor_common as C

PERIOD = 6 * 3600


def metrics(s, root=C.ROOT):
    groups = defaultdict(list)
    errors = []
    spec, checked = s['spec'], s['state'].get('checked', {})
    for task in spec['tasks']:
        row = s['task_rows'].get(task['name'])
        if not row or row['status'] != 'done' or row['exit_code'] != 0 or checked.get(task['name']) != 'ok':
            continue
        try:
            artifact = C.read(root / task['child']['cwd'] / task['out'])
            if task['stage'] == 'P0':
                if artifact['split'] != 'val' or artifact['seeds'] != spec['policy']['val_seeds'] or artifact['variant'] != spec['policy']['variant']:
                    raise ValueError('reference provenance')
                items = [(f"{arm}/{config}", None, value['episodes'])
                         for arm, configs in artifact['grids'].items() if arm in ('hpa_orig', 'hpa_demand')
                         for config, value in configs.items()]
            else:
                if (artifact['seed'] != task['seed'] or artifact['eval_splits'] != ['val']
                        or artifact['eval_seeds'] != {'val': spec['policy']['val_seeds']}
                        or artifact.get('target_variant', artifact.get('variant')) != spec['policy']['variant']):
                    raise ValueError('training provenance')
                items = [(f"{task['arm']}/{task['lane']}/{task['config']}", task['seed'],
                          artifact['checkpoint_results'][str(task['target_ticks'])]['val']['episodes'])]
            parsed = []
            for name, seed, episodes in items:
                if len(episodes) != len(spec['policy']['val_seeds']) or not all(
                        C.finite(e.get(k)) for e in episodes for k in ('ret', 'slo_viol_rate')):
                    raise ValueError('nonfinite/incomplete metrics')
                parsed.append((name, dict(seed=seed, ret=statistics.mean(e['ret'] for e in episodes),
                                           slo=statistics.mean(e['slo_viol_rate'] for e in episodes))))
            for name, value in parsed:
                groups[name].append(value)
        except (OSError, KeyError, TypeError, ValueError):
            errors.append(task['name'])
    lines = []
    for name, values in sorted(groups.items()):
        seeds = sorted({v['seed'] for v in values if v['seed'] is not None})
        label = f"n={len(seeds)} training seeds ({','.join(map(str, seeds))})" if seeds else 'reference, χωρίς training seeds'
        lines.append(f"- {name}: μέση επιστροφή={statistics.mean(v['ret'] for v in values):.3f}, "
                     f"SLO violation rate={statistics.mean(v['slo'] for v in values):.6f}, {label}.")
    return lines, errors


def eta(s):
    # Nominal costs are historical. Calibrate them only with completed learning tasks.
    ratios = []
    tasks = s['spec']['tasks']
    for task in tasks:
        row = s['task_rows'].get(task['name'])
        if task['stage'] != 'P0' and row and row['status'] == 'done' and row['exit_code'] == 0 and row['started'] and row['ended']:
            duration = C.epoch(row['ended']) - C.epoch(row['started'])
            ratios.append(duration / (task['nominal_cpu_h'] * 3600))
    if s['state']['state'] == 'DONE':
        return 'ολοκληρώθηκε'
    if s['state']['state'] != 'RUNNING' or not ratios:
        return 'άγνωστο — δεν υπάρχουν ακόμη επαρκείς ολοκληρωμένες μετρήσεις εκπαίδευσης'
    remaining = 0
    longest = 0
    scale = statistics.median(ratios)
    for task in tasks:
        row = s['task_rows'].get(task['name'])
        if row and row['status'] not in C.ACTIVE:
            continue
        elapsed = s['now'] - C.epoch(row['started']) if row and row['started'] else 0
        estimate = max(0, task['nominal_cpu_h'] * 3600 * scale - elapsed)
        remaining += estimate
        longest = max(longest, estimate)
    hours = max(longest, remaining / s['spec']['sandbox']['max_parallel']) / 3600
    return f'περίπου {hours:.1f} ώρες ακόμη (πρόχειρη προβολή από {len(ratios)} runs· όχι εγγύηση)'


def changes(previous, root=C.ROOT, started=None):
    head = C.command(['git', 'rev-parse', 'HEAD'], cwd=root)
    since = previous.get('head')
    history = C.command(['git', 'log', '--max-count=6', '--format=%h %s',
                         f'{since}..HEAD' if since else '--since=' + (started or C.read(C.OUT / 'receipt.json')['started'])], cwd=root)
    text = (root / 'docs/EXPERIMENTS.md').read_text()
    digest = hashlib.sha256(text.encode()).hexdigest()
    relevant = [line for line in text.splitlines() if 'C345' in line or 'R-20261106-006' in line or 'J377' in line]
    lines = ['Υλοποίηση/καταγραφές από την προηγούμενη αναφορά:']
    lines.append(history if history else 'Δεν υπάρχουν νέα commits.')
    if digest != previous.get('experiments_hash'):
        lines += ['EXPERIMENTS.md (πρόσφατες καταγραφές W· η τρέχουσα κατάσταση δίνεται παραπάνω):', *relevant[-3:]]
    else:
        lines.append('Η καταγραφή EXPERIMENTS.md δεν άλλαξε.')
    lines.append('Οι μη καταγεγραμμένες αλλαγές κώδικα δεν πιστοποιούνται από το git log.')
    return '\n'.join(lines), dict(head=head, experiments_hash=digest)


def render(s, change_text, root=C.ROOT):
    c = s['counts']
    charged = 'άγνωστη' if s['charged_cpu_h'] is None else f"{s['charged_cpu_h']:.2f}"
    cap = s['spec']['sandbox']['cpu_hours_budget']
    reserved = s['state'].get('used_cpu_h')
    budget = f'{reserved:.2f}' if C.finite(reserved) else 'άγνωστο'
    lines = ['Κώστα,', '', f"Αναφορά W — {C.stamp(s['now'])} · κατάσταση {s['state']['state']}/{s['state'].get('stage', '?')}.",
             f"Εργασίες: {c['done']} ολοκληρωμένες, {c['running']} ενεργές, {c['queued']} σε αναμονή, "
             f"{c['failed']} αποτυχημένες/σταματημένες, σύνολο {len(s['spec']['tasks'])}. "
             f"Από τις ολοκληρωμένες, {c['verifying']} περιμένουν έλεγχο ακεραιότητας.",
             f'Χρέωση χρόνου × cores έως τώρα: {charged} CPU-h / όριο {cap:.2f}. '
             f'Λογιστικό σύνολο driver (χρέωση τελειωμένων + πλήρης κράτηση ενεργών): {budget} CPU-h.',
             'ETA: ' + eta(s) + '.', '', change_text, '',
             'Αποτελέσματα: val/screening, χωρίς ισχυρισμό υπεροχής. Μέσος όρος ανά run στα κοινά val traces, '
             'έπειτα ανά training seed· κάθε config χωριστά, χωρίς επιλογή νικητή.']
    data, errors = metrics(s, root)
    lines += data or ['Δεν υπάρχουν ακόμη επαληθευμένα ολοκληρωμένα runs με αριθμούς μοντέλων.']
    if errors:
        lines.append('Μη αναγνώσιμα ή ασύμβατα artifacts, παραλείφθηκαν: ' + ', '.join(errors))
    lines += ['', 'Πηγές: .lab/c345run/{state,parent-spec,receipt}.json, lab.db/R-20261106-006, '
              'code-poisson-c345/tuning/results/c345/*.json, git log, docs/EXPERIMENTS.md.', '', '— Πάρις']
    return '\n'.join(lines)


def due_slot(started, now):
    return max(0, int((now - C.epoch(started)) // PERIOD))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--post', action='store_true')
    group.add_argument('--due', action='store_true')
    args = parser.parse_args()
    with C.locked('progress'):
        path = C.MONITOR / 'progress-state.json'
        previous = C.read(path) if path.exists() else {}
        now = time.time()
        receipt = C.read(C.OUT / 'receipt.json')
        slot = due_slot(receipt['started'], now)
        if args.due and (slot < 1 or slot <= previous.get('slot', 0)):
            return
        try:
            s = C.snapshot(now)
            terminal = s['state']['state'] in ('DONE', 'STOPPED', 'INCOMPLETE')
            if args.due and terminal and previous.get('terminal_state') == s['state']['state']:
                return
            change_text, record = changes(previous, started=receipt['started'])
            record['terminal_state'] = s['state']['state'] if terminal else None
            body = render(s, change_text)
        except Exception as ex:
            # A failed observation must not silently swallow a scheduled report.
            record = {}
            body = f'Κώστα,\n\nΗ προγραμματισμένη αναφορά W δεν μπόρεσε να διαβάσει επαληθευμένα στοιχεία ({type(ex).__name__}). Η πρόοδος και τα νούμερα είναι άγνωστα.\n\n— Πάρις'
        if args.post or args.due:
            mid = C.post(body)
            C.atomic(path, dict(previous, **record, slot=slot, posted_at=C.stamp(now), message_id=mid))
            print(mid)
        else:
            print(body)


if __name__ == '__main__':
    main()
