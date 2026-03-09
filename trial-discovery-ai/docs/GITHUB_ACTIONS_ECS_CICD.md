# GitHub Actions CI/CD (ECR -> ECS)

This repo includes a production workflow at:

- `.github/workflows/peregrine-cicd-ecs.yml`

Pipeline:

1. `git push` to `main`
2. GitHub Actions builds Docker images
3. Images are pushed to ECR
4. ECS task definitions are updated to new image tags
5. ECS services roll to the new revisions

## 1) Configure GitHub Variables

Set these repository variables in **Settings -> Secrets and variables -> Actions -> Variables**:

- `AWS_REGION` (example: `us-east-1`)
- `ECR_API_REPOSITORY` (example: `acquittify-prod-api`)
- `ECR_WORKER_REPOSITORY` (example: `acquittify-prod-worker`)
- `ECR_FRONTEND_REPOSITORY` (example: `acquittify-prod-frontend`)
- `ECS_CLUSTER` (example: `acquittify-prod-cluster`)
- `ECS_API_SERVICE` (example: `acquittify-prod-api`)
- `ECS_WORKER_SERVICE` (example: `acquittify-prod-worker`)
- `ECS_FRONTEND_SERVICE` (example: `acquittify-prod-frontend`)
- `NEXT_PUBLIC_PEREGRINE_API_URL` (example: `https://peregrine-api.example.com`)

Optional frontend vars (only needed if non-default):

- `NEXT_PUBLIC_PEREGRINE_CSRF_COOKIE_NAME`
- `NEXT_PUBLIC_PEREGRINE_CSRF_HEADER_NAME`

## 2) Configure GitHub Secrets

Preferred (OIDC role):

- `AWS_ROLE_TO_ASSUME` = IAM role ARN trusted for GitHub OIDC.

Fallback (long-lived keys):

- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`

If `AWS_ROLE_TO_ASSUME` is set, the workflow uses OIDC and ignores static keys.

## 3) IAM permissions for deploy role/user

Grant least-privilege access to:

- ECR auth + image push:
  - `ecr:GetAuthorizationToken`
  - `ecr:BatchCheckLayerAvailability`
  - `ecr:CompleteLayerUpload`
  - `ecr:InitiateLayerUpload`
  - `ecr:UploadLayerPart`
  - `ecr:PutImage`
- ECS deploy actions:
  - `ecs:DescribeServices`
  - `ecs:DescribeTaskDefinition`
  - `ecs:RegisterTaskDefinition`
  - `ecs:UpdateService`
  - `ecs:ListTasks`
  - `ecs:DescribeTasks`
- Pass execution/task roles used by ECS task definitions:
  - `iam:PassRole` for the ECS task execution role and task role ARNs.

## 4) Trigger and deploy

Push to `main`:

```bash
git add .
git commit -m "Deploy update"
git push origin main
```

The workflow builds/pushes:

- `trial-discovery-ai/backend/Dockerfile` -> API and worker repositories
- `trial-discovery-ai/frontend/Dockerfile` -> frontend repository

Then it deploys all three ECS services with image tag = commit SHA.
