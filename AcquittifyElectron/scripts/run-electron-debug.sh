#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${HOME}/Library/Application Support/acquittifyelectron"
LOG_FILE="${LOG_DIR}/acquittify.startup.log"
EXTRA_ARGS=()

if [[ "${1:-}" == "--allow-multi-instance" ]]; then
  EXTRA_ARGS=(-- --allow-multi-instance)
fi

echo "Stopping running AcquittifyElectron dev processes..."
pkill -f "${ROOT_DIR}/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron" >/dev/null 2>&1 || true
pkill -f "${ROOT_DIR}/node_modules/.bin/electron" >/dev/null 2>&1 || true

mkdir -p "${LOG_DIR}"
echo "Startup log: ${LOG_FILE}"
echo "Starting AcquittifyElectron (dev) with logging..."

cd "${ROOT_DIR}"
if (( ${#EXTRA_ARGS[@]} )); then
  ELECTRON_ENABLE_LOGGING=1 ELECTRON_ENABLE_STACK_DUMPING=1 ACQUITTIFY_STARTUP_LOG=1 ACQUITTIFY_SKIP_OBSIDIAN_DISCOVERY=1 ACQUITTIFY_SKIP_VAULT_DISCOVERY=1 npm start "${EXTRA_ARGS[@]}"
else
  ELECTRON_ENABLE_LOGGING=1 ELECTRON_ENABLE_STACK_DUMPING=1 ACQUITTIFY_STARTUP_LOG=1 ACQUITTIFY_SKIP_OBSIDIAN_DISCOVERY=1 ACQUITTIFY_SKIP_VAULT_DISCOVERY=1 npm start
fi
