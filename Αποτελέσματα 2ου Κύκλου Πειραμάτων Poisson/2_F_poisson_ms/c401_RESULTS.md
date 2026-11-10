# Αποτελέσματα F (F-A+F-B, 10 seeds/μοντέλο) — poisson_ms, μόνο validation, ΧΩΡΙΣ ισχυρισμό

Κέρδος = μέσο return/επεισόδιο 5.000 ticks (χιλ.), τελικό checkpoint, 20 κοινά val traces. CI = bootstrap 10.000, επίπεδο seed. Ranking μεταξύ των 8 πρώτων ΔΕΝ είναι στατιστικά διακριτό.

| Μοντέλο | Κέρδος (χιλ.) | Διαφορά από HPA [95% CI] | Διαφορά από tuned HPA | SLO παραβ. | Σταθερότητα (±) | Verdict |
|---|---|---|---|---|---|---|
| Dinos | 200 | +69 [+63,+75] | -12 | 7% | ±10 | καλύτερο από HPA, όχι από tuned HPA |
| MLP (1 κρυφό) | 197 | +65 [+59,+71] | -15 | 5% | ±10 | καλύτερο από HPA, όχι από tuned HPA |
| DERP + Double DQN (νέο) | 195 | +64 [+52,+74] | -16 | 7% | ±19 | καλύτερο από HPA, όχι από tuned HPA |
| MLP + transfer | 192 | +60 [+56,+65] | -20 | 9% | ±8 | καλύτερο από HPA, όχι από tuned HPA |
| Dinos+Transfer V.2 | 189 | +58 [+49,+66] | -23 | 18% | ±14 | καλύτερο από HPA, όχι από tuned HPA |
| LSTM + transfer | 186 | +55 [+48,+62] | -25 | 9% | ±12 | καλύτερο από HPA, όχι από tuned HPA |
| LSTM | 186 | +54 [+48,+60] | -26 | 11% | ±10 | καλύτερο από HPA, όχι από tuned HPA |
| DERP βελτιωμένο (hist10) | 184 | +53 [+39,+63] | -28 | 12% | ±20 | καλύτερο από HPA, όχι από tuned HPA |
| DERP αρχικό | 131 | -1 [-31,+28] | -81 | 10% | ±51 | ασταθές — ίδιο με HPA (αβέβαιο), όχι από tuned HPA |
| DRe-SCale (LSTM-PPO) | -17 | -148 [-212,-82] | -229 | 63% | ±111 | ασταθές — χειρότερο από HPA, όχι από tuned HPA (SLO>30%) |
Αναφορές: HPA 131 (SLO 2%), tuned HPA 212 (SLO 5%, ρυθμισμένο στο ίδιο val), fixed-10 135.
Πηγές: .lab/c401/f_analysis.json (tools/c345/analyse_f.py), 80/80 runs done exit 0 (50 F-B + 30 νέα, 31 παλιά stopped = superseded). Προηγούμενο A-only: .lab/j408/RESULTS_A_only.md
