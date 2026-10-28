Εργασία: ολοκλήρωσε την αναβάθμιση αυτού του VM στη v0.3 (dispatcher). Είσαι νέα συνεδρία. Μη διαβάσεις παλιές
συνομιλίες ή transcripts (~/.claude/projects/*/*.jsonl) και μην ξεκινήσεις υπηρεσίες.
Διάβασε πρώτα: SETUP_v03.md, CHANGELOG_v03.md, docs/COORDINATION.md.

Κανόνες για αυτή την εργασία
- Επιτρέπεται να αλλάξεις τα αρχεία της v0.3 για να ταιριάζουν σε αυτό το VM: tools/dispatcher.py, tools/ask_peer.py,
  tools/build_md_index.py, tools/install_v03.py, dashboard/coord_panel.py, tests/test_dispatcher.py, tests/fakes/,
  prompts/, deploy/. Τα dashboard/app.py, tools/labdb.py, .claude/settings.json, CLAUDE.md και AGENTS.md τα αλλάζεις
  μόνο αν είναι απαραίτητο, και πρώτα μου εξηγείς γιατί.
- Ποτέ μη χαλαρώσεις τον έλεγχο ενός test για να περάσει. Αν ένας έλεγχος δεν ισχύει για αυτό το VM, εξήγησε γιατί
  πριν τον αλλάξεις.
- Οι προειδοποιήσεις (warnings) του Streamlit δεν είναι αποτυχία. Το αποτέλεσμα είναι η τελευταία γραμμή:
  ALL PASSED ή FAILED.
- Τα tests τα τρέχεις πάντα με όριο χρόνου: timeout 600 .venv/bin/python tests/test_dispatcher.py 2>&1 | tail -40
- Μη σταματήσεις τον παλιό συντονιστή, μην αλλάξεις cron ή systemd, μην τρέξεις sudo.

Βήματα
1. Tests: τα tests/test_dispatcher.py και tests/test_lab.py να τελειώνουν με ALL PASSED. Αν κάτι αποτυγχάνει ή
   κολλάει, βρες την αιτία σε αυτό το VM και διόρθωσέ την.
2. Έλεγχος (μόνο ανάγνωση): βρες ό,τι ξεκινά ή ξυπνά συντονιστή ή καλεί μοντέλο: crontab -l, systemctl --user
   list-timers και list-units, tools/watchdog.sh, tools/rotate_coordinator.sh, tools/start-coordinator.sh, tmux ls,
   προγραμματισμένα tasks, /loop. Για το καθένα γράψε τι κάνει και την ακριβή εντολή που το σταματά πριν από την
   εναλλαγή.
3. Πειράματα: φτιάξε το docs/EXPERIMENTS.md (πρότυπο: prompts/EXPERIMENTS.template.md) με ΚΑΘΕ παρτίδα πειραμάτων που
   μπορείς να βρεις. Πηγές:
   - python3 tools/launch_run.py list
   - docs/handoffs/
   - η μνήμη σου (~/.claude/projects/-home-ubuntu-qrl-lab/memory/)
   - docs/DECISIONS.md
   - ό,τι τρέχει τώρα (ps, tmux, nvidia-smi)
   Για κάθε παρτίδα γράψε: τι είναι, πού τρέχει ή έτρεξε, πού είναι τα αποτελέσματα, την κατάσταση, και το αποτέλεσμα
   με δείκτη. Ό,τι δεν επιβεβαιώνεις, γράψ' το «άγνωστο», μαζί με το πώς ελέγχεται.
4. Μνήμη: γράψε το docs/STATE.md (πρότυπο: prompts/STATE.template.md, έως 150 γραμμές, κάθε γεγονός με δείκτη) από τις
   ίδιες πηγές. Πρέπει ένας νέος συντονιστής, Claude ή Codex, να μπορεί να συνεχίσει μόνο με αυτό. Ό,τι σημαντικό
   υπάρχει μόνο στη μνήμη σου, γράψ' το στο STATE.md, στο DECISIONS.md ή στο EXPERIMENTS.md.
5. Τρέξε python3 tools/build_md_index.py. Ψάξε το docs/INDEX.md με grep και διάλεξε έως 15 στρατηγικά .md που δεν
   έχουν περιγραφή. Πρόσθεσε σε αυτά front matter με γραμμή `description:`. Μετά ξανατρέξε το script.
6. Τρέξε python3 tools/install_v03.py (χωρίς --apply) και δείξε μου τι θα αλλάξει. Περίμενε να σου πω «ναι». Μετά:
   --apply, ξανά τα δύο tests, και git add -A && git commit.
7. Στο τέλος απάντησέ μου στα ελληνικά, σε έως 25 γραμμές:
   (α) τι διόρθωσες και γιατί·
   (β) τι πρέπει να σταματήσω πριν την εναλλαγή, με τις ακριβείς εντολές·
   (γ) ποια πειράματα βρήκες και πού είναι·
   (δ) τις εντολές της εναλλαγής (SETUP_v03.md, βήμα 3), προσαρμοσμένες σε όσα βρήκες. Μην τις τρέξεις εσύ.
