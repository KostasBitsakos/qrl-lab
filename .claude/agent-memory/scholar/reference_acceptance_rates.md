---
name: acceptance-rates
description: Verified acceptance-rate sources for CCGrid, SIGMETRICS, PDP (2024-2026) and dead ends, as of 2026-10-17
metadata:
  type: reference
---

- CCGrid: only source is table on https://clouds.cis.unimelb.edu.au/~rbuyya/ccgrid/ (secondary): 2023 58/275, 2024 51/194 (26.3%), 2025 55/219 (25%), 2026 blank.
- SIGMETRICS: per-cycle counts from POMACS editorials via https://api.crossref.org/works/10.1145/<doi> (WebFetch works; 429 -> retry). Winter 2025 (3727107) and winter 2026 (3805623) editorials have NO counts. DOIs: 2026 3771560(summer 23/111), 3788083(fall 25/149); 2025 3700411(20/110), 3711694(14/113); 2024 3626773(20/91), 3639027(18/118), 3656013(10/127).
- PDP: no counts found for 2024-26 (IEEE Xplore 418, ACM DL 403, pdp2024.org hijacked redirect: do not follow). Only PDP 2010 (28.1%) and 2020 (120 submissions) seen.
- Crossref list query trick: api.crossref.org/works?query.title=POMACS+Editorial&filter=container-title:...
