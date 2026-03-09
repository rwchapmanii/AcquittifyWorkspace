#!/bin/bash
set -euo pipefail

# Canonical launcher:
# 1) Prefer installed /Applications bundle (single stable runtime)
# 2) Fallback to local dev Electron only if app bundle is missing

DEV_APP_DIR="$HOME/Desktop/Acquittify/AcquittifyElectron"
APP_BUNDLE="/Applications/Acquittify.app"

# Avoid duplicate windows: kill any lingering dev-mode Electron instance.
pkill -f "AcquittifyElectron/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron \\." >/dev/null 2>&1 || true

if [ -d "$APP_BUNDLE" ]; then
  open -a "$APP_BUNDLE"
  exit 0
fi

if [ -f "$DEV_APP_DIR/package.json" ] && [ -d "$DEV_APP_DIR/node_modules" ]; then
  cd "$DEV_APP_DIR"
  npm run start
  exit 0
fi

echo "No runnable Acquittify app found."
echo "Expected local source app at: $DEV_APP_DIR"
echo "or installed app bundle at: $APP_BUNDLE"
exit 1
