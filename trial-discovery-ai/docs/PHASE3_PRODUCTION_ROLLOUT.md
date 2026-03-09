# Phase 3: Production Launch and Rapid Scale Plan

This phase turns Peregrine into a web-accessible production service with horizontal scale headroom.

## Scope implemented in repo

- Container packaging for backend and frontend:
  - `trial-discovery-ai/backend/Dockerfile`
  - `trial-discovery-ai/frontend/Dockerfile`
- Staging-style deploy stack with API + worker + frontend:
  - `deploy/docker-compose.phase3.yml`
- Launch and validation scripts:
  - `trial-discovery-ai/scripts/phase3_preflight_env.sh`
  - `trial-discovery-ai/scripts/phase3_activate_local.sh`
- Phase 3b Terraform stack and scripts:
  - `deploy/terraform`
  - `trial-discovery-ai/scripts/phase3b_terraform_plan.sh`
  - `trial-discovery-ai/scripts/phase3b_terraform_apply.sh`
  - `trial-discovery-ai/scripts/phase3b_run_migration_task.sh`

## Target production architecture (AWS)

- DNS and TLS:
  - Route 53 hosted zone
  - ACM certificate
- Edge and load balancing:
  - Application Load Balancer (ALB)
  - HTTPS listener only (redirect HTTP to HTTPS)
- Compute:
  - ECS Fargate service: `peregrine-api`
  - ECS Fargate service: `peregrine-worker`
  - ECS Fargate service: `peregrine-frontend`
- Data and state:
  - Amazon RDS PostgreSQL (with pgvector)
  - Amazon ElastiCache Redis
  - Amazon S3 bucket (artifacts)
- Secrets and config:
  - AWS Secrets Manager for sensitive env
  - SSM Parameter Store for non-secret config
- Observability:
  - CloudWatch logs and alarms
  - ALB 5xx + latency alarms
  - ECS CPU/memory alarms

## Initial sizing baseline

- `peregrine-api`:
  - 2 tasks minimum, autoscale to 12
  - 1 vCPU / 2 GB RAM per task
- `peregrine-worker`:
  - 2 tasks minimum, autoscale to 20
  - 2 vCPU / 4 GB RAM per task
- `peregrine-frontend`:
  - 2 tasks minimum, autoscale to 8
  - 0.5 vCPU / 1 GB RAM per task
- RDS:
  - start `db.r6g.large`, Multi-AZ enabled
- Redis:
  - start `cache.r7g.large`, Multi-AZ with auto-failover

## Environment requirements for production

Required:

- `DATABASE_URL`
- `REDIS_URL`
- `MINIO_BUCKET` (or S3 bucket name)
- `AUTH_SECRET_KEY`
- `CORS_ALLOW_ORIGINS`
- `AUTH_COOKIE_SECURE=true`
- `AUTH_PASSWORD_RESET_DEV_RETURN_TOKEN=false`

Recommended:

- `AUTH_RATE_LIMIT_ENABLED=true`
- `AUTH_RATE_LIMIT_MAX_ATTEMPTS=10`
- `AUTH_RATE_LIMIT_WINDOW_SECONDS=60`
- `AUTH_RATE_LIMIT_BACKEND=redis`
- `UVICORN_WORKERS=2` (tune under load test)
- `CELERY_CONCURRENCY=2` (tune under queue depth)

## Deployment sequence

1. Provision infrastructure (VPC, RDS, Redis, S3, ECS, ALB, IAM).
2. Push backend and frontend images to ECR.
3. Run DB migrations (`alembic upgrade head`) as one-off ECS task.
4. Deploy API and worker services.
5. Deploy frontend service.
6. Run smoke checks:
   - `/healthz`
   - register/login/logout
   - password reset flow
   - ingest + worker completion
7. Shift DNS traffic to ALB.

## Rollback sequence

1. Keep previous image tags pinned.
2. If release fails, redeploy previous API/worker/frontend task definitions.
3. If migration is backward-compatible, leave schema in place and roll back app only.
4. If migration is incompatible, run explicit downgrade playbook before app rollback.

## Load and scale strategy

- Trigger autoscaling by API CPU > 60% and ALB target response time > 400ms.
- Scale workers by queue depth and task age (Celery backlog alarms).
- Cache expensive metadata queries with Redis where safe.
- Keep read-heavy endpoints (`/matters`, `/documents`) indexed and paginated.

## Local phase 3 activation

```bash
./trial-discovery-ai/scripts/phase3_activate_local.sh
```

Preflight production env file:

```bash
./trial-discovery-ai/scripts/phase3_preflight_env.sh <path-to-prod-env-file>
```

Phase 3b Terraform implementation guide:

- `trial-discovery-ai/docs/PHASE3B_TERRAFORM_AWS.md`
