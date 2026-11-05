---
description: QRL-Lab v0.5 target architecture - one control plane in the dashboard, scripts instead of LLM runs for mechanical events, one source per concern, safe self-changes; phased migration from v0.4
---
# QRL-Lab v0.5: καθαρή αρχιτεκτονική και μετάβαση (σχέδιο, 3/11/2026)

Βάση: `docs/architecture_audit_2026-11-03.md` (εδώ «audit») και τα αρχεία του bundle (Part B). Γράφτηκε στο
claude.ai (Claude Opus 5.5) **χωρίς πρόσβαση στο VM**. Τον περισσότερο κώδικα δεν τον είδα: `dispatcher.py` μετά τη
γραμμή 146, `app.py`, `kb.py`, `work.py`, `labdb.py`, `convo_context.py`. Ό,τι εξαρτάται από αυτόν είναι υπόθεση και
ελέγχεται πρώτα (§14). Τα ποσά είναι εκτιμήσεις των CLI (audit §12), όχι χρεώσεις. Τα οφέλη που γράφω είναι
αναμενόμενα, όχι μετρημένα. Μετριούνται στο βήμα 1.9.

**Αποφάσεις του Κώστα (3/11/2026, claude.ai):**
1. Τώρα γίνεται **μόνο η Φάση 1**. Η Φάση 2 όταν βολέψει, η Φάση 3 μετά την υποβολή του paper.
2. Ο Πάρις τρέχει από προεπιλογή σε **Claude Sonnet** (`route.chat`).
3. Οι **ανταγωνιστικοί κλάδοι Claude/Codex και οι solo κλάδοι μένουν όπως είναι** (§10).
4. Στο τέλος μιας παρτίδας γίνεται **σύνοψη από script**. Μοντέλο τρέχει μόνο σε αποτυχία ή αν ζητηθεί (§7.1).

---

## 0. Σύνοψη

Το πρόβλημα δεν είναι ο dispatcher. Ο dispatcher είναι το κομμάτι που δουλεύει: κανένα μοντέλο δεν τρέχει όσο δεν
συμβαίνει τίποτα, και κάθε εκτέλεση ξεκινά μικρή (audit §4.1, §13). Τα προβλήματα είναι τρία.

1. **Οι ρυθμίσεις δεν φαίνονται.** Το dashboard δείχνει 4 από τις 25 ρυθμίσεις του dispatcher (§4.3). Οι πράκτορες
   απαγορεύεται να τις αλλάξουν, και σωστά. Άρα σου απαντούσαν «τρέξ' το εσύ στο τερματικό» (41 φορές, §10.1).
2. **Στρώσεις πάνω σε στρώσεις.** Κάθε κρίση λύθηκε με κάτι καινούργιο. Τα παλιά σταμάτησαν, αλλά δεν σβήστηκαν
   (§2, §10.3). Έτσι υπάρχουν 7 πηγές για τα μοντέλα, 6 στρώσεις αδειών, 3 ευρετήρια και περίπου 7 μετρητές ορίων.
3. **Μισές εκτελέσεις είναι διαχείριση.** Τέλος παρτίδας, απόφαση, άδεια, κλιμάκωση: 145 από τις 268 εκτελέσεις
   Claude, ≈$69 από ≈$148 (28/10–2/11, §12). Ένα μέρος διορθώθηκε στις 30–31/10. Πόσο μένει δεν το ξέρω.

Η v0.5 κάνει τέσσερα πράγματα και τίποτα άλλο:
- **Ένας πίνακας ελέγχου** στο dashboard για κάθε ρύθμιση. Οι πράκτορες προτείνουν με κάρτα. Εσύ πατάς «Εφαρμογή».
  Την αλλαγή την κάνει script, με 0 tokens.
- **Scripts αντί για μοντέλα** για τη μηχανική δουλειά.
- **Μία πηγή ανά θέμα** (μοντέλα, άδειες, γνώση, όρια). Το παλιό σβήνεται στο ίδιο commit.
- **Ασφαλείς αλλαγές στο ίδιο το dashboard, από το dashboard:** προεπισκόπηση, tests, «Εφαρμογή», αυτόματη επαναφορά.

Το paper είναι για τέλος Νοεμβρίου. Γι' αυτό η μετάβαση έχει τρεις φάσεις (§12). Η Φάση 1 είναι μικρή και φέρνει το
μεγαλύτερο όφελος.

---

## 1. Οι έννοιες με απλά λόγια

**Dispatcher.** Πρόγραμμα Python χωρίς AI. Περιμένει. Όταν γράψεις κάτι ή τελειώσει ένα πείραμα, ξεκινά μία σύντομη
εκτέλεση Claude ή Codex, δημοσιεύει την απάντηση και σταματά. Μπήκε στις 26–28/10. Ο προηγούμενος συντονιστής ήταν μια
συνεδρία Claude ανοιχτή από τις 16/10, με ιστορικό 282 MB. Στις 23/10 έφαγε το εβδομαδιαίο όριο και ≈$15.6 credits σε
1,5 ώρα (§4.1). Ο dispatcher μένει.

**Συντονιστής και συνομιλητής.** Είναι δύο ρόλοι, αλλά μοντέλο χρειάζεται μόνο ο ένας.
- *Συντονιστής* = ο dispatcher. Κάνει ουρά, διαλέγει μοντέλο ανά ρόλο, προσέχει όρια και προϋπολογισμό, κάνει
  failover, κλειδώνει αρχεία, κάνει commits. Όλα αυτά είναι μηχανικά: 0 tokens.
- *Συνομιλητής* = ο Πάρις. Ένα μοντέλο που σου απαντά, σχεδιάζει και αναθέτει σε workers.

Αν ήταν δύο μοντέλα, κάθε μήνυμά σου θα περνούσε από δύο εκτελέσεις, η καθεμία με δικό της context: περίπου διπλό
κόστος και περισσότερη αναμονή. Εσύ διαλέγεις ποιο μοντέλο παίζει τον Πάρη (μία ρύθμιση) και, αν θέλεις, ανά μήνυμα
από το dropdown.

**Γνώση: τρία επίπεδα.**

| Επίπεδο | Τι | Πότε φορτώνεται |
|---|---|---|
| 0 | `AGENTS.md` (+ `CLAUDE.md`) + prompt του ρόλου | πάντα |
| 1 | `docs/STATE.md` (≤ 8 KB) + τελευταία μηνύματα του θέματος + **«Σχετικά»** | σε κάθε νέα εκτέλεση, από τον dispatcher |
| 2 | `kb.py query`: docs, κώδικας, σημειώσεις, **και μηνύματα/αποφάσεις του `lab.db`** | όταν το ζητήσει ο πράκτορας |

Το «Σχετικά» είναι το έξυπνο κομμάτι. Ο dispatcher τρέχει μόνος του `kb.py query "<το μήνυμά σου>"` (script, χωρίς
μοντέλο) και βάζει τους δείκτες path:line στο πακέτο του Πάρη πριν ξεκινήσει. Ο Πάρις ξεκινά ξέροντας πού να κοιτάξει.

---

## 2. Αρχές (για κάθε αλλαγή από εδώ και πέρα)

1. **Ένα σπίτι για κάθε πληροφορία.** Ρυθμίσεις στον πίνακα ελέγχου. Κατάσταση εκτέλεσης στο `dispatch.db`.
   Συνομιλία και εγκρίσεις στο `lab.db`. Κώδικας, κανόνες και σημειώσεις στο git.
2. Ό,τι μπορεί να γίνει με script, γίνεται με script.
3. Τον έλεγχο τον έχεις εσύ, από το dashboard. Οι πράκτορες προτείνουν. Δεν εφαρμόζουν.
4. Κανένα νέο κομμάτι δίπλα σε παλιό. Το commit που προσθέτει κάτι σβήνει αυτό που αντικαθιστά.
5. Ο κώδικας του εργαστηρίου (dashboard, dispatcher, tools) αλλάζει μόνο μέσω προεπισκόπησης και «Εφαρμογής» (§9.2).
6. Κάθε ρύθμιση που διαβάζει ο κώδικας εμφανίζεται αυτόματα στο dashboard. Το ελέγχει test.

---

## 3. Διάγραμμα

```
                Κώστας (laptop / κινητό μέσω Tailscale)
                               │
                    ┌──────────▼───────────┐
                    │      Dashboard       │  Συνομιλία · Αποφάσεις · Πειράματα · Paper ·
                    │  (μόνο 127.0.0.1)    │  Γνώση · Σύστημα · Ιστορικό · Υποδομή
                    └───┬──────────────┬───┘
     μηνύματα, αποφάσεις,│              │ ρυθμίσεις: μόνο ενέργεια δική σου, με audit
     κάρτες              ▼              ▼
                  ┌──────────┐   ┌───────────────────────────────┐
                  │  lab.db  │   │ dispatch.db                   │
                  │          │   │  settings = ΜΙΑ πηγή          │
                  │          │   │  (μοντέλα, workers, budget…)  │
                  └────┬─────┘   └───────────────┬───────────────┘
                       └───────────┬─────────────┘
                     ┌─────────────▼───────────────┐  0 tokens όσο δεν συμβαίνει τίποτα
                     │ Dispatcher = συντονιστής    │─ scripts: τέλος παρτίδας, έγκριση πειράματος,
                     │ (Python, χωρίς μοντέλο)     │   commits για Codex, review jobs, kb refresh
                     │                             │─ governor: budget/ημέρα, 5ωρο, εβδομάδα, workers
                     └──┬──────────┬───────────┬───┘
     πακέτο: ρόλος +    │          │           │
     STATE + θέμα +     ▼          ▼           ▼
     «Σχετικά»     ┌─────────┐ ┌─────────┐ ┌─────────┐   Claude ή Codex ανά ρόλο
                   │ Πάρις   │ │ Workers │ │ Peer    │   (πίνακας δρομολόγησης §6)
                   │ (chat)  │ │ J<n>    │ │ (r/o)   │
                   └────┬────┘ └────┬────┘ └─────────┘
                        │           │ claims + commits (work.py) · deploy → worktree προεπισκόπησης
                        ▼           ▼                              → κάρτα «Εφαρμογή»
             git ~/qrl-lab: κώδικας, κανόνες, STATE / DECISIONS / RULES / EXPERIMENTS
                        │
                        ▼
             kb.py: ένα ευρετήριο (docs + κώδικας + μηνύματα), αυτόματη ανανέωση
```

---

## 4. Ποια αποθήκη κατέχει ποια πληροφορία

| Αποθήκη | Κατέχει (και μόνο αυτή) | Ποιος γράφει | Σημείωση |
|---|---|---|---|
| `.lab/lab.db` | συνομιλία, κάρτες/αιτήματα κάθε είδους, runs, audit των ενεργειών σου | dashboard, `labq.py`, `launch_run.py`, scripts του dispatcher | σχήμα: μόνο προσθήκες, ποτέ διαγραφές |
| `.lab/dispatch.db` | **settings** (όλες οι ρυθμίσεις, πίνακας μοντέλων, budget), providers, limits (Claude **και** Codex), sessions, tasks (κόστος), jobs, claims, agent_msgs, peer_requests | dispatcher, `work.py`, `ask_peer.py`· τα settings **μόνο** από dashboard ή κάρτα | Φάση 2: τα settings φεύγουν έξω από το workspace (§5.3) |
| git `~/qrl-lab` | κώδικας, κανόνες, prompts, πολιτική αδειών, PLAN / STATE / DECISIONS / RULES / EXPERIMENTS, journal | πράκτορες (μόνο claimed αρχεία), deploy | |
| `.lab/kb/` | παράγωγο ευρετήριο, ποτέ πηγή αλήθειας | `kb.py` (αυτόματα) | ξαναχτίζεται από το μηδέν |
| `.lab/events.jsonl` | ροή των hooks (μόνο για προβολή) | `lab_event_hook.py` | |
| `.lab/runs/`, `uploads/`, `perm/`, φάκελοι jobs | αποτελέσματα, συνημμένα, κάρτες αδειών, briefs | αντίστοιχα | |

Παύουν να είναι αποθήκες:
- root `~/qrl-lab/lab.db` (0 γραμμές), `events.jsonl`, `health.json`, `health_watch.*`· `.lab/j147/timing-copy.db`
- `.lab/usage/*.json`, `extra_credits*.json`: τα όρια ζουν μόνο στο `dispatch.db.limits`
- `.lab/health.json`, `heartbeat`, `inbox.jsonl`, `deputy_queue.jsonl`, `offers_*`: αρχειοθέτηση στο
  `.lab/archive-v02/`, όχι διαγραφή. Το `offers_watch_events.jsonl` δεν σβήνεται ποτέ (`docs/rules/dashboard.md`).

---

## 5. Πίνακας ελέγχου

### 5.1 Κάθε ρύθμιση: πού ζει, ποιος την αλλάζει, πού φαίνεται

Όλες οι ρυθμίσεις του dispatcher περιγράφονται σε ένα `SETTINGS_META` (τύπος, επιτρεπτές τιμές, ομάδα, ελληνική
ετικέτα, βοήθεια). Η καρτέλα «⚙️ Σύστημα» φτιάχνει τη φόρμα **αυτόματα** από αυτό. Μια νέα ρύθμιση εμφανίζεται μόνη
της, και ένα test αποτυγχάνει αν κάποιο κλειδί του `DEFAULTS` δεν έχει meta. Κάθε αλλαγή περνά από έλεγχο τιμής και
γράφεται στο audit (ποιος, πότε, παλιά → νέα τιμή).

| Ομάδα | Ρυθμίσεις | Πού ζει | Ποιος αλλάζει | Στο dashboard |
|---|---|---|---|---|
| Πάροχοι | `failover`, `paused`, `allow_paid_credits`, «διαθέσιμος ξανά» | dispatch.db | εσύ ή κάρτα | Σύστημα + γρήγοροι διακόπτες στο πλάι |
| Μοντέλα | `route.<ρόλος>.*` (§6). Αντικαθιστά τα `coordinator`, `claude_model/effort`, `codex_model/effort`, `events_model`, `peer_*` | dispatch.db | εσύ ή κάρτα | Σύστημα › Μοντέλα (πίνακας) |
| Παραλληλία | `max_workers`, `max_subagents` (νέο· γράφεται από script στο env του `.claude/settings.json`) | dispatch.db | εσύ ή κάρτα | Σύστημα |
| Κόστος | `budget_daily_usd`, `claude_5h_max_pct`, `claude_week_max_pct`, `codex_daily_runs` (νέα), `chat_budget_usd`, `max_budget_usd`, `peer_budget_usd`, `resume_max_tokens` | dispatch.db | εσύ ή κάρτα | Σύστημα › Κόστος, με την κατανάλωση δίπλα |
| Context | `thread_messages`, `state_max_bytes` (νέο, 8000), `kb_pointers_tokens` (νέο), `codex_resume_window_s` | dispatch.db | εσύ | Σύστημα › Προχωρημένα |
| Χρόνοι | `task_timeout_min`, `peer_timeout_min` | dispatch.db | εσύ | Σύστημα › Προχωρημένα |
| Γνώση | `kb_roots` (λίστα φακέλων), `kb_refresh_min` | dispatch.db | εσύ | Σύστημα › Γνώση |
| Dashboard | `hidden_tabs` (νέο) | dispatch.db | εσύ | Σύστημα |
| Άδειες | πολιτική (§8) → παράγει `.claude/settings.json` και `~/.codex/rules/qrl-lab.rules` | Φ1: όπως σήμερα. Φ2: ένα αρχείο πολιτικής | εσύ, με κάρτα `policy` | Σύστημα › Άδειες (προβολή + προτάσεις) |
| Sudo | grants | όπως σήμερα (`sudo_grant.py`) | εσύ | Αποφάσεις |
| Πειράματα | εγκρίσεις με frozen spec | lab.db | εσύ | Αποφάσεις |
| Υπηρεσίες | systemd units, crontab | `deploy/`, crontab | εσύ, με κάρτα `command` | Σύστημα › Υπηρεσίες (κατάσταση, restart) |
| Κανόνες | `AGENTS.md`, `CLAUDE.md`, `prompts/*`, `docs/RULES.md` | git | ζητάς → worker → κάρτα deploy | Σύστημα › Κανόνες (προβολή) |
| Κώδικας εργαστηρίου | `dashboard/`, `tools/` | git | ζητάς → worker → κάρτα deploy | Αποφάσεις |
| Ανά μήνυμα | `req_model`, `req_effort` | lab.db | εσύ | Συνομιλία· **προεπιλογή «auto»** |

Σβήνονται ως ρυθμίσεις: `escalation_debounce_s` (δεν υπάρχουν πια κλιμακώσεις, §7.1) και `events_model` (τα γεγονότα
τα χειρίζεται script).

### 5.2 Κάρτες: ο πράκτορας προτείνει, εσύ πατάς, το script εφαρμόζει

| Κάρτα | Ποιος τη φτιάχνει | Τι κάνει το «Εφαρμογή» | Tokens |
|---|---|---|---|
| `config` | πράκτορας: `labq.py ask --kind config --set KEY=VALUE --reason "…"` | `DispatchDB.set` με έλεγχο τιμής, actor = researcher (R-id) | 0 |
| `command` | πράκτορας: όνομα από λίστα επιτρεπτών + ορίσματα | το dashboard τρέχει την εντολή και δείχνει την έξοδο | 0 |
| `policy` (Φ2) | πράκτορας: αλλαγή στην πολιτική αδειών | `apply_policy.py` ξαναπαράγει τα δύο αρχεία και τα ελέγχει | 0 |
| `deploy` (Φ2) | dispatcher, όταν τελειώσει job αλλαγής κώδικα εργαστηρίου | merge, restart, έλεγχος υγείας, αλλιώς επαναφορά (§9.2) | 0 |
| πείραμα, ερώτηση, πρόταση, άδεια, sudo, council | όπως σήμερα | όπως σήμερα (έγκριση πειράματος: §7.1) | |

Αρχική λίστα επιτρεπτών `command`: restart `qrl-dashboard` ή `qrl-dispatcher`· αφαίρεση γραμμής crontab με
συγκεκριμένο σχόλιο· διαγραφή **τοπικού** κλάδου ή worktree που έχει ήδη συγχωνευτεί· `kb.py refresh --full`.
Οτιδήποτε άλλο μένει στο τερματικό. Η κάρτα δείχνει πάντα την ακριβή εντολή, όχι μόνο την περιγραφή του πράκτορα.

Με αυτό σταματά το «τρέξ' το εσύ». Ο Πάρις δεν σου δίνει εντολή για το τερματικό. Σου δίνει κάρτα.

### 5.3 Ασφάλεια: ένα κενό που υπάρχει σήμερα

Ο Claude και ο Codex τρέχουν ως ο ίδιος χρήστης Unix με εσένα. Οι απαγορεύσεις είναι κανόνες πάνω σε εντολές και
εργαλεία. Για τον Codex ειδικά: το sandbox `workspace-write` τού επιτρέπει να γράψει οποιοδήποτε αρχείο μέσα στο
`~/qrl-lab` εκτός από το `.git`. Οι κανόνες του (`qrl-lab.rules`) απαγορεύουν **εντολές** όπως `sqlite3` και
`dispatcher.py set`, όχι εγγραφή αρχείων. Θεωρητικά λοιπόν μπορεί να αλλάξει το `.claude/settings.json` ή μια βάση
μέσω Python. Δεν ξέρω αν έχει συμβεί. Ελέγχεται στο §14.

Φάση 2:
- (α) Τα settings μεταφέρονται σε `~/.config/qrl-lab/control.db`, έξω από το workspace, όπου το sandbox δεν γράφει.
  Το dashboard και ο dispatcher τα διαβάζουν από εκεί.
- (β) Ο dispatcher δεν ξεκινά εκτέλεση αν τα αρχεία ελέγχου (`.claude/settings.json`, `prompts/`, `AGENTS.md`,
  `CLAUDE.md`, `deploy/`) έχουν αλλαγές εκτός git. Σου στέλνει ειδοποίηση.

Η πλήρης λύση είναι ξεχωριστός χρήστης Unix για τους πράκτορες. Αυτή μένει για μετά το paper (Φάση 3, προαιρετικά).

---

## 6. Μοντέλα: ένας πίνακας δρομολόγησης

Κάθε ρόλος έχει κύριο πάροχο και μοντέλο για **κάθε** πάροχο. Σε failover ή όταν πιάνει όριο, ο ίδιος ρόλος πάει
στη στήλη του άλλου παρόχου. Οι τιμές είναι προτάσεις που βγαίνουν από τους κανόνες σου στο `docs/rules/models.md`
(21/10: καλύτερα μοντέλα για πειράματα, μοντέλα, αρχιτεκτονική και αριθμούς· για τα υπόλοιπα το φθηνότερο επαρκές·
Codex για υλοποίηση όταν φτάνει). Τις αλλάζεις με ένα κλικ.

| Ρόλος | Τι κάνει | Κύριος | Claude | Codex |
|---|---|---|---|---|
| `chat` | ο Πάρις | Claude | sonnet · medium | gpt-6.1-sol · medium |
| `research` | κώδικας πειραμάτων/μοντέλων/simulator, αναλύσεις αποτελεσμάτων | Claude | opus · medium | gpt-6-astra · high |
| `work` | υλοποίηση, tools, tests | Codex | sonnet · medium | gpt-6.1-sol · medium |
| `light` | dashboard, docs, μικρές αλλαγές | Codex | sonnet · low | gpt-6.1-sol · low |
| `review` | έλεγχος από τον άλλο πάροχο (read-only) | όποιος **δεν** έγραψε | sonnet · medium | gpt-6.1-sol · medium |
| `major` | council, αποφάσεις που αλλάζουν την έρευνα (read-only) | όποιος δεν έγραψε | opus · high | gpt-6-astra · high |
| `explore`, `runner` | υποπράκτορες του Claude | Claude | haiku | — |

Ονόματα μοντέλων Codex όπως εμφανίζονται στα αρχεία σου. Επιβεβαιώνονται με `codex debug models` (§14).

Κανόνες:
- Αυτός ο πίνακας είναι η **μόνη** πηγή. Ο dispatcher τον διαβάζει για τον Πάρη, τους workers και τον peer. Ένα
  script γράφει το `model:` στα `.claude/agents/*.md` από τον πίνακα. Ο dispatcher δίνει πάντα `-m` στον Codex, άρα το
  `~/.codex/config.toml` δεν επηρεάζει πια τις εκτελέσεις του εργαστηρίου.
- Σβήνονται: `docs/agent_routing.json` και η εγγραφή του από την καρτέλα «Αρχιτεκτονική» (`topology_ui.py`), καθώς και
  οι γραμμές δρομολόγησης στα `CLAUDE.md`, `docs/rules/models.md`, `interactive.md` και `handoff.md` κανόνα 3.
- Ο Πάρις αναθέτει με **ρόλο** (`work.py spawn --role research|work|light`), όχι με μοντέλο. `--to codex|claude`
  μόνο όταν το ζητήσεις εσύ.
- Το dropdown του composer έχει προεπιλογή «auto» (= πίνακας). Τα τελευταία μηνύματα έτρεξαν σε Opus ενώ η ρύθμιση
  λέει Sonnet (tasks #386, #389, #390· audit §10.2). Αν η προεπιλογή του dropdown είναι Opus, κάθε μήνυμα πληρώνει
  Opus χωρίς να το έχεις διαλέξει (§14).
- Το `coordinator:<model>` του `docs/rules/dashboard.md` λέει «ο συντονιστής αναθέτει σε άλλο μοντέλο». Η
  `route_request()` (dispatcher.py:102) απλώς κόβει το πρόθεμα και τρέχει το μοντέλο. Μένει η συμπεριφορά του κώδικα
  και διορθώνεται το κείμενο.

---

## 7. Κόστος

### 7.1 Scripts αντί για μοντέλα

| Γεγονός | Σήμερα | v0.5 | 28/10–2/11 |
|---|---|---|---|
| `run_event` (τέλος παρτίδας) | εκτέλεση μοντέλου | script: σύνοψη στο θέμα (runs ok/failed, χρόνος, CPU-h, τελευταίες μετρικές, διαδρομές) και μία γραμμή στο `EXPERIMENTS.md`. Μοντέλο μόνο αν υπάρχει αποτυχία, NaN ή αν το αίτημα έχει `on_done: analyse` | 27 εκτελέσεις, ≈$10.4 |
| `decision` | εκτέλεση μοντέλου | έγκριση πειράματος → script: `launch_run.py start --request R --all` και μήνυμα «ξεκίνησε». Απόρριψη χωρίς σχόλιο → script. Μοντέλο μόνο όταν η απόφαση έχει κείμενο που ζητά δουλειά | 33, ≈$14.1 |
| `escalation` | εκτέλεση του Πάρη | **καταργείται.** Διαφωνία μεταξύ jobs: λύνεται ανάμεσά τους (`work.py`, όπως σήμερα). Πραγματική επιλογή: κάρτα σε σένα (`labq.py ask`)· όταν απαντήσεις, το job ξαναμπαίνει στην ουρά με την απάντηση. Ο Πάρις βλέπει τις ανοιχτές κάρτες στο «Σχετικά» του | 22, ≈$28.1 (η πιο ακριβή: ≈$1.27 ανά εκτέλεση) |
| `perm_answer` | εκτέλεση, batched από 30/10 | μένει batched, αλλά γίνεται σπάνιο: `tools/dbq.py` (SQL μόνο για ανάγνωση, `mode=ro`) επιτρέπεται, τα worktrees φτιάχνονται από το `work.py`, `pip install` μέσα στο `.venv` επιτρέπεται | 63, ≈$16.7 |

Προεπιλογή για το τέλος παρτίδας: μόνο σύνοψη από script (απόφαση Κώστα 3/11). Αν ένα αίτημα χρειάζεται ανάλυση για
να ξεκινήσει ο επόμενος κύκλος, η κάρτα έγκρισης γράφει `on_done: analyse` και φαίνεται πριν την εγκρίνεις.

Συμβιβασμός: χωρίς κλιμακώσεις, μπορεί να σου έρχονται λίγο περισσότερες ερωτήσεις από workers. Κάθε κάρτα λέει από
ποιο job και ποιο αίτημα έρχεται.

Αν ένα αίτημα έχει περισσότερες καταχωρήσεις από το `max_parallel`, ο dispatcher (script) ξεκινά τις επόμενες όταν
τελειώνει ένα run. Αν σήμερα το κάνει μοντέλο, σταματά να το κάνει (§14).

### 7.2 Governor: όριο σε όλο το σύστημα, όχι ανά εκτέλεση

- Ο Πάρις απαντά **πάντα**, μέχρι το πραγματικό όριο του παρόχου. Μετά κάνει failover.
- Νέος worker σε Claude ξεκινά μόνο αν: σημερινό κόστος < `budget_daily_usd`, 5ωρο < `claude_5h_max_pct`, εβδομάδα <
  `claude_week_max_pct`. Αλλιώς πάει στη στήλη Codex του ρόλου ή περιμένει. Το dashboard γράφει «σε αναμονή: όριο».
- Codex: δεν αναφέρει κόστος, άρα όριο σε πλήθος εκτελέσεων (`codex_daily_runs`) και στα όριά του από το
  `usage_limits.py`, που γράφει πλέον στο `dispatch.db.limits`.
- Πραγματική παραλληλία = `max_workers` × (1 + υποπράκτορες). Σήμερα: 2 workers, έως 3 υποπράκτορες ο καθένας. Το
  `max_subagents` την κρατά μικρή.
- **Ένας μετρητής.** Ό,τι δείχνει το dashboard για κόστος και όρια βγαίνει από `dispatch.db` (tasks + limits).
  Σβήνονται: το snapshot του statusline ως πηγή του dashboard, `extra_credits.py` (με `allow_paid_credits=0` δεν
  χρειάζεται), `token_savings.py` και η πλαϊνή «εξοικονόμηση», που δείχνει υποθέσεις σαν μετρήσεις (audit §6.3).

### 7.3 Context

- **STATE.md:** 108 γραμμές αλλά 34 KB (≈8.5k tokens με bytes/4) σε κάθε νέα εκτέλεση. Νέο όριο **8 KB**
  (`state_max_bytes`). Το επιβάλλει το `work.py commit`, που αρνείται μεγαλύτερο αρχείο. Οι λεπτομέρειες φεύγουν σε
  αρχεία θέματος που βρίσκει το kb.
- **«Σχετικά»:** ένα `kb.py query` ανά μήνυμα, έως `kb_pointers_tokens` (≈500, όσο βγάζει σήμερα ένα query).
- **Prompts ανά ρόλο** (§13): ο worker δεν φορτώνει τις οδηγίες συνομιλίας, ούτε το αντίστροφο.

### 7.4 Μέτρηση

`tools/cost_report.py` (script): εκτελέσεις και ≈$ ανά ημέρα και είδος, από το `tasks`. Βγάζει αναφορά για τις 7
μέρες πριν και τις 7 μέρες μετά τη Φάση 1. Αυτή η αναφορά λέει αν δούλεψε, όχι οι εκτιμήσεις μου.

---

## 8. Άδειες: μία πολιτική

Φάση 1: καμία δομική αλλαγή. Προστίθεται το `dbq.py` στα allow, ώστε να βγαίνουν λιγότερες κάρτες.

Φάση 2: ένα αρχείο πολιτικής (`~/.config/qrl-lab/policy.toml`) → `tools/apply_policy.py` → παράγει το κομμάτι
`permissions` + `env` του `.claude/settings.json` (merge, όχι αντικατάσταση) και το `~/.codex/rules/qrl-lab.rules`.
Τρεις κατηγορίες:

| Κατηγορία | Τι περιλαμβάνει | Συμπεριφορά |
|---|---|---|
| deny | kubectl writes, helm, secrets, αρχικοί φάκελοι, force push, αρχεία ελέγχου, `labq decide/say`, `dispatcher set/clear/exhaust/run`, `systemctl stop/disable qrl-*` | απορρίπτεται. **Ποτέ κάρτα, ποτέ επανάληψη** |
| allow | labq (εκτός decide/say), launch_run, work, kb, dbq, ask_peer, git status/diff/log, pip μέσα στο `.venv`, kubectl get/describe/logs/top, push στο `github` (fast-forward, μετά από κοινό review) | τρέχει |
| ask | sudo (μόνο με ενεργό grant), apt, `rm -rf`, `kubectl config use-context`, ό,τι δεν είναι παραπάνω | κάρτα, και μία batched επανάληψη μετά την έγκριση |

Χωριστά μένουν τα sudo grants (`sudo_gate.py`) και οι εγκρίσεις πειραμάτων (`launch_run.py`). Είναι άλλο πράγμα:
άδειες έρευνας, όχι εργαλείων. Από 6 στρώσεις μένουν: μία πολιτική με δύο παραγόμενα αρχεία, sudo grants, εγκρίσεις
πειραμάτων, και κείμενο μόνο για όσα δεν ελέγχει εργαλείο.

Test: για κάθε γραμμή της πολιτικής, παράδειγμα εντολής ελέγχεται με `codex execpolicy check`, και το παραγόμενο
`settings.json` περνά έλεγχο schema και περιέχει τις αναμενόμενες γραμμές.

---

## 9. Dashboard

### 9.1 Από 22 καρτέλες σε 8

| Νέα καρτέλα | Από τις σημερινές |
|---|---|
| 💬 Συνομιλία | Home/chat, λίστα ενεργών jobs, 🤖 Πράκτορες |
| ✅ Αποφάσεις | Αποφάσεις, 🔐 Sudo, ⚖️ Council, νέες κάρτες config/command/deploy |
| 📈 Πειράματα | Πειράματα, 🧠 Μοντέλα (RL) |
| 📝 Paper | Paper, 🎓 Συνέδρια |
| 🗂️ Γνώση | Γνώση, 📁 Αρχεία, 📚 Tutorials, αναζήτηση στο kb |
| ⚙️ Σύστημα | πάνελ συντονιστή, 🏛️ Αρχιτεκτονική, 🧩 Επεκτάσεις, ⌨️ Terminal, υπηρεσίες, κατανάλωση και όρια |
| 🧾 Ιστορικό | Ιστορικό, 🧭 Ιστορικό αλλαγών, 🔌 Διακοπές, journal, audit ρυθμίσεων |
| 🖥️ Υποδομή | Πόροι, ☸️ Kubernetes, 📡 Prometheus, 📊 Grafana |

Φάση 1: μόνο απόκρυψη (`hidden_tabs`) και η νέα καρτέλα Σύστημα. Καμία αναδιάρθρωση.
Φάση 3: το `app.py` (3221 γραμμές, το αρχείο με τις περισσότερες συγκρούσεις claims) σπάει σε ένα αρχείο ανά καρτέλα.
Αναμένονται λιγότερες συγκρούσεις και φθηνότερες αλλαγές, επειδή ο πράκτορας διαβάζει μόνο την καρτέλα που αλλάζει.

### 9.2 Αλλαγές στο dashboard μέσα από το dashboard (deploy)

Κάθε αλλαγή στο dashboard κοστίζει tokens, όπου κι αν τη ζητήσεις. Το dashboard γλιτώνει την ανοιχτή συνεδρία, όχι
τη δουλειά. Γι' αυτό ο ρόλος `light` έχει προεπιλογή τον Codex: η δουλειά πάει στο όριο του ChatGPT, όχι του Claude.

1. Ζητάς την αλλαγή στη Συνομιλία. Ο Πάρις φτιάχνει job με `--deploy`.
2. Ο worker δουλεύει σε ξεχωριστό worktree (`~/qrl-lab-preview`, κλάδος `deploy/J<n>`). Το ζωντανό dashboard δεν το
   αγγίζει κανείς.
3. Script: tests (`tests/test_lab.py` + AppTest σε όλες τις καρτέλες). Αν περάσουν, ξεκινά προεπισκόπηση στο
   `127.0.0.1:8503` με **αντίγραφο** των βάσεων. Ό,τι πατήσεις εκεί δεν πειράζει τα αληθινά δεδομένα.
4. Κάρτα: σύνδεσμος προεπισκόπησης, αρχεία που άλλαξαν, tests ✓/✗, [Εφαρμογή] [Απόρριψη] [Ζήτα αλλαγές].
5. «Εφαρμογή» (script): merge, restart, έλεγχος υγείας 60″. Αν αποτύχει: revert, restart, μήνυμα σε σένα.

Για τον `dispatcher.py` και ό,τι φορτώνει: «Εφαρμογή όταν αδειάσει» (παύση → τέλος ενεργών jobs → restart →
`tests/test_dispatcher.py` → συνέχεια). Για προεπισκόπηση από το κινητό χρειάζεται καταχώρηση Tailscale Serve για
τη θύρα 8503 (§14).

### 9.3 Προσαρμογή για άλλες δουλειές (Φάση 3)

`dashboard/core/` (Συνομιλία, Αποφάσεις, Γνώση, Σύστημα, Ιστορικό) + `dashboard/packs/qrl/` (Πειράματα, Paper,
Υποδομή). Ένα νέο project παίρνει τον core, ένα δικό του pack και δικά του `AGENTS.md`/`STATE.md`. Συμπληρώνει το
`docs/for_other_projects.md`.

---

## 10. Claude + Codex

- Ίδια αρχεία και κανόνες. Κάθε ρόλος τρέχει σε όποιον από τους δύο.
- Ο φόρτος μοιράζεται εκ σχεδιασμού, όχι μόνο στο failover: συνομιλία και έρευνα στο Claude, υλοποίηση και dashboard
  στον Codex (§6). Δύο συνδρομές σημαίνει δύο ξεχωριστά όρια.
- Ο Codex δεν μπορεί να κάνει commit (`.git` read-only στο sandbox, audit §7.1). Στη v0.5 ο dispatcher κάνει commit τα
  claimed αρχεία του μετά την εκτέλεση (script). Τότε μόνο οι δύο γίνονται πραγματικά εναλλάξιμοι.
- Έλεγχος από τον άλλο: όταν ένα job αλλάζει κώδικα που παράγει αποτελέσματα (μοτίβα σε ρύθμιση, π.χ. `code-*/`,
  `sim_v2/`, `experiments/`), ο dispatcher βάζει αυτόματα job `review` στον άλλο πάροχο και δημοσιεύει την ετυμηγορία.
  Ο Πάρις δεν χρειάζεται να το οργανώσει.
- Ένας δρόμος προς τον Codex: μέσω dispatcher (`work.py spawn`, `ask_peer.py`). Το plugin `codex:codex-rescue` βγαίνει
  από τους κανόνες και απενεργοποιείται για το project. Το skill `council` ξαναγράφεται με `ask_peer.py`.
- **Ανταγωνιστικοί κλάδοι: μένουν όπως είναι** (απόφαση Κώστα 3/11· M-20261029-028, `handoff.md` §6). Σε κάθε κύκλο
  πειραμάτων ο Claude δουλεύει στον `<topic>` και ο Codex στον `<topic>-astra`. Για αυτά τα jobs τον πάροχο τον ορίζει
  ο κλάδος, όχι ο πίνακας §6. Ο dispatcher το ελέγχει: job σε κλάδο `-astra` πάει στον Codex, στον άλλο κλάδο στον Claude.
- Όταν ένας «κοιμάται», ο διαθέσιμος συνεχίζει και τους δύο κλάδους, όπως λέει το `handoff.md` §6. Τη δουλειά του
  αναπληρωτή την κάνει σε προσωρινούς solo κλάδους, και τα jobs σημαδεύονται `solo`. Όταν επιστρέψει ο άλλος, ο
  dispatcher βάζει αυτόματα job κοινού ελέγχου (council) για τους solo κλάδους. Έτσι ο κανόνας μένει ίδιος, χωρίς το
  deputy και το `deputy_queue.jsonl`.

---

## 11. Τι σβήνεται, τι συγχωνεύεται, τι μένει

Πριν σβηστεί οτιδήποτε: `grep` σε `tools/ dashboard/ prompts/ .claude/ deploy/ tests/ AGENTS.md CLAUDE.md` πρέπει να
δείχνει 0 αναφορές, ή να διορθώνονται στο ίδιο commit.

**Σβήνονται** (v0.2, δεν τρέχουν, audit §3, §10.3):
- `tools/start-coordinator.sh`, `health_watch.py`, `watchdog.sh`, `deputy.py`, `offers_watch.py`, `term_prompt.py`,
  `codex_health.py`, `boot_recover.sh` (αν το καλύπτει το systemd), `tools/lab-bridge/`, `lab_bridge_watch.py`
- skill `inbox`, `docs/rules/interactive.md`, τα σημεία του `handoff.md` για deputy και `deputy_queue`
- οι 12 αναφορές του `app.py` σε deputy/health_watch και τα banners από `health.json`
- `.mcp.json.disabled` και `enabledMcpjsonServers: ["codex"]` στο `settings.local.json`
- `docs/agent_routing.json` και η εγγραφή του από το `topology_ui.py`
- `token_savings.py`, `dashboard/token_savings.json`, `extra_credits.py`
- `convo_context.py` (Φάση 2, μετά τη συγχώνευση στο kb)
- skill `find-skills` (untracked, τρίτου κατασκευαστή, ενθαρρύνει νέα εργαλεία)
- η γραμμή `cycle2_daily` του crontab (έληξε 2/11), με κάρτα `command`
- root `lab.db`, `events.jsonl`, `health.json`, `health_watch.*`· `.lab/j147/timing-copy.db`.

**Αρχειοθετούνται** (`docs/archive/` ή `.lab/archive-v02/`): `SETUP.md` (v0.2), `docs/RECOVERY.md`,
`docs/deputy_handoff.md`, `.lab/inbox.jsonl`, `deputy_queue.jsonl`, `health.json`, `offers_*`.

**Συγχωνεύονται:**
- 7 πηγές μοντέλων → πίνακας §6
- 3 ευρετήρια → `kb.py`. Το `INDEX.md` μένει ως προβολή στη Γνώση, όχι οδηγία για πράκτορες
- κανόνες: τα 11 `docs/rules/*.md`, το `researcher_requirements.md` και η auto-memory του Claude
  (`docs/claude-memory/`) → **`docs/RULES.md`**: οι ισχύοντες κανόνες, χωρίς διπλά, ο καθένας με την πηγή του. Το
  `DECISIONS.md` μένει ημερολόγιο. Η auto-memory είναι δεύτερο κανάλι μνήμης που γράφει μόνο ο Claude. Οι σημειώσεις
  της μπαίνουν στο RULES.md ή σβήνονται (π.χ. `deputy-codex`, το cron του `experiment-loop`). Μετά απενεργοποιείται, αν
  το επιτρέπει η έκδοση του Claude Code (§14)
- 3 καρτέλες εγκρίσεων → μία
- περίπου 7 μετρητές ορίων → `dispatch.db` (tasks + limits)
- hooks (προαιρετικό): το `lab_event_hook.py` σε Pre/PostToolUse μένει μόνο αν το χρειάζεται η προβολή «brain».
  Αλλιώς μόνο SessionStart/SubagentStart/SubagentStop/Stop.

**Αντιφάσεις** που λύνονται όταν ξαναγραφτούν οι κανόνες:
1. `CLAUDE.md` «Codex review gate stays off» ↔ `AGENTS.md` «every result-producing change is reviewed by the other model».
2. `AGENTS.md`: «Retrieval first: kb.py» και «Notes: grep docs/INDEX.md» στο ίδιο αρχείο.
3. `docs/rules/dashboard.md` `coordinator:<model>` ↔ `route_request()` (§6).
4. `docs/rules/models.md`: fallback μέσω `.lab/deputy_queue.jsonl` (νεκρό).
5. skill `inbox` και `interactive.md`: `.lab/health.json`, QRL-INBOX (νεκρά).

**Μένουν** (audit §13): dispatcher, οι δύο λωρίδες, οι κανόνες resume, failover, `ask_peer.py`, `labdb.py`, `labq.py`,
`launch_run.py`, `work.py`, STATE, journal, η υπογραφή κόστους, tests με ψεύτικα CLI, Tailscale, systemd, `kb.py`,
τα skills `council`, `ask-user`, `drl-tuning`, `poisson-workload`, `rl-eval-protocol`, οι 5 υποπράκτορες.

---

## 12. Μετάβαση

Γενικά:
- Η δουλειά γίνεται σε **ξεχωριστό worktree** (`~/qrl-lab-v05`, κλάδος `v05`), ώστε η έρευνα να συνεχίζει. Ο
  dispatcher σταματά μόνο για λίγα λεπτά σε κάθε εναλλαγή.
- Κάθε βήμα: πρώτα tests (ψεύτικα CLI, 0 tokens), μετά κώδικας, και στο ίδιο commit σβήνεται ό,τι αντικαθίσταται.
- Πριν από κάθε εναλλαγή: δείχνεις το diff στον Κώστα και ο Codex το ελέγχει (read-only).
- Σχήμα βάσεων: μόνο νέοι πίνακες ή στήλες. Τίποτα δεν σβήνεται ή μετονομάζεται στο `lab.db`.
- Επαναφορά: κάθε βήμα είναι ένα commit με tag. Αν κάτι σπάσει: `git revert`, επαναφορά backup βάσης (μόνο αν άλλαξε
  σχήμα), restart.

**Φάση 0: προετοιμασία** (καμία αλλαγή συμπεριφοράς)
- 0.1 Έλεγχοι §14. Αναφορά αποκλίσεων στον Κώστα πριν από οτιδήποτε άλλο.
- 0.2 Πράσινα tests: `test_dispatcher`, `test_lab`, `test_kb`, `test_exp_view`. Το `test_exp_view` αποτυγχάνει από
  τις 29/10: διόρθωση ή καραντίνα με αιτιολογία.
- 0.3 Τα 44 uncommitted paths: λίστα ανά κατηγορία. Ο Κώστας αποφασίζει commit ή αρχειοθέτηση. Ποτέ `git add -A`.
- 0.4 Backup `.lab/lab.db` και `.lab/dispatch.db` (online backup του SQLite) και `git tag pre-v05`.

**Φάση 1: έλεγχος και κόστος** (τώρα)
- 1.1 `SETTINGS_META` + καρτέλα «⚙️ Σύστημα» με όλες τις ρυθμίσεις, έλεγχο τιμών και audit. Tests: κάθε κλειδί του
  `DEFAULTS` έχει meta και εμφανίζεται (AppTest)· άκυρη τιμή απορρίπτεται.
- 1.2 Κάρτες `config` και `command`. Test: η έγκριση αλλάζει τη ρύθμιση και δεν δημιουργεί γραμμή στο `tasks`.
- 1.3 Πίνακας δρομολόγησης (§6), `work.py spawn --role`, παραγωγή front-matter, dropdown με προεπιλογή «auto».
  Σβήνονται οι παλιές πηγές. Test: το ψεύτικο CLI παίρνει το σωστό `--model`/`-m` ανά ρόλο, και στο failover.
- 1.4 Scripts γεγονότων (§7.1), κατάργηση κλιμακώσεων, `dbq.py`. Tests: τέλος παρτίδας → μήνυμα στο θέμα και 0 νέες
  γραμμές `tasks`· αποτυχία → μία εργασία· έγκριση πειράματος → runs ξεκινούν, 0 εργασίες.
- 1.5 Governor (§7.2). Tests: με budget 0 οι workers περιμένουν και ο Πάρις απαντά· με 5ωρο πάνω από το όριο ο
  worker πάει Codex.
- 1.6 Όριο STATE 8 KB στο `work.py commit`. Μία συμπύκνωση του σημερινού STATE (worker, με έγκρισή σου).
- 1.7 Σβήσιμο των v0.2 (§11) και του stray υλικού.
- 1.8 `hidden_tabs`: κρύψε ό,τι δεν χρησιμοποιείς.
- 1.9 `cost_report.py`: αναφορά πριν/μετά.

Δοκιμές αποδοχής στο τέλος της Φάσης 1, από το κινητό:
- A. Αλλάζεις `max_workers` από το Σύστημα. Το `dispatcher.py status` το δείχνει, και το audit γράφει «researcher».
- B. Γράφεις στον Πάρη «βάλε 3 workers». Εμφανίζεται κάρτα. Ένα κλικ, και η αλλαγή γίνεται χωρίς εκτέλεση μοντέλου.
- C. Τελειώνει μια παρτίδα. Η σύνοψη εμφανίζεται στο θέμα χωρίς εκτέλεση μοντέλου.
- D. Εγκρίνεις πείραμα. Τα runs ξεκινούν χωρίς εκτέλεση μοντέλου.
- E. Βάζεις κύριο του `chat` τον Codex. Σου απαντά ο Codex, και η υπογραφή το γράφει.
- F. `budget_daily_usd = 0`: οι workers περιμένουν, ο Πάρις απαντά.
- G. `grep` για όλα τα σβησμένα: 0 αποτελέσματα.

**Φάση 2: γνώση, κανόνες, ασφαλείς αλλαγές** (μετά τη Φάση 1, όταν σου βολεύει)
- 2.1 Το `kb.py` γίνεται η μόνη ανάκτηση. Νέα πηγή: `lab.db` (μηνύματα, αιτήματα, αποφάσεις με M-/R- ids). Αυτόματη
  ανανέωση: μικρή μετά από κάθε job και κάθε `kb_refresh_min`, πλήρης τη νύχτα, στους πυρήνες 4–7. Το «Σχετικά»
  μπαίνει στο πακέτο του Πάρη. Σβήνεται το `convo_context.py`. Το `INDEX.md` μένει μόνο ως προβολή. Το graphify μένει
  για το `kb.py callers` και την καρτέλα-γράφημα, χωρίς άλλη δουλειά πάνω του: μόνο του δεν έδειξε κέρδος (audit §6.2,
  `docs/kb_eval.md`).
- 2.2 Νέα `AGENTS.md`, `CLAUDE.md`, `prompts/chat.md`, `prompts/worker.md` (§13)· `docs/RULES.md`· σβήσιμο
  `docs/rules/`, `interactive.md`, skill `inbox`· η auto-memory μεταφέρεται σε αρχεία.
- 2.3 Πολιτική αδειών (§8) και μεταφορά των settings έξω από το workspace (§5.3).
- 2.4 Deploy: προεπισκόπηση, εφαρμογή, επαναφορά (§9.2).
- 2.5 Commits του Codex από τον dispatcher· αυτόματο `review` job (§10).
- 2.6 Ενιαία καρτέλα Αποφάσεις.

**Φάση 3: μετά την υποβολή του paper**
- 3.1 Σπάσιμο του `app.py` ανά καρτέλα, 8 καρτέλες (§9.1).
- 3.2 Core + packs για άλλες δουλειές (§9.3).
- 3.3 Προαιρετικά: ξεχωριστός χρήστης Unix για τους πράκτορες.

---

## 13. Νέα αρχεία κανόνων (Φάση 2.2· στα αγγλικά, όπως τα σημερινά)

Οι εντολές με ★ δεν υπάρχουν ακόμα: τις φτιάχνει η Φάση 1 (`labq.py ask --kind config|command`, `dbq.py`,
`work.py spawn --role/--deploy`) και η Φάση 2 (`docs/RULES.md`, «Σχετικά»).

### `AGENTS.md`
```markdown
# QRL-Lab — shared rules (Claude and Codex)

Research: hybrid quantum–classical extension of the DInos autoscaler (Kubernetes + Redis, Deep RL).
Plan: `docs/PLAN.md` (read only the section you need). Your role (chat, worker or peer) is in your task text.

## Safety — always; nothing overrides these
- Edit only inside `~/qrl-lab`, and only paths you claimed (`tools/work.py claim`). Never edit `~/simulations`,
  `~/redis`, `~/k8s`, `~/prometheus-grafana`.
- Never read or print secrets (`~/.ssh`, `.env`, tokens, `~/.codex/auth.json`, `~/.kube/config`, IBM credentials).
- Experiments only through `tools/launch_run.py` with an approved frozen spec. No `kubectl` writes, Helm, IBM Quantum
  jobs, installs outside `.venv`, purchases or API keys.
- `git push` only to remote `github`, fast-forward, after a joint Claude+Codex review (R-20261029-002); never `--force`.
- The control plane belongs to the researcher: settings, model routing, budgets, permissions (`.claude/settings.json`,
  `~/.codex/`), `prompts/`, `deploy/`, systemd, crontab. Never change them, and never tell him to use the terminal:
  file a one-click card with `python3 tools/labq.py ask --kind config|command ...` ★ (see `--help`).
- Never invent numbers, results, citations or API behaviour. Every number gets a pointer (path:line, run id,
  M-/R- id); otherwise write "unknown".
- Quantum: no speed-up claims from simulator timings; parameter savings only against a parameter-matched classical
  control.

## Knowledge
- Handoff: `docs/STATE.md` (≤ 8 KB). It is in your task text when you start fresh, with «Σχετικά» ★ pointers.
- Anything else: `python3 tools/kb.py query "<question or id>"` first (docs, code, notes, past messages and
  decisions), then read only the returned path:line windows. Exact symbol in a known file: `grep -n`.
- Current research and process rules: `docs/RULES.md` ★ (search it; do not read it whole). History: `docs/DECISIONS.md`.
- Experiments: `python3 tools/launch_run.py list`, `docs/EXPERIMENTS.md`. Lab databases, read-only:
  `python3 tools/dbq.py "SELECT ..."` ★.
- Before adding a rule to `docs/RULES.md` or to this file, search for conflicts. On a conflict, ask the researcher
  and do not write.

## The researcher (Kostas)
- Greek, short and direct, opening with «Κώστα,». The chat coordinator signs «— Πάρις» («— Πάρις (Codex)» when
  Codex). Code, files and internal notes in English.
- Anything that needs him (approval, question, choice): `python3 tools/labq.py ask ...`, never only in a file.
  Silence is never approval.
- Write `~/` paths so the dashboard links them.

## Claude and Codex
Same rules and files for both; either may take any role. The other model is a co-researcher:
`python3 tools/ask_peer.py ask --prompt-file <brief.md> [--major]` (read-only; send the question, not your answer).
Result-producing code changes are reviewed by the other model before their results are used; the dispatcher queues
that review.
```

### `CLAUDE.md`
```markdown
@AGENTS.md

# Claude specifics
- Subagents: `Explore` for searches, `runner` for approved runs, `engineer` / `scholar` / `writer` as their
  descriptions say. Their models come from the routing table (generated front-matter); do not override them.
- Reach Codex only through `tools/ask_peer.py` or `tools/work.py spawn`; do not use the Codex plugin.
```

### `prompts/chat.md`
```markdown
# Role: chat coordinator «Πάρις» (job C<n>)

The dispatcher started you for ONE researcher message. Keep his line open: answer fast.
- Do yourself: answers, plans, status, small edits (one or two files, a few minutes; claim first).
- Hand off anything longer: `python3 tools/work.py spawn --role research|work|light --title "..." --brief-file <brief.md> [--deploy]` ★.
  The brief is self-contained: quote his request, scope, likely files, what "done" means, which tests to run.
  Use `--deploy` for any change to `dashboard/`, `tools/` or `prompts/`: it goes through a preview and his «Εφαρμογή».
  Independent parts → separate jobs; dependent parts → one job. Tell him the job ids.
- He changed his mind about running work: `work.py say <job> "..."` or `work.py cancel <job>`.
- He asks to change a setting (models, workers, budget, permissions, services): file the card
  (`labq.py ask --kind config --set KEY=VALUE --reason "..."` ★) and tell him it is in Αποφάσεις.
- Use the «Σχετικά» pointers in your task text before searching. Open cards and finished jobs are listed there too.
- Ask the other model (`ask_peer.py`) when he asks for it, or before a decision that changes the research. Post its
  answer verbatim (`labq.py post --author codex|claude --kind contribution`), then your synthesis.
- If something changed: update `docs/STATE.md` (keep its headings, ≤ 8 KB, a pointer for every fact) and append
  accepted decisions to `docs/DECISIONS.md` (claim, edit, `work.py release`).
- Your final message is the reply; the dispatcher posts it. End with `STATUS: waiting_approval` if you now wait for
  him, `STATUS: failed` if you could not do it.
```

### `prompts/worker.md`
```markdown
# Role: worker (job J<n>)

The dispatcher started you for ONE job. Do its brief end to end. Your final message is the report (Greek, short,
with pointers); the dispatcher posts it in the researcher's thread.
- Before editing: `python3 tools/work.py claim <paths> --note "<why>"`. Exit 2 means another job holds an
  overlapping path: negotiate (`work.py say <job> "..."`, then `work.py inbox --wait 120`), record the outcome
  (`work.py agree`), or wait (`claim --wait 600`). Never edit a file you have not claimed.
- Send no progress notes. If the researcher must choose: `labq.py ask`, then end with `STATUS: waiting_approval`;
  the job resumes with his answer.
- Commit only your claimed files: `python3 tools/work.py commit -m "<msg> (<job id>)"`. Never `git add -A`,
  `commit -a`, `stash`, `checkout -- .` or `reset`. If you are Codex, `.git` is read-only: list your changed files in
  the report and the dispatcher commits them.
- Shared docs (`docs/STATE.md`, `docs/DECISIONS.md`, `docs/EXPERIMENTS.md`): claim them only for the minute you
  update them, then `work.py release`.
- Deploy jobs: work only in the worktree named in the brief; the dispatcher runs the tests and builds the preview.
- Run the tests named in the brief and report the command and its outcome. Never fake a result or a passing test.
- End with `STATUS: failed` if you could not finish.
```

`prompts/peer.md`: μένει ως έχει. Τα skills `drl-tuning`, `poisson-workload`, `rl-eval-protocol` μένουν. Στο
`ask-user` προστίθενται τα είδη `config` και `command`. Το `council` ξαναγράφεται με `ask_peer.py`.

---

## 14. Τι ελέγχεται στο VM πριν αλλάξει οτιδήποτε

1. Ο dispatcher διαβάζει τα settings σε κάθε γύρο ή μόνο στην εκκίνηση;
2. Πού χρησιμοποιείται το `convo_context.py` (dispatcher, dashboard, αλλού);
3. Ποια είναι η προεπιλογή του dropdown μοντέλου στον composer;
4. Χρειάζεται το `launch_run.py start --all` να ξανακληθεί για τις επόμενες καταχωρήσεις; Ποιος το κάνει σήμερα;
5. Γράφεται στο `dispatch.db.limits` και η εβδομαδιαία χρήση του Claude, ή μόνο το 5ωρο;
6. Ποια σημεία χρησιμοποιούν τα `.lab/usage/claude.json` και `extra_credits*.json`;
7. Μπορεί ο Codex, μέσα στο sandbox του, να γράψει `.claude/settings.json` ή `.lab/dispatch.db`; (§5.3· δοκιμή με
   ψεύτικο αρχείο, όχι με τα αληθινά.)
8. Οι 12 αναφορές του `app.py` σε deputy/health_watch: τι δείχνει η καθεμία;
9. Γιατί αποτυγχάνει το `tests/test_exp_view.py`;
10. Πώς είναι ρυθμισμένο το Tailscale Serve, και μπορεί να εκθέσει και τη θύρα 8503;
11. Πού αποθηκεύονται τα sudo grants;
12. Επιτρέπει η έκδοση του Claude Code να κλείσει η auto-memory ανά project;
13. `codex debug models`: ποια μοντέλα δέχεται ο λογαριασμός;
14. Χρησιμοποιεί κάτι τα `lab_event_hook.py` Pre/PostToolUse, εκτός από την προβολή «brain»;

---

## 15. Για τη συνεδρία Claude Code που θα το υλοποιήσει

- Διάβασε αυτό το αρχείο και μετά το `docs/architecture_audit_2026-11-03.md`. Μη διαβάσεις τίποτα άλλο ολόκληρο. Για
  τα υπόλοιπα, `kb.py query`.
- Κάνε πρώτα τους ελέγχους του §14 και γράψε στον Κώστα, στα ελληνικά και σύντομα, πού το σχέδιο δεν ταιριάζει με το
  VM. Περίμενε το «ναι» του.
- Δούλεψε στο worktree `v05`, μία φάση τη φορά, με τη σειρά του §12. Μην προσθέσεις τίποτα που δεν είναι στο σχέδιο
  χωρίς να ρωτήσεις.
- Μην πειράξεις κώδικα έρευνας, πειράματα, specs ή τους αρχικούς φακέλους.
- Στο τέλος κάθε φάσης: αναφορά (τι άλλαξε, ποια tests πέρασαν, τι σβήστηκε), ενημέρωση `docs/STATE.md`,
  `CHANGELOG_v05.md`, και τέλος συνεδρίας (`/exit`). Η επόμενη φάση ξεκινά σε νέα συνεδρία.
