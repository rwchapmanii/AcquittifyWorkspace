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

echo "[1/4] terraform init"
terraform -chdir="$TF_DIR" init

echo "[2/4] terraform fmt"
terraform -chdir="$TF_DIR" fmt -recursive

echo "[3/4] terraform validate"
terraform -chdir="$TF_DIR" validate

echo "[4/4] terraform plan"
terraform -chdir="$TF_DIR" plan -var-file="$TFVARS"
