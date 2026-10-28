---
name: hpa-sources
description: Verified HPA facts (2026-10-17) and where they are; spec at docs/hpa_spec.md
metadata:
  type: reference
---

Spec written to /home/ubuntu/qrl-lab/docs/hpa_spec.md from k8s v1.34.0 code (pkg/controller/podautoscaler) + docs/flags pages. Flag defaults: sync 15s, tolerance 0.1, cpu-init 5m, initial-readiness 30s, downscale-stabilization 5m. Per-HPA tolerance: alpha-era v1.33, docs say stable v1.37.
Tool quirk: WebFetch is summarizing (not verbatim); ask for short exact lines, use offset for long pages (docs >100k chars). Unread: tags after v1.34.0, metric.Window value.
