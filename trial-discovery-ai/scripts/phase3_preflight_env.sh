#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEFAULT_ENV="$ROOT_DIR/trial-discovery-ai/backend/.env"
if [ ! -f "$DEFAULT_ENV" ]; then
  DEFAULT_ENV="$ROOT_DIR/trial-discovery-ai/.env.example"
fi
ENV_FILE="${1:-$DEFAULT_ENV}"

if [ ! -f "$ENV_FILE" ]; then
  echo "Env file not found: $ENV_FILE"
  exit 1
fi

required=(
  DATABASE_URL
  REDIS_URL
  MINIO_BUCKET
  S3_ACCESS_KEY_ID
  S3_SECRET_ACCESS_KEY
  AUTH_SECRET_KEY
  CORS_ALLOW_ORIGINS
)

get_value() {
  local key="$1"
  local value
  value=$(grep -E "^${key}=" "$ENV_FILE" | tail -n1 | cut -d= -f2- || true)
  printf "%s" "$value"
}

missing=0
for key in "${required[@]}"; do
  value="$(get_value "$key")"
  if [ -z "$value" ]; then
    echo "MISSING: $key"
    missing=1
  fi
done

if [ "$missing" -ne 0 ]; then
  echo "Preflight failed: set missing values in $ENV_FILE"
  exit 1
fi

secret="$(get_value AUTH_SECRET_KEY)"
cookie_secure="$(get_value AUTH_COOKIE_SECURE)"
reset_dev_token="$(get_value AUTH_PASSWORD_RESET_DEV_RETURN_TOKEN)"
cookie_secure_lc="$(printf '%s' "$cookie_secure" | tr '[:upper:]' '[:lower:]')"
reset_dev_token_lc="$(printf '%s' "$reset_dev_token" | tr '[:upper:]' '[:lower:]')"

if [ "$secret" = "change-this-in-production" ] || [ "$secret" = "replace_with_long_random_secret" ]; then
  echo "FAIL: AUTH_SECRET_KEY is still set to a placeholder"
  exit 1
fi

if [ "$cookie_secure_lc" != "true" ]; then
  echo "WARN: AUTH_COOKIE_SECURE should be true in production"
fi

if [ "$reset_dev_token_lc" = "true" ]; then
  echo "WARN: AUTH_PASSWORD_RESET_DEV_RETURN_TOKEN should be false in production"
fi

echo "Phase 3 preflight passed for $ENV_FILE"
