#!/usr/bin/env bash
set -euo pipefail

uvicorn acquittify.library_api:app --host 0.0.0.0 --port 8092
