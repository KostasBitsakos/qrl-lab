# QRL-Lab v0.3.2: εγκατάσταση

Δεν εγκαθίσταται κανένα MCP, plugin ή skill. Το zip περιέχει μόνο αρχεία της v0.3 και δεν αγγίζει κανένα δικό σου.
Την προσαρμογή στο VM την κάνει **μία νέα συνεδρία Claude Code**: τρέχει τα tests και διορθώνει ό,τι αποτύχει, βρίσκει
τι πρέπει να σταματήσει, καταγράφει τα πειράματα και τη μνήμη, και εγκαθιστά αφού της πεις «ναι». Σταματά πριν από
την εναλλαγή, που την κάνεις εσύ.

## 0. claude.ai (στον browser)
Settings → Usage → **Extra usage: off** (ή μηνιαίο όριο, π.χ. $10). Έτσι, όταν τελειώσει το όριο, ο Claude
σταματά και αναλαμβάνει ο Codex, αντί να χρεώνονται credits.

## 1. VM: αρχεία και συνεδρία αναβάθμισης
Σύρε το `qrl-lab-v0.3.2-addon.zip` στον φάκελο `~` (VS Code Explorer). Σε ένα τερματικό του VS Code, **όχι** μέσα στο
tmux `lab`:
```bash
cd ~ && unzip -o qrl-lab-v0.3.2-addon.zip    # -o: αντικαθιστά μόνο την προηγούμενη v0.3
bash ~/qrl-lab/tools/upgrade_v03.sh
```
Απάντα στις ερωτήσεις της. Στο βήμα 6 σου δείχνει τι θα αλλάξει η εγκατάσταση και περιμένει το «ναι» σου. Όταν
τελειώσει, γράψε `/exit`. Κράτα την τελική της αναφορά.

## 2. VM: εναλλαγή
Σταμάτα πρώτα ό,τι σου είπε η αναφορά (cron, watchdog κ.λπ.). Μετά:
```bash
tmux kill-session -t lab                  # κλείνει τον παλιό συντονιστή και το παλιό dashboard
sudo loginctl enable-linger $USER         # μία φορά: οι υπηρεσίες τρέχουν και χωρίς ανοιχτό SSH
systemctl --user daemon-reload
systemctl --user enable --now qrl-dashboard qrl-dispatcher
python3 ~/qrl-lab/tools/dispatcher.py status   # πρέπει: heartbeat λίγα δευτερόλεπτα πριν
```
Το dashboard είναι πάλι στο http://localhost:8501 (VS Code → Ports → 8501, όπως πριν).

## 3. Dashboard: δοκιμές αποδοχής
1. «Ποια πειράματα έχουμε τρέξει, πού είναι τα αποτελέσματα και τι εκκρεμεί;» → απάντηση από τα
   `docs/EXPERIMENTS.md` και `docs/STATE.md`, με δείκτες.
2. Στο ίδιο θέμα: «@codex πες μου σε 3 γραμμές τι γράφει το docs/STATE.md» → απαντά ο Codex.
3. Άσκηση ανάληψης: στο τερματικό `python3 ~/qrl-lab/tools/dispatcher.py exhaust claude 10`. Μετά στείλε ένα μήνυμα
   χωρίς @: πρέπει να απαντήσει ο Codex, και το πάνελ να δείχνει τον Claude κόκκινο. Τέλος:
   `python3 ~/qrl-lab/tools/dispatcher.py clear claude`.

## Προαιρετικά
- Φάκελοι με .md εκτός `~/qrl-lab` στο ευρετήριο: μία διαδρομή ανά γραμμή στο `docs/index_roots.txt`.
- Φθηνότερα μηνύματα «τέλος πειράματος»: `python3 tools/dispatcher.py set events_model sonnet`.
