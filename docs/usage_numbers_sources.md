# Dashboard numbers: where each one comes from (J228, M-20261030-063)

| Where | Number | Source | Status |
|---|---|---|---|
| Sidebar ring Claude 5ω / 7ημ | used % and reset time | `statusLine` stdin `rate_limits` → `.lab/usage/claude.json` (`tools/claude_statusline.py`); a rejection in `dispatch.db` overrides to 100 % | measured; shows observation time, old readings dimmed «~N» |
| Sidebar ring Codex 5h / 7d | used % and reset time | `~/.codex/sessions/**/rollout-*.jsonl`, `token_count.rate_limits` | measured, as of the latest turn |
| «Tokens consumed / remaining» in absolute numbers | — | Claude does not expose absolute quotas, only %; Codex likewise | **not available** (we show %, never invent tokens) |
| 💳 purchased credits | spent / remaining $ | session cost from the statusline | labelled ΕΚΤΙΜΗΣΗ (may differ from billing) |
| Token card, «μετρημένα» line (new) | tasks, input, cached, cache-write, output per provider, 24 h | `tasks.*` in `.lab/dispatch.db` = CLI result JSON (`tools/token_metrics.dispatcher_usage`) | measured, dispatcher jobs only (not interactive sessions, not the account total) |
| Token card, «−X %» bars | CLAUDE.md / AGENTS.md size vs backup 28/10; INDEX excerpt vs index | file sizes (stat) | bytes exact; «tokens» = bytes/4, labelled **εκτίμηση** |
| Total tokens saved by architecture / extensions | — | no counterfactual measurement exists. `dashboard/token_savings.json` holds assumed per-event numbers and is shown nowhere | **unknown**, not displayed |

Removed (J228): «δωρεάν resets / προσφορές» (`docs/free_offers.json` was empty) and «ειδοποιήσεις ορίων» (only rolling-window
«νέο παράθυρο» events and 2 unverified false positives). `tools/offers_watch.py` may still be scheduled; if so it can be stopped.
