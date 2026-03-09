#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INGEST_SCRIPT="$ROOT/scripts/ingest_6th_circuit_findlaw_obsidian.py"
LOG_DIR="$ROOT/reports"
OBSIDIAN_ROOT="${ACQUITTIFY_OBSIDIAN_ROOT:-$HOME/AcquittifyData/Obsidian}"

mkdir -p "$LOG_DIR"

# Wait for any active 6th-circuit ingest invocation of this script.
SIXTH_PATTERN="ingest_6th_circuit_findlaw_obsidian.py --court-slug us-6th-circuit"

# Stabilized network settings used after overnight full-speed failures.
REQ_INTERVAL="0.1"
REQ_JITTER="0.05"
TIMEOUT_SECONDS="20"
FETCH_MAX_ATTEMPTS="6"
FETCH_RETRY_BACKOFF="0.5"

printf '[%s] Waiting for active 6th Circuit ingest to finish...\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')"
while pgrep -f -- "$SIXTH_PATTERN" >/dev/null 2>&1; do
  printf '[%s] 6th Circuit ingest still running.\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')"
  sleep 60
done
printf '[%s] 6th Circuit ingest complete. Starting remaining circuits.\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')"

# Order requested by user: start with D.C. Circuit, then the remainder.
CIRCUITS=(
  "us-dc-circuit|D.C. Circuit"
  "us-1st-circuit|1st Circuit"
  "us-2nd-circuit|2nd Circuit"
  "us-3rd-circuit|3rd Circuit"
  "us-4th-circuit|4th Circuit"
  "us-5th-circuit|5th Circuit"
  "us-7th-circuit|7th Circuit"
  "us-8th-circuit|8th Circuit"
  "us-9th-circuit|9th Circuit"
  "us-10th-circuit|10th Circuit"
  "us-11th-circuit|11th Circuit"
)

for item in "${CIRCUITS[@]}"; do
  slug="${item%%|*}"
  vault_name="${item##*|}"
  log_path="$LOG_DIR/findlaw_${slug}_recovery_$(date '+%Y%m%d_%H%M%S').log"

  printf '[%s] Starting %s (%s). Log: %s\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')" "$vault_name" "$slug" "$log_path"
  python3 -u "$INGEST_SCRIPT" \
    --court-slug "$slug" \
    --vault-path "$OBSIDIAN_ROOT/$vault_name" \
    --since-year 2010 \
    --request-interval-seconds "$REQ_INTERVAL" \
    --request-jitter-seconds "$REQ_JITTER" \
    --timeout-seconds "$TIMEOUT_SECONDS" \
    --fetch-max-attempts "$FETCH_MAX_ATTEMPTS" \
    --fetch-retry-backoff-seconds "$FETCH_RETRY_BACKOFF" \
    2>&1 | tee "$log_path"

  printf '[%s] Completed %s (%s).\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')" "$vault_name" "$slug"
done

printf '[%s] All requested circuits completed.\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')"
