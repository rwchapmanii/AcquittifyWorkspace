#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <COURTLISTENER_API_TOKEN>" >&2
  exit 1
fi

TOKEN="$1"
ENV_FILE="${ACQUITTIFY_ENV_FILE:-$HOME/.acquittify_env}"
PLIST="$HOME/Library/LaunchAgents/com.acquittify.courtlistener.opinion.autoupdate.plist"

{
  echo "export COURTLISTENER_API_TOKEN=\"${TOKEN}\""
} > "${ENV_FILE}"

launchctl bootout "gui/$(id -u)" "${PLIST}" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "${PLIST}"

echo "Token saved to ${ENV_FILE} and LaunchAgent restarted."
