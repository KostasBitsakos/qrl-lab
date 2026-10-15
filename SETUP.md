# QRL-Lab — Εγκατάσταση βήμα βήμα

Όλα γίνονται στο **VM**. Στο laptop δεν εγκαθιστάς τίποτα. Χρειάζεσαι μόνο VS Code (Remote-SSH), browser και VPN.
Το Node 12 του laptop δεν μας αφορά πια.

Κανόνας: tokens, κωδικούς και κλειδιά δεν τα επικολλάς ποτέ σε συνομιλία.

---

## 0. Προετοιμασία (μία φορά)
- **Κινητό:** εγκατάστησε το Claude app και κάνε login με τον ίδιο λογαριασμό (Pro).
- **ChatGPT:** για login του Codex μέσα από SSH χρειάζεται device code. Αν δεν είναι ενεργό, ενεργοποίησέ το στο
  ChatGPT → Settings → Security. Αυτό το βήμα το βρήκα σε οδηγό τρίτου, όχι σε επίσημα docs, οπότε επιβεβαίωσέ το εκεί.
- **Αντιγραφή του kit στο VM** (από το laptop):
  ```bash
  scp qrl-lab-kit.zip <vm>:~
  ```

## 1. Έλεγχος του VM (μόνο ανάγνωση, δεν αλλάζει τίποτα)
```bash
cd ~ && unzip qrl-lab-kit.zip            # δημιουργεί το ~/qrl-lab
bash ~/qrl-lab/tools/vm_check.sh 2>&1 | tee ~/vm_check.txt
```
Στείλε μου το `~/vm_check.txt`. Αν κάποια γραμμή στο «outbound https» δείχνει `000`, σταματάμε εκεί.
Χωρίς έξοδο προς τα έξω δεν δουλεύει τίποτα από τα παρακάτω.

## 2. Εργαλεία (στον χρήστη σου, χωρίς sudo, χωρίς να αγγίξουν τα Python envs των πειραμάτων)
```bash
# Claude Code: μόνο αν το vm_check έγραψε "claude not installed"
curl -fsSL https://claude.ai/install.sh | bash

# Node LTS μέσω nvm (το Codex plugin θέλει Node ≥ 18.18).
# Πάρε την εντολή εγκατάστασης του nvm από το README του https://github.com/nvm-sh/nvm, μετά:
nvm install --lts

# Codex CLI + login με device code (δεν χρειάζεται browser στο VM)
npm install -g @openai/codex
codex login --device-auth        # ανοίγεις το URL στο laptop/κινητό και βάζεις τον κωδικό
codex login status

# Python language server για το pyright-lsp plugin (λιγότερα tokens: πλοήγηση ανά σύμβολο)
npm install -g pyright
```

## 3. Το project
```bash
cd ~/qrl-lab && git init && git add -A && git commit -m "QRL-Lab bootstrap kit v0.1"
chmod +x tools/*.sh tools/*.py
bash tools/start-coordinator.sh
```
Μέσα στο Claude Code που ανοίγει:
```
/login                                            (αν ζητηθεί· το URL το ανοίγεις στο laptop)
/plugin marketplace add openai/codex-plugin-cc
/plugin install codex@openai-codex
/plugin install pyright-lsp@claude-plugins-official
/reload-plugins
/codex:setup
/mcp                                              (έγκρινε τον project server "codex")
/status                                           (πρέπει να δείχνει Pro και Opus)
```
Αν δεις `Marketplace "claude-plugins-official" not found`, τρέξε πρώτα
`/plugin marketplace add anthropics/claude-plugins-official`.

## 4. Πρόσβαση από παντού
- **VS Code:** στο integrated terminal του Remote-SSH γράφεις `tmux attach -t lab`. Για έξοδο χωρίς να σταματήσει
  τίποτα: `Ctrl+b` και μετά `d`.
- **Browser:** claude.ai/code → session `qrl-lab`.
- **Κινητό:** Claude app → Code → `qrl-lab`. Δέξου τις ειδοποιήσεις όταν σου τις ζητήσει.
- **Dashboard** (μόλις φτιαχτεί): από το laptop `ssh -N -L 8501:127.0.0.1:8501 <vm>` και μετά `http://localhost:8501`.
- Μην ανοίγεις άλλα Claude panels στο VS Code για αυτό το project. Θα ήταν ξεχωριστές sessions, ασυντόνιστες.

## 5. Smoke tests
Γράψε στον συντονιστή: **«Τρέξε τα smoke tests S1–S6 του docs/PLAN.md §12 και ανέφερε.»**
Για το S5, σε δεύτερο terminal:
```bash
cd ~/qrl-lab && python3 tools/labq.py say "ping από τον Κώστα"
```
Ο συντονιστής πρέπει να απαντήσει χωρίς να του γράψεις τίποτα άλλο.

## 6. Μετά τα smoke tests
1. Δώσε στον συντονιστή τα paths των φακέλων σου: simulation, real-world, YAMLs, logs.
2. Θα κάνει read-only inventory (`docs/INVENTORY.md`) και θα σου προτείνει ποια είναι η τελευταία έκδοση, με τεκμήρια.
3. Επιβεβαιώνεις εσύ. Μετά (με έγκρισή σου) φτιάχνει το worktree `code/` στο branch `qrl-dev`.

## Επανεκκίνηση
- Αν το VM επανεκκινηθεί, η συνομιλία συνεχίζει με `bash ~/qrl-lab/tools/start-coordinator.sh resume`.
- Τα πειράματα τρέχουν ανεξάρτητα από τη session, με checkpoints.
