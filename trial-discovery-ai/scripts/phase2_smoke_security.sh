#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8002}"
COOKIE_FILE="$(mktemp)"
EMAIL="phase2_user_$(date +%s)@example.test"
PASSWORD="password123"
NEW_PASSWORD="newpassword123"

cleanup() {
  rm -f "$COOKIE_FILE"
}
trap cleanup EXIT

R_CODE=$(curl -sS -c "$COOKIE_FILE" -o /tmp/phase2_register.json -w '%{http_code}' \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" \
  "$BASE_URL/auth/register")

CSRF_TOKEN=$(awk '$6=="peregrine_csrf"{print $7}' "$COOKIE_FILE" | tail -n1)

NO_CSRF_CREATE=$(curl -sS -b "$COOKIE_FILE" -o /tmp/phase2_no_csrf.json -w '%{http_code}' \
  -H 'Content-Type: application/json' \
  -d '{"name":"Phase2 Missing CSRF"}' \
  "$BASE_URL/matters")

WITH_CSRF_CREATE=$(curl -sS -b "$COOKIE_FILE" -o /tmp/phase2_with_csrf.json -w '%{http_code}' \
  -H 'Content-Type: application/json' \
  -H "X-CSRF-Token: $CSRF_TOKEN" \
  -d '{"name":"Phase2 With CSRF"}' \
  "$BASE_URL/matters")

FORGOT_CODE=$(curl -sS -o /tmp/phase2_forgot.json -w '%{http_code}' \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\"}" \
  "$BASE_URL/auth/password/forgot")

RESET_TOKEN=$(python3 - <<'PY'
import json
from pathlib import Path
body = json.loads(Path('/tmp/phase2_forgot.json').read_text())
print(body.get('reset_token') or '')
PY
)

RESET_CODE=""
OLD_LOGIN_CODE=""
NEW_LOGIN_CODE=""
if [ -n "$RESET_TOKEN" ]; then
  RESET_CODE=$(curl -sS -o /tmp/phase2_reset.json -w '%{http_code}' \
    -H 'Content-Type: application/json' \
    -d "{\"token\":\"$RESET_TOKEN\",\"new_password\":\"$NEW_PASSWORD\"}" \
    "$BASE_URL/auth/password/reset")

  OLD_LOGIN_CODE=$(curl -sS -o /tmp/phase2_old_login.json -w '%{http_code}' \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" \
    "$BASE_URL/auth/login")

  NEW_LOGIN_CODE=$(curl -sS -o /tmp/phase2_new_login.json -w '%{http_code}' \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"$EMAIL\",\"password\":\"$NEW_PASSWORD\"}" \
    "$BASE_URL/auth/login")
fi

LAST_RATE_CODE=""
for _ in $(seq 1 11); do
  LAST_RATE_CODE=$(curl -sS -o /tmp/phase2_rate.json -w '%{http_code}' \
    -H 'Content-Type: application/json' \
    -H 'X-Forwarded-For: 192.0.2.200' \
    -d '{"email":"nobody@example.test","password":"wrong"}' \
    "$BASE_URL/auth/login")
done

python3 - <<'PY'
import json
from pathlib import Path

register = json.loads(Path('/tmp/phase2_register.json').read_text())
no_csrf = json.loads(Path('/tmp/phase2_no_csrf.json').read_text())
with_csrf = json.loads(Path('/tmp/phase2_with_csrf.json').read_text())
forgot = json.loads(Path('/tmp/phase2_forgot.json').read_text())

assert register.get('user', {}).get('email'), register
assert no_csrf.get('detail') == 'CSRF token missing or invalid', no_csrf
assert with_csrf.get('id'), with_csrf
assert forgot.get('status') == 'ok', forgot

print('Phase2 security smoke: PASS')
PY

if [ "$R_CODE" != "200" ] || [ "$NO_CSRF_CREATE" != "403" ] || [ "$WITH_CSRF_CREATE" != "200" ] || [ "$FORGOT_CODE" != "200" ]; then
  echo "phase2 smoke failed: register=$R_CODE no_csrf=$NO_CSRF_CREATE with_csrf=$WITH_CSRF_CREATE forgot=$FORGOT_CODE"
  exit 1
fi

if [ -n "$RESET_TOKEN" ]; then
  if [ "$RESET_CODE" != "200" ] || [ "$OLD_LOGIN_CODE" != "401" ] || [ "$NEW_LOGIN_CODE" != "200" ]; then
    echo "phase2 reset flow failed: reset=$RESET_CODE old_login=$OLD_LOGIN_CODE new_login=$NEW_LOGIN_CODE"
    exit 1
  fi
fi

if [ "$LAST_RATE_CODE" != "429" ]; then
  echo "phase2 rate limit failed: expected 429, got $LAST_RATE_CODE"
  exit 1
fi

echo "codes register=$R_CODE no_csrf=$NO_CSRF_CREATE with_csrf=$WITH_CSRF_CREATE forgot=$FORGOT_CODE reset=$RESET_CODE old_login=$OLD_LOGIN_CODE new_login=$NEW_LOGIN_CODE rate_last=$LAST_RATE_CODE"
