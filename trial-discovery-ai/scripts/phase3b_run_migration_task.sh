#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TF_DIR="$ROOT_DIR/deploy/terraform"

if ! command -v terraform >/dev/null 2>&1; then
  echo "terraform is required but not installed"
  exit 1
fi

if ! command -v aws >/dev/null 2>&1; then
  echo "aws cli is required but not installed"
  exit 1
fi

CLUSTER_NAME="$(terraform -chdir="$TF_DIR" output -raw ecs_cluster_name)"
TASK_DEF_ARN="$(terraform -chdir="$TF_DIR" output -raw migrate_task_definition_arn)"
TASK_SG_ID="$(terraform -chdir="$TF_DIR" output -raw ecs_task_security_group_id)"
SUBNETS_CSV="$(terraform -chdir="$TF_DIR" output -raw private_subnet_ids_csv)"

NETWORK_CFG="awsvpcConfiguration={subnets=[${SUBNETS_CSV}],securityGroups=[${TASK_SG_ID}],assignPublicIp=DISABLED}"

echo "Running migration task on cluster ${CLUSTER_NAME}..."
TASK_ARN="$(aws ecs run-task \
  --cluster "$CLUSTER_NAME" \
  --launch-type FARGATE \
  --task-definition "$TASK_DEF_ARN" \
  --network-configuration "$NETWORK_CFG" \
  --query 'tasks[0].taskArn' \
  --output text)"

echo "Waiting for migration task: $TASK_ARN"
aws ecs wait tasks-stopped --cluster "$CLUSTER_NAME" --tasks "$TASK_ARN"

EXIT_CODE="$(aws ecs describe-tasks \
  --cluster "$CLUSTER_NAME" \
  --tasks "$TASK_ARN" \
  --query 'tasks[0].containers[0].exitCode' \
  --output text)"

if [ "$EXIT_CODE" != "0" ]; then
  echo "Migration task failed with exit code: $EXIT_CODE"
  aws ecs describe-tasks --cluster "$CLUSTER_NAME" --tasks "$TASK_ARN" --output json
  exit 1
fi

echo "Migration task completed successfully."
