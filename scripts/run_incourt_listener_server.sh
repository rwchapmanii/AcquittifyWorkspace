#!/usr/bin/env bash
set -euo pipefail

HOST="${INCOURT_SERVER_HOST:-127.0.0.1}"
PORT="${INCOURT_SERVER_PORT:-8777}"
PYTHON=".venv-incourt/bin/python"
if [[ ! -x "${PYTHON}" ]]; then
  PYTHON=".venv/bin/python"
fi
if [[ ! -x "${PYTHON}" ]]; then
  PYTHON="python3"
fi

exec "${PYTHON}" -m uvicorn incourt_listener.streaming_server:app --host "${HOST}" --port "${PORT}"
