#!/usr/bin/env bash
# Starts ONE new Claude Code session that finishes the v0.3 upgrade on this VM: tests (and fixes), conflicts,
# experiment registry, STATE.md, index, install (with your OK). It stops before the switch, which stays yours.
# Never --continue/--resume an old coordinator session: it would reload its whole history.
cd "$(dirname "$0")/.." || exit 1
if ! command -v claude >/dev/null 2>&1; then source "$HOME/.nvm/nvm.sh"; fi
command -v claude >/dev/null 2>&1 || { echo "Δεν βρέθηκε το claude (source ~/.nvm/nvm.sh)"; exit 1; }
[ -f prompts/upgrade_v03.md ] || { echo "Λείπει το prompts/upgrade_v03.md"; exit 1; }
echo "QRL-Lab v0.3: νέα συνεδρία αναβάθμισης. Απάντα στις ερωτήσεις της· όταν τελειώσει, γράψε /exit."
exec claude -n "qrl-v03-upgrade" "$(cat prompts/upgrade_v03.md)"
