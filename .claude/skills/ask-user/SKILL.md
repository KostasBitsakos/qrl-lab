---
name: ask-user
description: File a question, proposal or approval request for the researcher in the dashboard inbox and notify their phone. Use whenever a decision belongs to the researcher (PLAN §6), when a council card is ready, or when a fact is missing. Never continue a blocking item without an approve.
---

# Ask the researcher

1. Write the body in Markdown to a temporary file (Greek for the researcher, technical terms in English):
   what you need, why now, the options, your recommendation, cost (CPU-h / QPU-s / days / tokens), links
   to evidence (run ids, council folder, file paths). Under 250 words.
2. File it:
   ```bash
   python3 tools/labq.py ask --kind approval|question|proposal|info \
     --title "<short title>" --body-file <file> [--options approve,reject,changes] [--blocking] [--cost "<text>"]
   ```
   The command prints the request id (`R-...`).
3. If `--blocking`, or the request unblocks a batch, call `PushNotification` with one line:
   `"[QRL] <title> — περιμένει απόφαση (R-...)"`. Do not push for `info`.
4. Continue with work that does not depend on the answer. The answer arrives as an inbox notification
   (`reply_to` = the request id). `python3 tools/labq.py pending` lists open requests.

Never treat silence, a comment, or an approval of a different request as approval.
