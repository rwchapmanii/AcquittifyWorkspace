#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8002}"
TMP1="$(mktemp)"
TMP2="$(mktemp)"
U1="phase1_user_$(date +%s)"
U2="phase1_user2_$(date +%s)"
MNAME="Phase1 Matter $(date +%s)"

cleanup() {
  rm -f "$TMP1" "$TMP2"
}
trap cleanup EXIT

UNAUTH_CODE=$(curl -sS -o /tmp/phase1_unauth.json -w '%{http_code}' "$BASE_URL/matters")
R1_CODE=$(curl -sS -c "$TMP1" -o /tmp/phase1_r1.json -w '%{http_code}' -H 'Content-Type: application/json' -d "{\"email\":\"$U1\",\"password\":\"password123\"}" "$BASE_URL/auth/register")
CSRF1=$(awk '$6=="peregrine_csrf"{print $7}' "$TMP1" | tail -n1)
ME1_CODE=$(curl -sS -b "$TMP1" -o /tmp/phase1_me1.json -w '%{http_code}' "$BASE_URL/auth/me")
C1_CODE=$(curl -sS -b "$TMP1" -o /tmp/phase1_cm.json -w '%{http_code}' -H 'Content-Type: application/json' -H "X-CSRF-Token: $CSRF1" -d "{\"name\":\"$MNAME\"}" "$BASE_URL/matters")
L1_CODE=$(curl -sS -b "$TMP1" -o /tmp/phase1_l1.json -w '%{http_code}' "$BASE_URL/matters")
R2_CODE=$(curl -sS -c "$TMP2" -o /tmp/phase1_r2.json -w '%{http_code}' -H 'Content-Type: application/json' -d "{\"email\":\"$U2\",\"password\":\"password123\",\"organization_name\":\"Org Two\"}" "$BASE_URL/auth/register")
L2_CODE=$(curl -sS -b "$TMP2" -o /tmp/phase1_l2.json -w '%{http_code}' "$BASE_URL/matters")

python3 - <<'PY'
import json
from pathlib import Path

def read(path):
    return json.loads(Path(path).read_text())

unauth = read('/tmp/phase1_unauth.json')
r1 = read('/tmp/phase1_r1.json')
me1 = read('/tmp/phase1_me1.json')
cm = read('/tmp/phase1_cm.json')
l1 = read('/tmp/phase1_l1.json')
r2 = read('/tmp/phase1_r2.json')
l2 = read('/tmp/phase1_l2.json')

matter_id = cm.get('id')
list1_ids = {m.get('id') for m in l1.get('matters', [])}
list2_ids = {m.get('id') for m in l2.get('matters', [])}

assert unauth.get('detail') == 'Authentication required'
assert r1.get('user', {}).get('email')
assert me1.get('user', {}).get('email') == r1.get('user', {}).get('email')
assert matter_id in list1_ids
assert matter_id not in list2_ids
assert r1.get('organization', {}).get('id') != r2.get('organization', {}).get('id')

print('Phase1 auth/tenant smoke: PASS')
print('created_matter_id', matter_id)
print('user1_org', r1.get('organization', {}).get('name'))
print('user2_org', r2.get('organization', {}).get('name'))
PY

echo "codes unauth=$UNAUTH_CODE r1=$R1_CODE me1=$ME1_CODE create=$C1_CODE list1=$L1_CODE r2=$R2_CODE list2=$L2_CODE"
