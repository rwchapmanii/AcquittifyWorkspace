#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TRIAL_DIR="$ROOT_DIR/trial-discovery-ai"
COMPOSE_FILE="$TRIAL_DIR/deploy/docker-compose.phase3.yml"
PROJECT_NAME="acq_phase3_local"

if ! docker info >/dev/null 2>&1; then
  echo "Docker daemon is not running. Start Docker Desktop and retry."
  exit 1
fi

echo "[1/8] Stopping prior Phase 3 stack (if running)..."
docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" down >/dev/null 2>&1 || true

echo "[2/8] Starting infrastructure services..."
docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" up -d postgres redis minio minio_init

echo "[3/8] Building application images..."
docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" build api worker frontend

echo "[4/8] Running database migrations in container..."
docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" run --rm migrate

echo "[5/8] Starting API, worker, and frontend..."
docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" up -d api worker frontend

echo "[6/8] Waiting for API and frontend health..."
for _ in $(seq 1 60); do
  if curl -sf http://127.0.0.1:58002/healthz >/dev/null 2>&1 && curl -sf http://127.0.0.1:53000 >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

if ! curl -sf http://127.0.0.1:58002/healthz >/dev/null 2>&1; then
  echo "API did not become healthy on http://127.0.0.1:58002/healthz"
  docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" logs api --tail=120
  exit 1
fi

if ! curl -sf http://127.0.0.1:53000 >/dev/null 2>&1; then
  echo "Frontend did not become healthy on http://127.0.0.1:53000"
  docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" logs frontend --tail=120
  exit 1
fi

echo "[7/8] Running security smoke checks against containerized API..."
"$TRIAL_DIR/scripts/phase1_smoke_auth.sh" "http://127.0.0.1:58002"
"$TRIAL_DIR/scripts/phase2_smoke_security.sh" "http://127.0.0.1:58002"

echo "[8/8] Phase 3 local activation complete."
echo "Frontend: http://127.0.0.1:53000"
echo "API:      http://127.0.0.1:58002"

echo "To stop: docker compose -f $COMPOSE_FILE -p $PROJECT_NAME down"
