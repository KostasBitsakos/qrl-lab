# Πύλη χρόνων pilot C345 (J364)

Το `build_w.py` δεν εκτελεί πειράματα. Χωρίς timings παράγει draft με ιστορικές εκτιμήσεις και `policy.launch_ready=false`. Ο driver απαγορεύει την εκκίνησή του. Η dry επικύρωση επιτρέπεται για έλεγχο της προετοιμασίας.

Πριν από W: χωριστό frozen pilot spec, ανεξάρτητο review, έγκριση ερευνητή, εκτέλεση μέσω `tools/launch_run.py`. Το J364 δεν καταθέτει ούτε εκτελεί αυτή την κάρτα. Κάθε διακριτό W command, μαζί με το reference, χρειάζεται πλήρη έκθεση W και την ίδια evaluation/weights διαδικασία. Διαφέρουν μόνο seed και output· δεν γίνονται extrapolations μικρών runs. Το κόστος των pilots χρεώνεται χωριστά μέσα στο εγκεκριμένο envelope (council `.lab/c341/council_record.md:22`).

Αρχείο JSON εισόδου (σχήμα, όχι πραγματικά δεδομένα):

```text
{
  "measurements": [
    {
      "cmd": [ολόκληρο το frozen command ως λίστα strings],
      "elapsed_seconds": συνολικός θετικός πεπερασμένος χρόνος,
      "includes_startup_and_eval": true,
      "run_id": "id από launcher",
      "request_id": "id εγκεκριμένου pilot request",
      "evidence_path": "διαδρομή receipt/log με timestamps και επιτυχές τέλος"
    }
  ]
}
```

Χρόνος = τέλος launcher − αρχή launcher, με startup, training, τελικό val και αποθήκευση βαρών. Όχι training-only `cpu_s`. Ένας launcher CPU ανά run και threads=1, όπως το W. Το review αντιπαραβάλλει ids, πραγματικά timestamps, ολοκλήρωση και commands με launcher records· ο builder ελέγχει δομή/κάλυψη, δεν πιστοποιεί την αλήθεια ενός εξωτερικού αρχείου.

Ο builder ταυτίζει πλήρη commands αγνοώντας μόνο τιμές `--seed`/`--out`. Απαιτεί κάλυψη όλων των διακριτών commands, και ορίζει κοινό cap ανά arm ως 2× το μέγιστο πλήρες pilot του arm (με στρογγυλοποίηση προς τα πάνω στο μικρο-hour). Ξαναχτίζει child reservations, whitelist και συνολικό budget· ο driver επαληθεύει ξανά τη συμφωνία με τα timings. Αρχεία tests με `fixture` είναι συνθετικά, δεν αποτελούν μετρήσεις.

```bash
taskset -c 4-7 .venv/bin/python tools/c345/build_w.py --lanes opus,astra --pilot-timings PATH_TO_REVIEWED_JSON
taskset -c 4-7 .venv/bin/python tools/c345/validate_w.py
```

Μετά: επανέλεγχος sandbox cap/envelope, freeze νέου hash και review πριν την κατάθεση W. Το F χρειάζεται δικό του freeze μετά την επιλογή W και full-exposure timings· το `F-template.json` δεν εξουσιοδοτεί runs.
