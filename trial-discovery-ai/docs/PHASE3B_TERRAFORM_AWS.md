# Phase 3b: Terraform AWS Infrastructure

Phase 3b provides Infrastructure-as-Code for production deployment on AWS.

## Implemented assets

- Terraform application stack:
  - `/Users/ronaldchapman/Desktop/Acquittify/deploy/terraform`
- Terraform foundation stack:
  - `/Users/ronaldchapman/Desktop/Acquittify/deploy/terraform-foundation`
- Helper scripts:
  - `/Users/ronaldchapman/Desktop/Acquittify/trial-discovery-ai/scripts/phase3b_generate_tfvars_from_foundation.sh`
  - `/Users/ronaldchapman/Desktop/Acquittify/trial-discovery-ai/scripts/phase3b_terraform_plan.sh`
  - `/Users/ronaldchapman/Desktop/Acquittify/trial-discovery-ai/scripts/phase3b_terraform_apply.sh`
  - `/Users/ronaldchapman/Desktop/Acquittify/trial-discovery-ai/scripts/phase3b_run_migration_task.sh`

## What Terraform provisions

Foundation stack (`deploy/terraform-foundation`):

- VPC, IGW, public/private subnets, NAT gateway + route tables
- ACM certificate with DNS validation records in Route53
- `AUTH_SECRET_KEY` secret shell in Secrets Manager

Application stack (`deploy/terraform`):

- ECR repositories (`api`, `worker`, `frontend`)
- S3 artifact bucket (private, versioned, encrypted)
- RDS PostgreSQL (Multi-AZ defaults)
- ElastiCache Redis replication group
- IAM task/execution roles for ECS
- ECS cluster + Fargate task definitions (`api`, `worker`, `frontend`, `migrate`)
- ECS services + autoscaling policies
- Application Load Balancer (HTTPS + HTTP redirect)
- Route53 alias records for frontend and API hostnames
- Secrets Manager secret storing generated `DATABASE_URL`

## 1) Apply foundation stack

```bash
terraform -chdir=/Users/ronaldchapman/Desktop/Acquittify/deploy/terraform-foundation init
terraform -chdir=/Users/ronaldchapman/Desktop/Acquittify/deploy/terraform-foundation apply
```

If `acquittify.ai` is still delegated to GoDaddy nameservers, ACM validation will remain `PENDING_VALIDATION`.
Either:

- switch domain nameservers to the Route53 hosted zone, or
- add the ACM validation CNAME in the current GoDaddy DNS zone.

If your root domain should serve the frontend (apex), keep:

- `frontend_subdomain = ""`
- `api_subdomain = "api"` (or your preferred API host label)

## 2) Generate app stack tfvars from foundation outputs

```bash
DOMAIN_NAME=acquittify.ai \
FRONTEND_SUBDOMAIN="" \
API_SUBDOMAIN="api" \
NAME_PREFIX="acquittify" \
/Users/ronaldchapman/Desktop/Acquittify/trial-discovery-ai/scripts/phase3b_generate_tfvars_from_foundation.sh \
  /Users/ronaldchapman/Desktop/Acquittify/deploy/terraform/terraform.tfvars
```

If you prefer manual editing, copy from:

```bash
cp /Users/ronaldchapman/Desktop/Acquittify/deploy/terraform/terraform.tfvars.example \
   /Users/ronaldchapman/Desktop/Acquittify/deploy/terraform/terraform.tfvars
```

Then fill:

- `vpc_id`, `public_subnet_ids`, `private_subnet_ids`
- `route53_zone_id`
- `domain_name`
- `acm_certificate_arn`
- `auth_secret_arn`

Your VPC must already provide outbound connectivity for private subnets
(NAT gateway or equivalent VPC endpoints for ECR, CloudWatch Logs, and S3).
For S3 behavior aligned to account-cancel hard delete and direct browser uploads, keep:

- `s3_versioning_enabled = false`
- `s3_cors_allowed_origins = ["https://acquittify.ai"]` (or your frontend origin list)

## 3) Plan and apply app stack

```bash
/Users/ronaldchapman/Desktop/Acquittify/trial-discovery-ai/scripts/phase3b_terraform_plan.sh \
  /Users/ronaldchapman/Desktop/Acquittify/deploy/terraform/terraform.tfvars

/Users/ronaldchapman/Desktop/Acquittify/trial-discovery-ai/scripts/phase3b_terraform_apply.sh \
  /Users/ronaldchapman/Desktop/Acquittify/deploy/terraform/terraform.tfvars
```

## 4) Build and push images to ECR

After `apply`, fetch repo URLs:

```bash
terraform -chdir=/Users/ronaldchapman/Desktop/Acquittify/deploy/terraform output ecr_api_repository_url
terraform -chdir=/Users/ronaldchapman/Desktop/Acquittify/deploy/terraform output ecr_worker_repository_url
terraform -chdir=/Users/ronaldchapman/Desktop/Acquittify/deploy/terraform output ecr_frontend_repository_url
```

Build and push using your chosen tag (example: `release-2026-02-19`):

- Backend API image from `/Users/ronaldchapman/Desktop/Acquittify/trial-discovery-ai/backend/Dockerfile`
- Worker image from same backend Dockerfile
- Frontend image from `/Users/ronaldchapman/Desktop/Acquittify/trial-discovery-ai/frontend/Dockerfile`

Set `api_image_tag`, `worker_image_tag`, `frontend_image_tag` in `terraform.tfvars`, then `terraform apply` again to roll services.

## 5) Run DB migrations in ECS

```bash
/Users/ronaldchapman/Desktop/Acquittify/trial-discovery-ai/scripts/phase3b_run_migration_task.sh
```

## 6) Verify production endpoints

```bash
terraform -chdir=/Users/ronaldchapman/Desktop/Acquittify/deploy/terraform output frontend_url
terraform -chdir=/Users/ronaldchapman/Desktop/Acquittify/deploy/terraform output api_url
```

Smoke checks:

- `GET /healthz`
- register/login/logout
- password reset
- CSRF-protected write endpoint (`POST /matters`)
- ingest pipeline and worker execution

## Notes

- API and frontend are on separate subdomains by default.
- Cookies are configured for the parent domain (`.example.com`) unless overridden with `cookie_domain`.
- Rate limiting defaults to Redis (`AUTH_RATE_LIMIT_BACKEND=redis`) for multi-instance correctness.
