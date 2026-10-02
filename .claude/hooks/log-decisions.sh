#!/usr/bin/env bash
# Stop hook: log the decisions from the turn that just ended into DECISIONS.md.
# Runs async (see .claude/settings.json), so the session never waits for it.
# Turn off: touch .claude/decision-logger/disabled

# The headless logger is itself a Claude session; never let it trigger another logger.
[ "${DECISION_LOGGER_CHILD:-}" = "1" ] && exit 0

exec python3 "$(dirname "$0")/decision_logger.py"
