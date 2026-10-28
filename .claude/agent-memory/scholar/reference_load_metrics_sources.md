---
name: load-metrics-sources
description: Verified sources (2026-10-17) on load vs latency/CPU/memory/scale-out for Redis/K8s and where verification tooling failed
metadata:
  type: reference
---

Verified set is in /home/ubuntu/qrl-lab/paper/notes/load_metrics_literature.md and paper/refs.bib (keys li2014tales, atikoglu2012workload, kulkarni2017rocksteady, shahrad2020serverless, luo2021alibaba, whitt2006fluid, zhou2023ahpa, redisdocs_*, redisblog2026asm, k8sdocs_hpa, ...).

Tool quirks: WebFetch cannot decode PDFs (FlateDecode garbage) and there is no Bash/pdftotext, so full-text claims need an HTML source (ar5iv.labs.arxiv.org works for arXiv papers); abstracts via api.semanticscholar.org/graph/v1/paper/DOI:<doi>?fields=abstract (null for ACM). Crossref API returns 429 when hit in parallel; query.bibliographic works for title lookup. Never guess a DOI: a guessed Springer DOI returned an unrelated paper.

Pass 2 (2026-10-17, paper/notes/sim_realism_review.md): added mansouri2022fragmented (Redis 8 nodes <= 2x of 2 nodes, theta<1 hint), sivko2022coroot (HPA 2m05s vs 30s with metrics resolution), zhang2025kiss, calheiros2011cloudsim (metadata only). UNVERIFIED, not in bib: Erlang EuroSys24 (10.1145/3627703.3650084; ACM 403, PDF unreadable), Rabl PVLDB12 Redis claim, Bodra 2510.08863. Semantic Scholar API gives 429 often; ar5iv works for arXiv HTML (not all ids).

Known gaps: no peer-reviewed Redis queueing model; no peer-reviewed Redis Cluster resharding measurement (only Redis 8.4 vendor blog, ElastiCache docs); Atikoglu/Mi/Urdaneta/Bodik full texts not read.
