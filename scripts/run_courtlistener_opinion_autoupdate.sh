#!/usr/bin/env bash
set -euo pipefail

LOG_PATH="${1:-/tmp/courtlistener_opinion_autoupdate.log}"
PYTHON=".venv/bin/python"
if [[ ! -x "${PYTHON}" ]]; then
  PYTHON="python3"
fi

nohup "${PYTHON}" scripts/courtlistener_opinion_autoupdate.py >> "${LOG_PATH}" 2>&1 &
echo $!
