Νέα, σύντομη εργασία πριν περάσουμε στη v0.3. Μη διαβάσεις παλιές συνομιλίες ή transcripts (~/.claude/projects/*/*.jsonl).
Διάβασε μόνο docs/COORDINATION.md και CHANGELOG_v03.md για τη v0.3.

1. Έλεγχος, μόνο ανάγνωση: βρες ό,τι σε αυτό το VM ξεκινά ή ξυπνά συντονιστή ή καλεί μοντέλο: crontab -l,
   systemctl --user list-timers και list-units, tools/watchdog.sh, tools/rotate_coordinator.sh,
   tools/start-coordinator.sh, tmux, προγραμματισμένα tasks ή /loop. Για το καθένα γράψε τι κάνει και αν πρέπει να
   σταματήσει πριν ενεργοποιηθεί ο qrl-dispatcher. Αλλιώς δύο συντονιστές θα απαντούν στα ίδια μηνύματα και θα
   διπλασιαστεί το κόστος. Βρες και ό,τι συγκρούεται με τη v0.3: αλλαγές από τη v0.2 στα tools/labdb.py,
   dashboard/app.py και .claude/settings.json (git log/diff). Μην αλλάξεις τίποτα από αυτά.
2. Γράψε το docs/STATE.md με πρότυπο το prompts/STATE.template.md: έως 150 γραμμές, κάθε γεγονός με δείκτη
   (M-/R-/run id, διαδρομή). Πηγές:
   - το νεότερο αρχείο στο docs/handoffs/
   - τη μνήμη σου (~/.claude/projects/-home-ubuntu-qrl-lab/memory/)
   - το docs/DECISIONS.md
   - το docs/PLAN.md §11–§13
   Ό,τι σημαντικό υπάρχει μόνο στη μνήμη σου και όχι σε αρχείο του repo, γράψ' το στο STATE.md ή στο
   docs/DECISIONS.md, ώστε να το βλέπει και ο Codex.
3. Τρέξε python3 tools/build_md_index.py. Ψάξε το docs/INDEX.md με grep, όχι ολόκληρο. Διάλεξε έως 15 .md που είναι
   στρατηγικά σημαντικά και πρόσθεσε σε όσα δεν έχουν front matter με μία γραμμή `description:`. Μη μετακινήσεις
   και μη σβήσεις αρχεία. Ξανατρέξε το script.
4. Απάντησέ μου στα ελληνικά, σε έως 20 γραμμές:
   (α) τι πρέπει να σταματήσω πριν το βήμα 3 του SETUP_v03.md, με τις ακριβείς εντολές·
   (β) τις συγκρούσεις με τη v0.3·
   (γ) τι έγραψες και πού.
