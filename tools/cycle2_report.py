"""Read-only cycle-2 dashboard data. Never evaluates a model or reads test splits."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import sqlite3
from statistics import mean

PARENT = 'R-20261029-006'
AMENDMENT = '.lab/specs/R-20261029-010.json'
ARMS = {
    'lstm': 'LSTM', 'lstm_transfer': 'LSTM+transfer', 'dinos': 'Dinos',
    'v2': 'Dinos+Transfer V.2', 'derp': 'DERP',
    'derp_hist10': 'Enhanced DERP',
    'rppo': 'DRe-SCale LSTM-PPO — προσαρμοσμένο μοντέλο του paper',
    'hpa_original': 'HPA αρχικό', 'hpa': 'HPA-demand',
    'fixed_best': 'fixed_best (αναφορά)', 'oracle_Dstep': 'oracle_Dstep (ευριστικός)',
}
NAME = re.compile(r'.+-(smoke|calib|screen)-(.+)-c(\d+)-s(\d+)$')
LANES = ('code-poisson', 'code-poisson-astra')


def _json(path):
    return json.loads(Path(path).read_text())


def _inside(root, path):
    path = path.resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Διαδρομή εκτός qrl-lab')
    return path


def _result(root, run):
    cmd = json.loads(run['cmd']) if isinstance(run['cmd'], str) else run['cmd']
    out = _inside(root, Path(run['cwd']) / cmd[cmd.index('--out') + 1])
    x = _json(out)
    if x.get('eval_splits') != ['val']:
        raise ValueError('Απαιτείται αποκλειστικά val')
    checkpoints = x['checkpoint_results']
    # Final checkpoint only; never select a best validation score for this display.
    ck = checkpoints[str(max(map(int, checkpoints)))]
    if 'val' not in ck or any(k.startswith('test') or 'shift' in k for k in ck):
        raise ValueError('Μη αναμενόμενα splits')
    episodes = ck['val']['episodes']
    if len(episodes) != 20:
        raise ValueError('Αναμένονται 20 val traces')
    result = {'source': str(out.relative_to(root.resolve())), 'ticks': x['total_ticks']}
    if int(x['seed']) != int(NAME.fullmatch(run['name'].rsplit('/', 1)[-1]).group(4)):
        raise ValueError('Ασυμφωνία training seed')
    for key in ('ret', 'mean_pods', 'slo_viol_rate', 'p95_latency', 'pods_changes'):
        values = [float(ep[key]) for ep in episodes]
        if not all(math.isfinite(v) for v in values):
            raise ValueError('Μη πεπερασμένη μετρική')
        result[key] = mean(values)
    return result


def snapshot(root, *, _connect=sqlite3.connect):
    """Snapshot of launcher state + validated completed JSON. Missing data stays None."""
    root = Path(root).resolve()
    result = {'updated': datetime.now(timezone.utc).isoformat(timespec='seconds'),
              'rows': [], 'stages': [], 'issues': []}
    planned = {}
    try:
        spec = _json(root / AMENDMENT)
        for lane, waves in spec['review']['screen_waves'].items():
            for wave in waves:
                for entry in wave['entries']:
                    planned[(lane, entry['name'])] = dict(entry, cwd=str(root / lane))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result['issues'].append(f'Frozen screen manifest: {exc}')
    try:
        with _connect(f'file:{root}/.lab/lab.db?mode=ro', uri=True, timeout=2) as c:
            c.row_factory = sqlite3.Row
            runs = [dict(r) for r in c.execute(
                'SELECT * FROM runs WHERE request_id=? ORDER BY created, run_id', (PARENT,))]
    except sqlite3.Error as exc:
        result['issues'].append(f'Launcher DB: {exc}')
        runs = []
    # At most one current attempt per lane/name; do not double-count retries.
    current = {(Path(r['cwd']).name, r['name'].rsplit('/', 1)[-1]): r for r in runs}
    for lane, name in sorted(set(planned) | set(current)):
        m = NAME.fullmatch(name)
        if not m:
            continue
        stage, arm, candidate, seed = m.groups()
        run = current.get((lane, name))
        row = dict(lane=lane, name=name, stage=stage, arm=arm, candidate=int(candidate),
                   seed=int(seed), status=run['status'] if run else 'pending',
                   run_id=run['run_id'] if run else '', source='', ret=None)
        if run and run['status'] == 'done' and run['exit_code'] == 0:
            try:
                row.update(_result(root, run))
                row['valid'] = True
            except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
                row['valid'] = False
                result['issues'].append(f"{run['run_id']}: {exc}")
        else:
            row['valid'] = False
        result['rows'].append(row)
    for stage in ('smoke', 'calib', 'screen'):
        rows = [r for r in result['rows'] if r['stage'] == stage]
        statuses = Counter(r['status'] for r in rows)
        result['stages'].append(dict(stage=stage, planned=len(rows), valid=sum(r['valid'] for r in rows),
                                    statuses=dict(statuses)))
    return result


def grouped(data, stage):
    """Keep candidates, lanes and stages separate; traces are not training seeds."""
    groups = defaultdict(list)
    for row in data['rows']:
        if row['stage'] == stage:
            groups[(row['lane'], row['arm'], row['candidate'])].append(row)
    output = []
    for lane in LANES:
        arms = list(ARMS) + sorted({a for l, a, _ in groups if l == lane} - set(ARMS))
        for arm in arms:
            candidates = sorted(c for l, a, c in groups if l == lane and a == arm)
            for candidate in candidates or [None]:
                rows = groups.get((lane, arm, candidate), [])
                valid = [r for r in rows if r['valid']]
                d = {'Κλάδος': lane, 'Μοντέλο': ARMS.get(arm, arm),
                     'Υποψήφιος': f'c{candidate}' if candidate is not None else '—',
                     'Έγκυρα / προβλεπόμενα': f'{len(valid)} / {len(rows)}' if rows else 'άγνωστο',
                     'Training seeds': ', '.join(str(r['seed']) for r in valid) or '—',
                     'Συνολικά training ticks': ', '.join(str(t) for t in sorted({r['ticks'] for r in valid})) or '—',
                     'Κατάσταση': ', '.join(f'{k}: {v}' for k, v in sorted(Counter(r['status'] for r in rows).items())) if rows else 'Αναμονή · άγνωστο αποτέλεσμα'}
                for key, label in [('ret', 'Val return'), ('mean_pods', 'Μέσα pods'),
                                   ('slo_viol_rate', 'SLO παραβιάσεις (0–1)'),
                                   ('p95_latency', 'Μέση p95 ανά trace'), ('pods_changes', 'Αλλαγές pods')]:
                    d[label] = mean(r[key] for r in valid) if valid else None
                output.append(d)
    return output


def render(st, data):
    st.subheader('Κύκλος 2 · Νέο φορτίο Poisson')
    st.caption(f"Ενημέρωση UTC: {data['updated']} · πηγή launcher {PARENT} και {AMENDMENT} · ανανέωση κάθε 30 s")
    st.info('Προκαταρκτικά δεδομένα validation. Smoke και calibration είναι διαγνωστικά. '
            'Τα λίγα training seeds του screen δεν τεκμηριώνουν νικητή. test12 και shift-test παραμένουν κλειστά.')
    for col, stage in zip(st.columns(3), data['stages']):
        label = {'smoke': 'Smoke · έλεγχος λειτουργίας', 'calib': 'Calibration · διαγνωστικά', 'screen': 'Screen · προκαταρκτικό val'}[stage['stage']]
        col.metric(label, f"{stage['valid']} / {stage['planned']}" if stage['planned'] else 'άγνωστο')
        col.caption('Έγκυρα JSON / προβλεπόμενες εκτελέσεις · ' + str(stage['statuses']))
    st.markdown('**DRe-SCale LSTM-PPO — προσαρμοσμένο μοντέλο του paper** (`rppo`)')
    st.caption('Κοινό περιβάλλον Poisson, observations/actions/reward και val traces· native recurrent PPO, '
               'όχι τεκμηριωμένη ισοδυναμία με sb3_contrib. Πηγές: docs/cycle2_plan.md §3, '
               'code-poisson/tuning/rppo.py, .lab/j104/static-rppo.md. Η αιτία των calibration diagnostics παραμένει άγνωστη.')
    st.markdown('**Screening · ανά κλάδο, μοντέλο και υποψήφιο**')
    st.dataframe(grouped(data, 'screen'), hide_index=True, width='stretch')
    st.caption('Μετρικές: μέσος των 20 val traces ανά training seed και μετά μέσος των διαθέσιμων seeds. '
               'Checkpoint: τελευταίο αποθηκευμένο. Εκκρεμή seeds δεν συμμετέχουν στον μέσο. '
               'Σύγκριση προϋποθέτει ίδιο training budget· τα ticks φαίνονται στις πηγές ανά seed. '
               'Ο oracle_Dstep είναι ευριστικός, όχι βέλτιστο άνω όριο.')
    for stage, title in [('calib', 'Calibration · διαγνωστικά ανά μοντέλο'), ('smoke', 'Smoke · διαγνωστικά ανά μοντέλο')]:
        with st.expander(title):
            st.dataframe(grouped(data, stage), hide_index=True, width='stretch')
    with st.expander('Πηγές και μετρήσεις ανά training seed'):
        st.dataframe(data['rows'], hide_index=True, width='stretch')
        st.caption('Συμπληρωματική ελεγμένη ανάλυση: .lab/j132/result.md · .lab/j132/review.md · .lab/j92/calib_result.md')
    for issue in data['issues']:
        st.warning(issue)
