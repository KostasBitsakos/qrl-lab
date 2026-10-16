# QRL-Lab v0.2 — τελευταία βήματα

Από το v0.1: τα Node, Codex login και plugins τα έχεις ήδη κάνει, οπότε δεν τα ξαναεγκαθιστάς.
Μετά από αυτά τα βήματα δουλεύεις από το dashboard. Τα tests του PLAN §12 (T0, A1–A8) δείχνουν πότε αυτό ισχύει.
Κωδικούς, tokens και κλειδιά δεν τα επικολλάς ποτέ σε συνομιλία.

## Laptop
```bash
scp qrl-lab-kit-v0.2.zip <vm>:~
```

## VM — 1. Έλεγχος (A1)
```bash
cd ~/qrl-lab
node --version        # ≥ v18.18 · αν δεν βρεθεί: source ~/.nvm/nvm.sh
codex login status    # πρέπει να λέει logged in
claude --version
```

## VM — 2. Ενημέρωση του kit
```bash
tmux kill-session -t lab 2>/dev/null       # κλείνει τον παλιό συντονιστή, αν τρέχει
cd ~ && unzip -o qrl-lab-kit-v0.2.zip      # αντικαθιστά μόνο αρχεία του kit· δεν αγγίζει τα .lab/ και code/
cd ~/qrl-lab && chmod +x tools/*.sh tools/*.py
bash tools/setup_dashboard_env.sh          # .venv μόνο για το dashboard (δεν αγγίζει το conda)
.venv/bin/python tests/test_lab.py         # T0: πρέπει να τελειώσει με "ALL PASSED (6)"
git add -A && git commit -m "QRL-Lab kit v0.2"
```
Προαιρετικό, αλλά το προτείνω: ένα αντίγραφο ασφαλείας των αρχικών φακέλων. Το `tar` μόνο τους διαβάζει,
δεν τους αλλάζει. Δες πρώτα το μέγεθος με `du -sh ~/simulations ~/redis ~/k8s ~/prometheus-grafana`.
```bash
tar czf ~/originals-backup-20261016.tgz -C ~ simulations redis k8s prometheus-grafana
```

## VM — 3. Εκκίνηση
```bash
bash tools/start-coordinator.sh
```
Ανοίγει tmux με δύο παράθυρα: `coordinator` (Claude) και `dashboard` (Streamlit). Αλλάζεις παράθυρο με
`Ctrl+b` και μετά `n`. Βγαίνεις χωρίς να σταματήσει τίποτα με `Ctrl+b` και μετά `d`.
Στο Claude:
```
/codex:setup
/status
```
Αν ζητήσει να εμπιστευτείς τον φάκελο ή να εγκρίνεις τα hooks, απάντησε ναι. Στις πρόσθετες προσβάσεις στους
αρχικούς φακέλους, οι κανόνες επιτρέπουν μόνο ανάγνωση.
Μετά γράψε στο Claude: **«Τρέξε το acceptance test A2 του docs/PLAN.md §12 και ανέφερε.»**

## Κινητό (A3)
Claude app → Code → session `qrl-lab`. Δέξου τις ειδοποιήσεις.

## Laptop — dashboard
```bash
ssh -N -L 8501:127.0.0.1:8501 <vm>        # με τις ίδιες επιλογές VPN/SSH που χρησιμοποιείς πάντα
```
Browser: **http://localhost:8501**

Στο dashboard, καρτέλα 💬 Συνομιλία → Νέο θέμα:
1. **A4**: «hello dashboard — ρώτα και τον Codex τι βρίσκει στο sandbox/demo.py». Περιμένεις δύο απαντήσεις στο θέμα,
   μία από τον Codex και μία από τον Συντονιστή.
2. **A5**: «Κάνε το A5: κατέθεσε δύο αιτήματα έγκρισης με το sandbox/toy_spec.json». Στο ✅ Αποφάσεις απορρίπτεις το
   πρώτο και εγκρίνεις το δεύτερο. Ο συντονιστής δοκιμάζει να τρέξει και τα δύο. Το πρώτο πρέπει να αρνηθεί,
   το δεύτερο να φανεί στο 📈 Πειράματα.
3. **A6**: στο VM κλείσε το Claude (`/exit` στο παράθυρο coordinator) και στείλε ένα μήνυμα από το dashboard. Το
   dashboard πρέπει να γράφει «offline» και το μήνυμα να μένει «νέο». Μετά τρέξε
   `bash tools/start-coordinator.sh resume`. Το μήνυμα πρέπει να παραδοθεί και να απαντηθεί.

Όταν περάσουν T0 και A1–A6, η συνεργασία γίνεται από το dashboard. Το terminal και το app χρειάζονται μόνο αν
το dashboard δείξει ότι ο συντονιστής περιμένει άδεια (🔐).

## Επανεκκίνηση του VM
`bash ~/qrl-lab/tools/start-coordinator.sh resume`. Τα runs έχουν checkpoints και καταγράφονται στη βάση.
