#!/usr/bin/env python3
"""J419: script-only. Wait for approval of the rerun card R-new, then keep starting its entries AND the unstarted entries of the
original R-20261109-002 (same global parity gate / ledger), until every test12 unit has a test12.json (or nothing runs and
something is missing -> report). Then analyse_t12 and post the table. No LLM, no retries (attempt 1 only).
usage: t12_pipeline2.py R-rerun [reply-to]"""
import subprocess, sys, time, re, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
rid = sys.argv[1]; reply = sys.argv[2] if len(sys.argv) > 2 else 'M-20261109-018'
ORIG = 'R-20261109-002'
PY = sys.executable
OUT = ROOT / 'code-poisson-c345/tuning/results/c345/t12'
man = json.load(open(ROOT / '.lab/j414/manifest.json'))
sys.path.insert(0, str(ROOT / 'code-poisson-c345'))
def log(*a): print(time.strftime('%F %T'), *a, flush=True)
def post(body, status='in_progress'):
    f = ROOT / '.lab/j419/_post.md'; f.write_text(body)
    subprocess.run([PY, 'tools/labq.py', 'post', '--reply-to', reply, '--author', 'coordinator', '--kind', 'status', '--status', status, '--body-file', str(f)], cwd=ROOT)
def state(r):
    out = subprocess.run([PY, 'tools/labq.py', 'request', r], cwd=ROOT, capture_output=True, text=True).stdout
    m = re.search(r'^state: (\S+)', out, re.M); return m.group(1) if m else '?'
def runs(r):
    out = subprocess.run([PY, 'tools/launch_run.py', 'list'], cwd=ROOT, capture_output=True, text=True).stdout
    return [l.split() for l in out.splitlines() if f'-{r}-e' in l]
while True:
    st = state(rid)
    if st == 'approved': break
    if st in ('rejected', 'withdrawn', 'changes'):
        log('card', st); post(f'Κώστα, η κάρτα {rid} έχει κατάσταση «{st}»· το test12 δεν συνεχίζεται.', 'failed'); sys.exit(0)
    time.sleep(30)
log('approved'); post(f'Κώστα, η κάρτα {rid} εγκρίθηκε· ξεκινούν οι έλεγχοι ισοδυναμίας που απέτυχαν, μετά το test12.')
n_test = len(man['units'])
t_last_post = 0
while True:
    for r in (rid, ORIG):
        subprocess.run([PY, 'tools/launch_run.py', 'start', '--request', r, '--all'], cwd=ROOT, capture_output=True, text=True)
    par = sorted(OUT.glob('*.parity.json')); t12 = sorted(OUT.glob('*.test12.json'))
    ra, ro = runs(rid), runs(ORIG)
    active = sum(x[1] in ('starting', 'running') for x in ra + ro)
    log(f'parity records {len(par)}/{n_test} test12 {len(t12)}/{n_test} active {active}')
    if len(t12) >= n_test: break
    if time.time() - t_last_post > 1800:
        t_last_post = time.time(); post(f'Κώστα, πρόοδος test12: parity {len(par)}/{n_test}, test12 {len(t12)}/{n_test}, ενεργά {active}.')
    if active == 0 and len(ra) >= 1:
        # nothing running: either unstarted entries remain (loop starts them) or we are stuck
        time.sleep(60)
        ra, ro = runs(rid), runs(ORIG)
        if not any(x[1] in ('starting', 'running') for x in ra + ro) and len(OUT.glob('*.test12.json') and list(OUT.glob('*.test12.json'))) < n_test:
            log('STUCK'); post(f'Κώστα, το test12 κόλλησε: parity {len(par)}/{n_test}, test12 {len(t12)}/{n_test}. Δες .lab/j419/pipeline.log.', 'failed'); sys.exit(1)
    time.sleep(30)
a = subprocess.run([PY, 'tools/c345/analyse_t12.py'], cwd=ROOT, capture_output=True, text=True)
log(a.stdout[-3000:], a.stderr[-1000:])
if a.returncode:
    post('Κώστα, το test12 τελείωσε αλλά η ανάλυση ΑΡΝΗΘΗΚΕ να βγάλει συμπεράσματα: ' + a.stdout[:1500], 'failed'); sys.exit(2)
table = (ROOT / '.lab/j414/t12_table.md').read_text()
post('# Αποτελέσματα test12 (traces 14000-14019, 10 seeds/μοντέλο, μία φορά) — ΧΩΡΙΣ ισχυρισμό\n\nΚέρδος = μέσο return/επεισόδιο 5.000 ticks (χιλ.). CI = crossed bootstrap (seeds × traces). Τίποτα δεν χρησιμοποιήθηκε για επιλογή· κάθε συμπέρασμα είναι δική σου απόφαση.\n\n' + table + '\n\nΠηγές: .lab/j414/t12_analysis.json, tuning/results/c345/t12/.', 'done')
log('posted')
