#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TRIAL_DIR="$ROOT_DIR/trial-discovery-ai"
BACKEND_DIR="$TRIAL_DIR/backend"
COMPOSE_FILE="$ROOT_DIR/docker-compose.peregrine.yml"

if ! docker info >/dev/null 2>&1; then
  echo "Docker daemon is not running. Start Docker Desktop and retry."
  exit 1
fi

echo "[1/4] Starting local infra (Postgres/Redis/MinIO)..."
cd "$ROOT_DIR"
docker compose -f "$COMPOSE_FILE" up -d postgres redis minio minio_init

echo "[2/4] Waiting for Postgres on port 55432..."
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

echo "[3/4] Running DB migrations..."
cd "$BACKEND_DIR"
DATABASE_URL="$(grep '^DATABASE_URL=' .env | cut -d= -f2-)" PYTHONPATH=. ./.venv/bin/alembic upgrade head

echo "[4/4] Starting backend and running auth+tenant smoke test..."
AUTH_SECRET_KEY="${AUTH_SECRET_KEY:-local-dev-secret-change-me}" \
DATABASE_URL="$(grep '^DATABASE_URL=' .env | cut -d= -f2-)" \
PYTHONPATH=. \
./.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8002 >/tmp/phase1_uvicorn.log 2>&1 &
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
  echo "Backend did not become ready. Check /tmp/phase1_uvicorn.log"
  exit 1
fi

"$TRIAL_DIR/scripts/phase1_smoke_auth.sh" "http://127.0.0.1:8002"

echo "Phase 1 local activation completed."
