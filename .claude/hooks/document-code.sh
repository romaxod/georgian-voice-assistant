#!/usr/bin/env bash
# Stop hook: rewrite docs/code/<path>.md for every code file whose content changed this turn.
# Runs async (see .claude/settings.json), so the session never waits for it.
# Turn off: touch .claude/code-docs/disabled

# The documenter is itself a Claude session; never let it trigger another hook run.
[ "${DECISION_LOGGER_CHILD:-}" = "1" ] && exit 0

cat > /dev/null  # the hook's JSON on stdin isn't needed: changes are found by content hash
exec python3 "$(dirname "$0")/code_docs.py"
