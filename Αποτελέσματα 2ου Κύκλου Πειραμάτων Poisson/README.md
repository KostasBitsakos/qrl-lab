# Αποτελέσματα 2ου Κύκλου Πειραμάτων Poisson

Εδώ μαζεύονται **αντίγραφα** των αριθμών που τροφοδοτούν τους πίνακες και τις γραφικές του paper.
Δεν αλλάζει τίποτα στα αρχικά αρχεία. Αν ένα αρχείο λείπει, γράφεται «ΛΕΙΠΕΙ» και δεν φτιάχνεται αριθμός.
Ξαναφτιάχνεται με: `python3 tools/results_collect.py`

Κανόνας: κάθε νέα παρτίδα πειραμάτων αποθηκεύει εδώ τους αριθμούς πινάκων/γραφικών της.
Ο 4ος κύκλος θα έχει δικό του φάκελο: «Αποτελέσματα 4ου Κύκλου Poisson».

Σημείωση: val = σύνολο επικύρωσης (όχι τελικός έλεγχος). Το test12 έχει ήδη χρησιμοποιηθεί μία φορά και δεν ξαναδιαβάζεται·
εδώ υπάρχει μόνο η έτοιμη σύνοψή του. Τα αποτελέσματα val είναι περιγραφικά, όχι ισχυρισμοί.

| Φάκελος / αρχείο | Τι είναι | Πηγή | Σύνολο | Seeds | Τροφοδοτεί |
|---|---|---|---|---|---|
| 1_W_screening/j380_w_analysis.json | W: σύνοψη επιλογής ρυθμίσεων | `.lab/j380/w_analysis.json` | val 13000-13019 | 18500-18501 | Πίνακας επιλογής ρυθμίσεων (παράρτημα) |
| 1_W_screening/j380_F-summary.json | W: σύνοψη F | `.lab/j380/F-summary.json` | val | - | Παράρτημα |
| 2_F_poisson_ms/c401_f_analysis.json | F: ανάλυση 10 seeds, 10 μοντέλα + αναφορές | `.lab/c401/f_analysis.json` | val 13000-13019 | 18600-18609 | Κύριος πίνακας val (poisson_ms)· παραβιάσεις SLO, pods, churn |
| 2_F_poisson_ms/c401_RESULTS.md | F: κείμενο αποτελεσμάτων | `.lab/c401/RESULTS.md` | val | 18600-18609 | Περιγραφή του πίνακα |
| 3_test12_poisson_ms/j414_t12_analysis.json | test12: τελική ανάλυση (ΜΙΑ χρήση, ήδη ξοδεμένο) | `.lab/j414/t12_analysis.json` | test12 | 18600-18609 (checkpoints) | Τελικός πίνακας test + ιεραρχία υποθέσεων |
| 3_test12_poisson_ms/j414_t12_table.md | test12: έτοιμος πίνακας | `.lab/j414/t12_table.md` | test12 | 18600-18609 | Τελικός πίνακας test (μορφή paper) |
| 4_spiky_P0_stageA/j299_stageA_summary.json | Spiky P0 αναφορές + Στάδιο A (6 seeds) | `.lab/j299/stageA_summary.json` | val 16000-16019 | 17000-17005 | Πρώιμος πίνακας spiky (παράρτημα) |
| 4_spiky_P0_stageA/j312_summary.json | Spiky ablation / mlp | `.lab/j312/summary.json` | val 16000-16019 | 17000-17005 | Παράρτημα |
| 5_S_spiky_10seeds/j442_summary.json | S: 7 μοντέλα × 10 seeds | `.lab/j442/summary.json` | val 16000-16019 | 19100-19109 | Κύριος πίνακας spiky· paired διαφορές |
| 5_S_spiky_10seeds/j446_summary.json | S: έλεγχος εγκυρότητας (J446) | `.lab/j446/summary.json` | val | 19100-19109 | Έλεγχος αναπαραγωγής |
| 6_shift_ENV_cycle3/c426_shift_results.json | Shift: αναφορές + 9 μοντέλα | `.lab/c426/shift_results.json` | val 13500-13509 | 18600-18609 | Πίνακας shift (προσαρμογή σε αλλαγή καθεστώτος) |
| 6_shift_ENV_cycle3/j431_summary.json | Shift: αναλυτικά (J431) | `.lab/j431/summary.json` | val 13500-13509 | - | Αναφορές HPA/oracle/fixed στο shift |
| 6_shift_ENV_cycle3/j438_summary.json | Shift: αναλυτικά (J438) | `.lab/j438/summary.json` | val | 18600-18609 | Αναλυτικά ανά run |
| 7_T_Dinos_vs_V2/j450_T-summary.json | T: Dinos vs Dinos+Transfer V.2, 10 νέα seeds | `.lab/j450/T-summary.json` | val | 19200-19209 | Πίνακας T + διαφορά V.2−Dinos με CI |
| 8_J444_traces_figures/base_spiky.json | Σχήμα: ίχνη φόρτου/pods, spiky | `code-poisson-c345/tuning/results/cycle3/j444/base_spiky.json` | val 16000-16002 | - | Σχήμα φόρτου, αναφορές |
| 8_J444_traces_figures/base_shift.json | Σχήμα: ίχνη φόρτου/pods, shift | `code-poisson-c345/tuning/results/cycle3/j444/base_shift.json` | val | - | Σχήμα φόρτου, αναφορές |
| 8_J444_traces_figures/c3S-dinos-s19100.traj.json | Σχήμα: ίχνη μοντέλου dinos | `code-poisson-c345/tuning/results/cycle3/j444/c3S-dinos-s19100.traj.json` | val 16000-16002 | 19100 | Σχήματα προσαρμογής (pods vs load, rewards) |
| 8_J444_traces_figures/c3S-derp-s19100.traj.json | Σχήμα: ίχνη μοντέλου derp | `code-poisson-c345/tuning/results/cycle3/j444/c3S-derp-s19100.traj.json` | val 16000-16002 | 19100 | Σχήματα προσαρμογής (pods vs load, rewards) |
| 8_J444_traces_figures/c3S-derp_hist10-s19100.traj.json | Σχήμα: ίχνη μοντέλου derp_hist10 | `code-poisson-c345/tuning/results/cycle3/j444/c3S-derp_hist10-s19100.traj.json` | val 16000-16002 | 19100 | Σχήματα προσαρμογής (pods vs load, rewards) |
| 8_J444_traces_figures/c3S-lstm-s19100.traj.json | Σχήμα: ίχνη μοντέλου lstm | `code-poisson-c345/tuning/results/cycle3/j444/c3S-lstm-s19100.traj.json` | val 16000-16002 | 19100 | Σχήματα προσαρμογής (pods vs load, rewards) |
| 8_J444_traces_figures/c3S-lstm_transfer-s19100.traj.json | Σχήμα: ίχνη μοντέλου lstm_transfer | `code-poisson-c345/tuning/results/cycle3/j444/c3S-lstm_transfer-s19100.traj.json` | val 16000-16002 | 19100 | Σχήματα προσαρμογής (pods vs load, rewards) |
| 8_J444_traces_figures/c3S-v2-s19100.traj.json | Σχήμα: ίχνη μοντέλου v2 | `code-poisson-c345/tuning/results/cycle3/j444/c3S-v2-s19100.traj.json` | val 16000-16002 | 19100 | Σχήματα προσαρμογής (pods vs load, rewards) |
| 2_F_poisson_ms/F_per_seed_val.csv | Ανά-seed βαθμολογίες (CSV από τη σύνοψη) | `.lab/c401/f_analysis.json` | όπως η σύνοψη | - | Πίνακες/boxplot ανά seed |
| 3_test12_poisson_ms/test12_per_seed.csv | Ανά-seed βαθμολογίες (CSV από τη σύνοψη) | `.lab/j414/t12_analysis.json` | όπως η σύνοψη | - | Πίνακες/boxplot ανά seed |
| 5_S_spiky_10seeds/S_per_seed_val.csv | Ανά-seed βαθμολογίες (CSV από τη σύνοψη) | `.lab/j442/summary.json` | όπως η σύνοψη | - | Πίνακες/boxplot ανά seed |
| 7_T_Dinos_vs_V2/T_per_seed_val.csv | Ανά-seed βαθμολογίες (CSV από τη σύνοψη) | `.lab/j450/T-summary.json` | όπως η σύνοψη | - | Πίνακες/boxplot ανά seed |
