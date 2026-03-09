# GitHub OIDC Setup (AcquittifyWorkspace)

This folder contains IAM templates for GitHub Actions deploys from:

- repo: `rwchapmanii/AcquittifyWorkspace`
- branch: `main`

The deploy workflow now requires OIDC role auth only (`AWS_ROLE_TO_ASSUME`).

## 1) Ensure GitHub OIDC provider exists (one-time per AWS account)

```bash
aws iam list-open-id-connect-providers \
  --query "OpenIDConnectProviderList[].Arn" \
  --output text
```

If missing, create it:

```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

## 2) Create trust policy role

Trust policy template:

- `deploy/iam/github-oidc-trust-policy.acquittifyworkspace.json`

Create role:

```bash
aws iam create-role \
  --role-name GitHubActionsAcquittifyWorkspaceDeployRole \
  --assume-role-policy-document file://deploy/iam/github-oidc-trust-policy.acquittifyworkspace.json
```

## 3) Attach least-privilege deploy policy

Policy template:

- `deploy/iam/github-actions-ecs-ecr-policy.template.json`

Replace placeholders:

- `<AWS_REGION>`
- `<AWS_ACCOUNT_ID>`
- `<ECR_API_REPOSITORY>`
- `<ECR_WORKER_REPOSITORY>`
- `<ECR_FRONTEND_REPOSITORY>`
- `<ECS_CLUSTER>`
- `<ECS_API_SERVICE>`
- `<ECS_WORKER_SERVICE>`
- `<ECS_FRONTEND_SERVICE>`
- `<ECS_TASK_EXECUTION_ROLE_NAME>`
- `<ECS_TASK_ROLE_NAME>`

Then create and attach:

```bash
aws iam create-policy \
  --policy-name GitHubActionsAcquittifyWorkspaceEcsDeployPolicy \
  --policy-document file://deploy/iam/github-actions-ecs-ecr-policy.json

aws iam attach-role-policy \
  --role-name GitHubActionsAcquittifyWorkspaceDeployRole \
  --policy-arn arn:aws:iam::<AWS_ACCOUNT_ID>:policy/GitHubActionsAcquittifyWorkspaceEcsDeployPolicy
```

## 4) GitHub repository settings

In `rwchapmanii/AcquittifyWorkspace`:

- `Settings > Secrets and variables > Actions`

Set secret:

- `AWS_ROLE_TO_ASSUME` = `arn:aws:iam::<AWS_ACCOUNT_ID>:role/GitHubActionsAcquittifyWorkspaceDeployRole`

Set variables:

- `AWS_REGION`
- `ECR_API_REPOSITORY`
- `ECR_WORKER_REPOSITORY`
- `ECR_FRONTEND_REPOSITORY`
- `ECS_CLUSTER`
- `ECS_API_SERVICE`
- `ECS_WORKER_SERVICE`
- `ECS_FRONTEND_SERVICE`
- `NEXT_PUBLIC_PEREGRINE_API_URL`
- optional: `NEXT_PUBLIC_PEREGRINE_CSRF_COOKIE_NAME`, `NEXT_PUBLIC_PEREGRINE_CSRF_HEADER_NAME`

## 5) Validate

Run workflow:

- `.github/workflows/peregrine-cicd-ecs.yml`

Expected:

- `Configure AWS credentials (OIDC)` succeeds
- ECR push succeeds for API/worker/frontend
- ECS service updates complete
