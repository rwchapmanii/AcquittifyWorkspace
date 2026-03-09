#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FOUNDATION_DIR="$ROOT_DIR/deploy/terraform-foundation"
MAIN_TF_DIR="$ROOT_DIR/deploy/terraform"
OUT_FILE="${1:-$MAIN_TF_DIR/terraform.tfvars}"

DOMAIN_NAME="${DOMAIN_NAME:-acquittify.ai}"
FRONTEND_SUBDOMAIN="${FRONTEND_SUBDOMAIN:-}"
API_SUBDOMAIN="${API_SUBDOMAIN:-api}"
NAME_PREFIX="${NAME_PREFIX:-acquittify}"
ENVIRONMENT="${ENVIRONMENT:-prod}"

if ! command -v terraform >/dev/null 2>&1; then
  echo "terraform is required but not installed"
  exit 1
fi

if [ ! -d "$FOUNDATION_DIR" ]; then
  echo "Foundation Terraform directory not found: $FOUNDATION_DIR"
  exit 1
fi

if [ ! -f "$FOUNDATION_DIR/terraform.tfstate" ]; then
  echo "No terraform.tfstate found in $FOUNDATION_DIR"
  echo "Run foundation apply first."
  exit 1
fi

if [ -f "$OUT_FILE" ]; then
  echo "Refusing to overwrite existing file: $OUT_FILE"
  echo "Pass a different output path as the first argument or delete the file."
  exit 1
fi

mkdir -p "$(dirname "$OUT_FILE")"

VPC_ID="$(terraform -chdir="$FOUNDATION_DIR" output -raw vpc_id)"
PUBLIC_SUBNET_IDS_JSON="$(terraform -chdir="$FOUNDATION_DIR" output -json public_subnet_ids)"
PRIVATE_SUBNET_IDS_JSON="$(terraform -chdir="$FOUNDATION_DIR" output -json private_subnet_ids)"
ROUTE53_ZONE_ID="$(terraform -chdir="$FOUNDATION_DIR" output -raw route53_zone_id)"
ACM_CERT_ARN="$(terraform -chdir="$FOUNDATION_DIR" output -raw acm_certificate_arn)"
AUTH_SECRET_ARN="$(terraform -chdir="$FOUNDATION_DIR" output -raw auth_secret_arn)"

if [ -n "$FRONTEND_SUBDOMAIN" ]; then
  FRONTEND_FQDN="${FRONTEND_SUBDOMAIN}.${DOMAIN_NAME}"
else
  FRONTEND_FQDN="$DOMAIN_NAME"
fi

if [ -n "$API_SUBDOMAIN" ]; then
  API_FQDN="${API_SUBDOMAIN}.${DOMAIN_NAME}"
else
  API_FQDN="$DOMAIN_NAME"
fi

cat >"$OUT_FILE" <<EOF
aws_region = "us-east-1"
name_prefix = "${NAME_PREFIX}"
environment = "${ENVIRONMENT}"

vpc_id             = "${VPC_ID}"
public_subnet_ids  = ${PUBLIC_SUBNET_IDS_JSON}
private_subnet_ids = ${PRIVATE_SUBNET_IDS_JSON}
route53_zone_id    = "${ROUTE53_ZONE_ID}"
domain_name        = "${DOMAIN_NAME}"
frontend_subdomain = "${FRONTEND_SUBDOMAIN}"
api_subdomain      = "${API_SUBDOMAIN}"
acm_certificate_arn = "${ACM_CERT_ARN}"
auth_secret_arn     = "${AUTH_SECRET_ARN}"

# Optional S3 settings
s3_bucket_name          = ""
s3_force_destroy        = false
s3_versioning_enabled   = false
s3_kms_key_arn          = ""
s3_cors_allowed_origins = ["https://${FRONTEND_FQDN}"]

# Optional secret ARNs
dropbox_access_token_secret_arn  = ""
dropbox_refresh_token_secret_arn = ""
dropbox_app_key_secret_arn       = ""
dropbox_app_secret_secret_arn    = ""
dropbox_team_member_id_secret_arn = ""
openai_api_key_secret_arn         = ""

# Optional app overrides
cors_allow_origins = ["https://${FRONTEND_FQDN}"]
cookie_domain      = ".${DOMAIN_NAME}"
frontend_next_public_api_url = "https://${API_FQDN}"

# Optional image tags
api_image_tag      = "latest"
worker_image_tag   = "latest"
frontend_image_tag = "latest"
EOF

echo "Wrote Terraform variables: $OUT_FILE"
echo "Next: terraform -chdir=\"$MAIN_TF_DIR\" init && terraform -chdir=\"$MAIN_TF_DIR\" plan -var-file=\"$OUT_FILE\""
