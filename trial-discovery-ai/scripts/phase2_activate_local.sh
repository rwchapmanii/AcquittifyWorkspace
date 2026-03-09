#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TRIAL_DIR="$ROOT_DIR/trial-discovery-ai"
BACKEND_DIR="$TRIAL_DIR/backend"
FRONTEND_DIR="$TRIAL_DIR/frontend"
COMPOSE_FILE="$ROOT_DIR/docker-compose.peregrine.yml"

if ! docker info >/dev/null 2>&1; then
  echo "Docker daemon is not running. Start Docker Desktop and retry."
  exit 1
fi

echo "[1/7] Starting local infra (Postgres/Redis/MinIO)..."
cd "$ROOT_DIR"
docker compose -f "$COMPOSE_FILE" up -d postgres redis minio minio_init

echo "[2/7] Waiting for Postgres on port 55432..."
for _ in $(seq 1 30); do
  if nc -z localhost 55432 >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
if ! nc -z localhost 55432 >/dev/null 2>&1; then
  echo "Postgres did not become reachable on localhost:55432"
  exit 1
fi

echo "[3/7] Running DB migrations..."
cd "$BACKEND_DIR"
DATABASE_URL="$(grep '^DATABASE_URL=' .env | cut -d= -f2-)" PYTHONPATH=. ./.venv/bin/alembic upgrade head

echo "[4/7] Installing backend test extras (if needed)..."
if ! ./.venv/bin/python -c "import pytest" >/dev/null 2>&1; then
  ./.venv/bin/pip install -e '.[dev]'
fi

echo "[5/7] Running backend integration tests..."
DATABASE_URL="$(grep '^DATABASE_URL=' .env | cut -d= -f2-)" \
AUTH_SECRET_KEY="${AUTH_SECRET_KEY:-local-dev-secret-change-me}" \
AUTH_PASSWORD_RESET_DEV_RETURN_TOKEN=true \
PYTHONPATH=. \
./.venv/bin/python -m pytest tests/test_auth_security.py -q

echo "[6/7] Starting backend and running Phase 1 + Phase 2 smoke tests..."
AUTH_SECRET_KEY="${AUTH_SECRET_KEY:-local-dev-secret-change-me}" \
AUTH_PASSWORD_RESET_DEV_RETURN_TOKEN=true \
DATABASE_URL="$(grep '^DATABASE_URL=' .env | cut -d= -f2-)" \
PYTHONPATH=. \
./.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8002 >/tmp/phase2_uvicorn.log 2>&1 &
UVICORN_PID=$!

cleanup() {
  if ps -p "$UVICORN_PID" >/dev/null 2>&1; then
    kill "$UVICORN_PID" >/dev/null 2>&1 || true
    wait "$UVICORN_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

for _ in $(seq 1 30); do
  if curl -sf http://127.0.0.1:8002/healthz >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
if ! curl -sf http://127.0.0.1:8002/healthz >/dev/null 2>&1; then
  echo "Backend did not become ready. Check /tmp/phase2_uvicorn.log"
  exit 1
fi

"$TRIAL_DIR/scripts/phase1_smoke_auth.sh" "http://127.0.0.1:8002"
"$TRIAL_DIR/scripts/phase2_smoke_security.sh" "http://127.0.0.1:8002"

echo "[7/7] Building frontend..."
cd "$FRONTEND_DIR"
npm run build

echo "Phase 2 local activation completed."
