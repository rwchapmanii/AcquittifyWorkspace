#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TF_DIR="$ROOT_DIR/deploy/terraform"
TFVARS="${1:-$TF_DIR/terraform.tfvars}"

if ! command -v terraform >/dev/null 2>&1; then
  echo "terraform is required but not installed"
  exit 1
fi

if [ ! -f "$TFVARS" ]; then
  echo "Terraform vars file not found: $TFVARS"
  echo "Copy $TF_DIR/terraform.tfvars.example to $TF_DIR/terraform.tfvars and edit values."
  exit 1
fi

terraform -chdir="$TF_DIR" init
terraform -chdir="$TF_DIR" apply -var-file="$TFVARS"
