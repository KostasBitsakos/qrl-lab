"""J444: generate report.tex (Greek text, English code) from stored JSON and compile with lualatex."""
import json, os, subprocess, statistics as st, sys
sys.path.insert(0, os.path.dirname(__file__))
import figs
R = figs.R; D = R + "reports/2026-11-10-models-report/"
s = figs.summ(); b = figs.p0(); sh = json.load(open(R + ".lab/j438/summary.json"))
have = lambda f: os.path.exists(D + "fig/" + f)
def f0(x): return f"{x:,.0f}".replace(",", ".")
rows = ""
for a in figs.ORDER:
    v = s[a]; rows += f"{figs.NAME[a]} & {f0(v['mean'])} & {f0(v['sd'])} & {f0(v['median'])} & {f0(v['min'])} & {f0(v['max'])} & {v['slo']:.3f} & {v['params']:,} \\\\\n".replace(",", ".") if False else \
        f"{figs.NAME[a]} & {f0(v['mean'])} & {f0(v['sd'])} & {f0(v['median'])} & {f0(v['min'])} & {f0(v['max'])} & {v['slo']:.3f} & {f0(v['params'])} \\\\\n"
brow = "".join(f"{figs.BNAME[k]} & {f0(b[k]['mean'])} & {f0(b[k]['sd'])} & \\multicolumn{{3}}{{c}}{{20 val episodes}} & -- & -- \\\\\n" for k in ["hpa_orig", "hpa_demand", "oracle", "fixed"])
def fig(f, cap, w=1.0):
    return f"\\begin{{figure}}[htbp]\\centering\\includegraphics[width={w}\\linewidth,height=0.8\\textheight,keepaspectratio]{{fig/{f}}}\\par\\small {cap}\\end{{figure}}\n" if have(f) else f"\\textbf{{[λείπει: {f}]}}\n\n"
T = r"""\documentclass[10pt,a4paper]{article}
\usepackage[margin=2cm]{geometry}
\usepackage[utf8]{inputenc}
\usepackage[LGR,T1]{fontenc}
\usepackage{lmodern}
\usepackage{textalpha}
\usepackage{substitutefont}
\substitutefont{LGR}{\rmdefault}{cmr}
\substitutefont{LGR}{\sfdefault}{cmss}
\substitutefont{LGR}{\ttdefault}{cmtt}
\usepackage{textcomp}
\sloppy\emergencystretch=3em
\usepackage{amsmath,graphicx,booktabs,xcolor,enumitem,array,float}\usepackage[hidelinks]{hyperref}
\setlength{\parskip}{0.45em}\setlength{\parindent}{0pt}\setlist{itemsep=0.1em,topsep=0.2em}
\newcommand{\ptr}[1]{{\footnotesize\texttt{#1}}}
\title{QRL-Lab: είσοδος, αποτελέσματα και αρχιτεκτονικές των μοντέλων\\\large cycle 3 · batch S · workload \texttt{poisson\_ms\_spiky} (και shift)}
\author{Πάρις --- ετοιμάστηκε για τον Κώστα (M-20261110-003, J444)}\date{10/11/2026}
\begin{document}\maketitle
\section{Τι περιέχει και τι ΟΧΙ}
\begin{itemize}
\item Όλα τα νούμερα είναι \textbf{validation} (spiky: val 16000--16019, shift: val 13500--13509)· \textbf{κανένα test split} δεν χρησιμοποιήθηκε, καμία νέα εκπαίδευση. Δεν είναι συμπέρασμα γενίκευσης ούτε claim.
\item Τα σχήματα adaptation (pods vs load) προέρχονται από \textbf{eval-only} επανεκτέλεση των αποθηκευμένων checkpoints του training seed 19100 (ένα seed ανά μοντέλο) σε 3 val επεισόδια (seeds 16000--16002), μέσω \ptr{tools/envelope.py} (envelope cycle3). Άρα δείχνουν συμπεριφορά ενός εκπαιδευμένου μοντέλου, όχι μέσο όρο seeds.
\item Το RPPO/DRe-SCale έχει δικό του module (\ptr{tuning/rppo.py}) χωρίς καταγραφή τροχιάς· ΔΕΝ υπάρχει σχήμα pods-vs-load γι' αυτό (τα νούμερα return και η αρχιτεκτονική υπάρχουν). Δεν επινοήθηκε τίποτα.
\item Το latency είναι \emph{proxy} (χρόνος παραμονής στην ουρά + $l_0$ τη στιγμή της αποδοχής), όχι μετρημένος χρόνος απόκρισης (\ptr{tuning/poisson\_ms.py}, docstring).
\item Οι αρχιτεκτονικές διαβάστηκαν από τον κώδικα και από τα \texttt{.pt} checkpoints· ο αριθμός παραμέτρων μετράται από τα state\_dict (συμφωνεί με \texttt{n\_params} των JSON).
\end{itemize}

\section{Είσοδος: workload και μετρικές}
Περιβάλλον: ουρά αιτημάτων με πόδια (pods) 1--20, $\mu=10$ αιτήματα/pod/tick, καθυστέρηση εκκίνησης pod 5 ticks, ουρά max 200, SLO: p95 latency $>1.0$ ή drops, κόστος pod 3/tick, ποινή SLO 20, ποινή drop 1 ανά αίτημα, επεισόδιο 5000 ticks, αρχικά 6 pods. Ρυθμός: $\lambda_t=\text{base}\cdot(1+0.4\sin(2\pi t/1000+\varphi))\cdot e^{x_t}$ (AR(1) log-noise, $\phi=0.98$, $\sigma=0.15$), $N_t\sim\text{Poisson}(\lambda_t)$. Η \texttt{spiky} παραλλαγή αντικαθιστά τη μαρκοβιανή έκρηξη με επικάλυψη γεγονότων (απότομα flash-crowds, ράμπες, ριπές), με $\lambda\le190$. Η \texttt{shift} έχει συχνότερες εκρήξεις ($r_{nb}=1/300$) και $\sigma=0.30$. Δράσεις: 0 κάτω / 1 μένω / 2 πάνω. Reward $=\text{served}-3\cdot\text{pods}-20\cdot[\text{SLO}]-\text{drops}$. \ptr{code-poisson-c345/tuning/poisson\_ms.py:1-34,55-124}.

State 7 διαστάσεων: [arrivals, capacity, CPU\%, mem\%, p95 latency, active pods, pending pods]· κανονικοποίηση (obs\_scale) με διαιρέτες 100,100,100,100,2,20,20 και reward/10 (\ptr{S/c3S-dinos-s19100.json}).
""" + fig("workload_spiky.png", "Είσοδος (spiky, val seed 16000): load και, για τρεις ελεγκτές αναφοράς, latency p95, CPU, μνήμη και pods. Τα CPU/mem/latency εξαρτώνται από τον ελεγκτή· δεν είναι ιδιότητα της εισόδου μόνο. Πηγή: eval-only \\ptr{base\\_spiky.json}.") + fig("workload_shift.png", "Ίδιο για το shift workload (val seed 13500).") + r"""
\section{Συνολικό reward ανά μοντέλο}
""" + fig("rewards_spiky.png", "Return ανά επεισόδιο, spiky val. Μοντέλα: μέσο ± sample SD των 10 training seeds 19100--19109 (μία κουκκίδα ανά seed, μέσος 20 val επεισοδίων, ένα checkpoint 19968 ticks). Baselines: μέσο ± SD των 20 val επεισοδίων με παραμέτρους επιλεγμένες στο ίδιο val (P0)· δεν είναι ανεξάρτητα από το val.") + r"""
\begin{table}[H]\centering\footnotesize\begin{tabular}{lrrrrrrr}\toprule
Μοντέλο & μέσο & SD & διάμεσος & min seed & max seed & SLO viol. & παράμετροι\\\midrule
""" + rows + r"\midrule" + "\n" + brow + r"""\bottomrule\end{tabular}
\caption{Πηγή: \ptr{.lab/j442/summary.json} (μοντέλα), \ptr{code-poisson-spiky/tuning/results/spiky-stage1/spiky1-P0-reference-off-s16000.json} (baselines). Ο oracle είναι look-ahead ευρετικός, όχι άνω φράγμα (\ptr{docs/paper\_notes.md} §6).}\end{table}
Παρατηρήσεις (περιγραφικά): όλα τα μοντέλα είναι κάτω από το tuned HPA (201,9k) και τον oracle (222,7k)· Dinos και Dinos+Transfer V.2 δεν διακρίνονται (paired διαφορά $-3{,}5\text{k}\pm16{,}9\text{k}$, \ptr{.lab/j442}). DERP enhanced και RPPO είναι ασταθή (seeds με αρνητικό return).
""" + fig("rewards_shift.png", "Shift workload (held-out), τα checkpoints F (10 seeds, 39936 ticks) αξιολογημένα eval-only στο val. Πηγή: \\ptr{.lab/j438/summary.json}. Περιγραφικό, όχι test.") + r"""
\section{Προσαρμογή: pods ως προς το load}
""" + fig("adaptation_timeseries.png", "Pods (έγχρωμο, δεξιός άξονας) και load (γκρι) στο ίδιο val επεισόδιο, ένα training seed (19100) ανά μοντέλο· στο τέλος οι ελεγκτές αναφοράς.") + fig("adaptation_pods_vs_load.png", "Μέσος αριθμός pods ανά κλάση load. Ένα training seed, 3 val επεισόδια.", 0.85) + r"""
\section{Αρχιτεκτονικές των μοντέλων}
Κοινά (αν δεν αναφέρεται διαφορετικά): 3 δράσεις, reward/10, κανονικοποιημένη είσοδος 7 χαρακτηριστικών, Adam, απώλεια SmoothL1 (Huber), Double DQN (online argmax / target τιμή, detached) για τους LSTM arms, replay από μνήμη, 16 διαδοχικές ενημερώσεις ανά replay, ένα replay ανά tick όταν η μνήμη $>16$. Παράθυρο ιστορικού 10 ticks για τα LSTM. Training 19968 ticks target (transfer: 9984 pretrain + 9984 finetune, συνολικά 19968). Πηγές: \ptr{tuning/legacy/\{network\_dense,networks\_lstm,agent\_lstm\_fixed,agent\_lstm\_v2,ddqnagent,c5\_protocol\}.py}, \ptr{tuning/rppo.py}, και τα JSON του batch S \ptr{tuning/results/cycle3/S/}.
\begin{table}[H]\centering\scriptsize\setlength{\tabcolsep}{3pt}\begin{tabular}{p{2.4cm}p{3.9cm}rp{1.1cm}rrrrp{1.4cm}}\toprule
Μοντέλο & Δίκτυο & params & lr & batch & γ & replay & n-step & target sync\\\midrule
DERP original & MLP 7-128-128-3 & 17.923 & $10^{-4}$ & 16 & 0.95 & 500 & -- & κάθε replay\\
DERP enhanced & MLP 70-128-128-3 & 25.987 & $10^{-4}$ & 16 & 0.95 & 500 & -- & κάθε replay\\
LSTM & 3×LSTM(128)+FC & 334.723 & $10^{-4}$ & 16 & 0.98 & 5000 & 2 & 100\\
LSTM+transfer & 3×LSTM(128)+FC & 334.723 & $10^{-4}$ & 16 & 0.98 & 5000 & 1 & 250\\
Dinos & LSTM128 → concat → 128 → 128 & 104.451 & $5\cdot10^{-5}$ & 16 & 0.98 & 5000 & 3 & 100\\
Dinos+Transfer V.2 & ίδιο με Dinos & 104.451 & $10^{-4}$ & 16 & 0.98 & 5000 & 5 & 250\\
RPPO / DRe-SCale & LSTM256 + MLP 64-64 (actor, critic) & 584.196 & $3\cdot10^{-4}$ & 128 & 0.99 & rollout 128 & -- & -- \\\bottomrule\end{tabular}
\caption{Σύνοψη. Πηγές: JSON του S (\texttt{hyperparameters}, \texttt{ddqn\_options}, \texttt{target\_sync\_replays}, \texttt{learning\_rate}), \ptr{ddqnagent.py:15-30}, \ptr{agent\_lstm\_fixed.py:1-16,153-154}, \ptr{rppo.py:1-13,44-45}. Το batch size των DQN arms είναι τα 16 δείγματα ανά replay (\ptr{run\_legacy.py:127}); το «batch» του RPPO είναι ολόκληρο το rollout των 128 βημάτων.}\end{table}

\subsection{DERP (original) --- \texttt{derp}}
Πυκνό δίκτυο: \texttt{fc1} Linear(7,128) → ReLU → \texttt{fc2} Linear(128,128) → ReLU → \texttt{fc3} Linear(128,3) (Q-τιμές των 3 δράσεων). Πλήρως συνδεδεμένα (fully connected), χωρίς μνήμη: βλέπει μόνο την τρέχουσα παρατήρηση. 17.923 παράμετροι. Αλγόριθμος: DDQN του αρχικού DInos (verbatim port), μνήμη 500, $\gamma=0.95$, Adam $10^{-4}$, SmoothL1, replay(16) κάθε tick. $\epsilon$: γραμμικά 1→0.01 σε 10k ticks (\texttt{linear10k}, \texttt{epsilon\_min}=0.01 στο JSON). Στόχος: $r+\gamma\max_a Q_{\text{target}}(s',a)$ όπως στο αρχικό· στο S δεν ενεργοποιείται double/n-step. Χωρίς transfer.

\subsection{DERP enhanced --- \texttt{derp\_hist10}}
Ίδιο δίκτυο, αλλά είσοδος η ισοπεδωμένη ιστορία 10 παρατηρήσεων (10×7=70): Linear(70,128)→ReLU→Linear(128,128)→ReLU→Linear(128,3), 25.987 παράμετροι. $\epsilon$: πολλαπλασιαστικά ×0.995 ανά replay (\texttt{eps\_schedule=original}), ελάχιστο 0.01. Άλλα ίδια με το DERP. Ασταθές στο S (SD 149,8k).

\subsection{LSTM --- \texttt{lstm\_scratch}, variant \texttt{fixed}}
Αναδρομικό δίκτυο (LSTM) \texttt{myLSTM}: είσοδος παράθυρο [10×7] → 3 στοιβαγμένα επίπεδα LSTM με 128 κρυφούς νευρώνες το καθένα (τα $h,c$ ξεκινούν από μηδέν σε κάθε παράθυρο) → η έξοδος του τελευταίου tick → Linear(128,3). Σύνδεση: μέσα στο κάθε επίπεδο οι νευρώνες συνδέονται με πύλες (input, forget, cell, output) και αναδρομικές συνδέσεις· τα επίπεδα συνδέονται σειριακά. 334.723 παράμετροι. Double DQN με n-step 2, $\gamma=0.98$, μνήμη 5000, 16 ενημερώσεις ανά replay, target sync κάθε 100 replays, lr $10^{-4}$, $\epsilon$ 1→0.05 γραμμικά σε 10k ticks.

\subsection{LSTM+transfer --- \texttt{dinos\_t}, variant \texttt{fixed}}
Ίδιο δίκτυο με το LSTM. Pretraining 9984 ticks στο \texttt{spike300\_d5} (cycle-1 περιβάλλον, ίδιο μέγεθος state), μετά finetune 9984 ticks στο \texttt{poisson\_ms\_spiky} με επανεκκίνηση $\epsilon$ (restart). n-step 1, target sync 250, lr $10^{-4}$. Ο αριθμός παραμέτρων είναι ίδιος (334.723).

\subsection{Dinos --- \texttt{lstm\_scratch}, variant \texttt{a1h}}
«Dinos V.2-H»: \texttt{window[10×7] → LSTM(7,128, 1 επίπεδο, μηδενικά $h,c$ ανά παράθυρο) → concat(τελευταία έξοδος[128], τελευταία παρατήρηση[7]) → Dense(135,128) ReLU → Dense(128,128) ReLU → Dense(128,3)} (πεδίο \texttt{architecture} του JSON). Δηλαδή ένα LSTM που συνοψίζει την ιστορία, ενώνεται (skip σύνδεση) με την τρέχουσα παρατήρηση και περνά από 3 πυκνά επίπεδα. 104.451 παράμετροι. Double DQN, n-step 3, $\gamma=0.98$, μνήμη 5000, 16 ενημερώσεις/replay, target sync 100 replays, Adam lr $5\cdot10^{-5}$, gradient clipping max-norm 10, $\epsilon$ 1→0.05 σε 10k ticks. Χωρίς pretraining. Σημείωση: το grad-clip ενεργοποιείται σχεδόν πάντα (clip\_frac 0,988 στο seed 19100, \ptr{c3S-dinos-s19100.json}, \texttt{grad\_norm}).

\subsection{Dinos+Transfer V.2 --- \texttt{dinos\_t}, variant \texttt{a1h}}
Ίδια αρχιτεκτονική με το Dinos (104.451 παράμετροι)· η διαφορά είναι στην εκπαίδευση: pretraining 9984 ticks στο ίδιο workload \texttt{poisson\_ms\_spiky}, μετά finetune 9984 ticks με restart του $\epsilon$ (συνολικά 19968)· n-step 5, target sync 250, lr $10^{-4}$, χωρίς grad-clip στο JSON (\texttt{hyperparameters}). Ονομασία πάντα «Dinos+Transfer V.2».

\subsection{RPPO / DRe-SCale --- \texttt{rppo}}
Recurrent PPO (native torch υλοποίηση, \ptr{tuning/rppo.py}, όπως οι προεπιλογές sb3\_contrib): δύο ξεχωριστά LSTM 256 νευρώνων (ένα για τον actor, ένα για τον critic, \texttt{lstm\_pi}, \texttt{lstm\_vf}, είσοδος 7), μετά MLP [64,64] με Tanh ανά κλάδο, κεφαλή πολιτικής Linear(64,3) (κατηγορική κατανομή) και κεφαλή τιμής Linear(64,1). 584.196 παράμετροι. Hyperparameters (JSON): n\_steps 128, batch 128 (ένα minibatch ανά rollout), n\_epochs 10, lr $3\cdot10^{-4}$ (Adam, eps $10^{-5}$), $\gamma=0.99$, GAE $\lambda=0.9$, clip 0.2, ent\_coef 0, vf\_coef 0.5, max\_grad\_norm 0.5, ορθογώνια αρχικοποίηση. On-policy· αξιολόγηση με greedy (argmax) πολιτική. Ασταθές στο S.

\section{Αναπαραγωγή και όρια}
Αριθμοί: \ptr{.lab/j442/summary.json}, \ptr{.lab/j438/summary.json}· σχήματα: \ptr{tools/j444/figs.py}, \ptr{tools/j444/build\_pdf.py}· eval-only runs: spec \ptr{.lab/j444/spec.json} (envelope cycle3, χωρίς training, μόνο val). Ένα training seed ανά μοντέλο στα σχήματα προσαρμογής· τα 20 val επεισόδια του return δεν έχουν καταγραφεί ανά tick. Άγνωστο/μη διαθέσιμο: τροχιά RPPO· CPU-seconds του launcher για τα εξωτερικά runs (\texttt{cpu\_seconds: None}).
\end{document}
"""
for a, b_ in [("→", "$\\to$"), ("×", "$\\times$"), ("≈", "$\\approx$"), ("−", "$-$"), ("≤", "$\\le$"), ("≥", "$\\ge$"), ("·", "\\textperiodcentered{}"), ("≠", "$\\neq$")]:
    T = T.replace(a, b_)
open(D + "report.tex", "w").write(T)
for _ in range(2):
    r = subprocess.run(["pdflatex", "-interaction=nonstopmode", "report.tex"], cwd=D, capture_output=True)
print(r.returncode, r.stdout[-400:].decode("utf8","ignore") if r.returncode else "ok")
