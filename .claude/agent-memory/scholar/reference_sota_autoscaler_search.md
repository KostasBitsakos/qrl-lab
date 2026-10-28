---
name: sota-autoscaler-search
description: 2026-10-22 verified findings for the SOTA autoscaler baseline search (DRe-SCale, AWARE, gym-hpa, Lipari) plus working lookup tricks
metadata:
  type: reference
---

Full report: docs/related_work_sota_autoscaler.md. Recommended baseline: DRe-SCale LSTM-PPO (Agarwal/Rodriguez/Buyya, IEEE TSC 2024, DOI 10.1109/TSC.2024.3387661, github.com/SidAg26/DRe-SCale Apache-2.0). Live OpenFaaS only, code has unrendered ${...} placeholders, so port = re-implementation. Its DRQN is not a true DDQN.
- AWARE (ATC23): DDPG + biRNN meta-learner, replicas+limits, 60-day meta-training; code gitlab.engr.illinois.edu/DEPEND/aware (host refuses connections from VM, unopened).
- gym-hpa: github.com/jpedro1992/gym-hpa, license NOASSERTION, sim = CSV replay (Zenodo 7944661, other-nc); extension paper NOMS 2025 (10.1109/NOMS57970.2025.11073717).
- Lipari et al. IPDPSW 2025 (10.1109/IPDPSW66978.2025.00169) = DDQN+LSTM forecaster, nearest prior art; repo alfredoLipari/CustomAutoscaler-k8s.
- RLScale-Bench arXiv 2605.26418: calibrated HPA beats 6 DRL (preprint). COLA has no venue on arXiv page; do not call it SoCC.

Tool tricks that work (2026-10-22): WebFetch of https://r.jina.ai/<public pdf url> returns readable PDF text (USENIX, arXiv, imec, IEEE abstract pages). api.openalex.org works for titles, citation counts, venue-filtered search (CCGrid source ids S7407086095, S4363606989). api.github.com repo/tree/search works. DBLP blocked (Anubis), Semantic Scholar 429, gitlab.engr.illinois.edu ECONNREFUSED, Read tool cannot render PDFs (no pdftoppm).
