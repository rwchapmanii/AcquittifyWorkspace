# Peregrine AWS Terraform

This directory provisions production infrastructure for Acquittify Peregrine on AWS.

Important auth settings:
- Configure `auth_email_sender` (and optionally `auth_email_region`) so password reset codes can be delivered through SES.
- Optionally set `ses_sender_identity_arn` to scope ECS task SES send permissions to one verified identity.

## Files

- `versions.tf`, `providers.tf`: Terraform/AWS provider setup
- `variables.tf`, `locals.tf`: input variables and computed defaults
- `network.tf`: security groups
- `alb.tf`: ALB, target groups, listeners, and API host rule
- `container_registry.tf`: ECR repositories
- `storage.tf`: S3 artifacts bucket
- `database.tf`: RDS PostgreSQL and generated `DATABASE_URL` secret
- `cache.tf`: ElastiCache Redis
- `iam.tf`: ECS execution/task roles
- `ecs.tf`: ECS cluster, task definitions, and services
- `openclaw_gateway.tf`: optional internal OpenClaw EC2 gateway, NLB, and private DNS
- `scheduler.tf`: EventBridge Scheduler + ECS task trigger for caselaw ingest
- `autoscaling.tf`: ECS service autoscaling
- `dns.tf`: Route53 alias records
- `outputs.tf`: useful outputs for deployment scripts
- `terraform.tfvars.example`: template for deployment inputs

## Usage

Prerequisite: private subnets must have outbound access (NAT gateway or
VPC endpoints) for pulling images and writing logs.

OpenClaw note: `llm_base_url` must be reachable from ECS tasks. For hosted ECS,
do not use `127.0.0.1`; use a private DNS/tunnel endpoint and set
`llm_api_key_secret_arn` when gateway auth requires a token.

When `openclaw_gateway_enabled=true`, Terraform provisions an internal EC2
gateway with Docker + OpenClaw, an internal NLB, and a private Route53 record.
In that mode, keep `llm_base_url=""` so ECS uses the generated private DNS URL.

1. Copy and edit `terraform.tfvars.example`:

```bash
cp terraform.tfvars.example terraform.tfvars
```

2. Plan:

```bash
../../scripts/phase3b_terraform_plan.sh
```

3. Apply:

```bash
../../scripts/phase3b_terraform_apply.sh
```

4. Run migration task:

```bash
../../scripts/phase3b_run_migration_task.sh
```

5. Confirm caselaw scheduler:

```bash
terraform output caselaw_scheduler_arn
```
