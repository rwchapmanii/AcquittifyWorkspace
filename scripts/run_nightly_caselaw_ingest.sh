#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

ENV_FILE="${ACQUITTIFY_ENV_FILE:-$HOME/.acquittify_env}"
if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck source=/dev/null
  . "${ENV_FILE}"
  set +a
fi

PYTHON="${ACQ_CASELAW_PYTHON:-}"
if [[ -z "${PYTHON}" ]]; then
  PYTHON="${ROOT}/.venv/bin/python"
  if [[ ! -x "${PYTHON}" ]]; then
    PYTHON="python3"
  fi
fi

RUNTIME_HOURS="${ACQ_CASELAW_RUNTIME_HOURS:-6}"
LOG_PATH="${ACQ_CASELAW_LOG_PATH:-${ROOT}/reports/caselaw_nightly_ingest.jsonl}"
VALIDATION_INPUT_DIR="${ACQ_NEO4J_VALIDATION_INPUT_DIR:-}"
VALIDATION_GLOB="${ACQ_NEO4J_VALIDATION_GLOB:-**/*.*}"
VALIDATION_JSON="${ACQ_NEO4J_VALIDATION_JSON:-${ROOT}/reports/nightly_neo4j_extraction_validation.json}"
VALIDATION_MD="${ACQ_NEO4J_VALIDATION_MD:-${ROOT}/reports/nightly_neo4j_extraction_validation.md}"
AUTONOMY_POLICY="${ACQ_ONTOLOGY_AUTONOMY_POLICY:-${ROOT}/acquittify/ontology/neo4j/policies/acquittify_autonomy_policy_v1_2026-03-08.yaml}"
AUTONOMY_JSON="${ACQ_ONTOLOGY_AUTONOMY_JSON:-${ROOT}/reports/nightly_ontology_autonomy_decision.json}"
AUTONOMY_MD="${ACQ_ONTOLOGY_AUTONOMY_MD:-${ROOT}/reports/nightly_ontology_autonomy_decision.md}"

set +e
"${PYTHON}" "${ROOT}/scripts/nightly_caselaw_ingest.py" \
  --max-runtime-hours "${RUNTIME_HOURS}" \
  --log-path "${LOG_PATH}" \
  "$@"
ingest_status=$?
set -e

if [[ ${ingest_status} -ne 0 ]]; then
  exit "${ingest_status}"
fi

if [[ -n "${VALIDATION_INPUT_DIR}" ]]; then
  "${PYTHON}" "${ROOT}/scripts/nightly_neo4j_extraction_validate.py" \
    --input-dir "${VALIDATION_INPUT_DIR}" \
    --glob "${VALIDATION_GLOB}" \
    --output-json "${VALIDATION_JSON}" \
    --output-md "${VALIDATION_MD}"

  if [[ -f "${AUTONOMY_POLICY}" ]]; then
    "${PYTHON}" "${ROOT}/scripts/evaluate_ontology_autonomy_policy.py" \
      --policy "${AUTONOMY_POLICY}" \
      --validation-report "${VALIDATION_JSON}" \
      --output-json "${AUTONOMY_JSON}" \
      --output-md "${AUTONOMY_MD}"
  fi
fi
