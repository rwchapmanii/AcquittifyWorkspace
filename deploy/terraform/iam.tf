data "aws_iam_policy_document" "ecs_task_assume_role" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "ecs_task_execution" {
  name               = "${local.stack_name}-ecs-exec-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume_role.json

  tags = local.tags
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution_managed" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

locals {
  secret_arns = compact([
    aws_secretsmanager_secret.database_url.arn,
    var.auth_secret_arn,
    var.dropbox_access_token_secret_arn != "" ? var.dropbox_access_token_secret_arn : null,
    var.dropbox_refresh_token_secret_arn != "" ? var.dropbox_refresh_token_secret_arn : null,
    var.dropbox_app_key_secret_arn != "" ? var.dropbox_app_key_secret_arn : null,
    var.dropbox_app_secret_secret_arn != "" ? var.dropbox_app_secret_secret_arn : null,
    var.dropbox_team_member_id_secret_arn != "" ? var.dropbox_team_member_id_secret_arn : null,
    var.openai_api_key_secret_arn != "" ? var.openai_api_key_secret_arn : null,
    var.llm_api_key_secret_arn != "" ? var.llm_api_key_secret_arn : null,
    var.courtlistener_api_token_secret_arn != "" ? var.courtlistener_api_token_secret_arn : null,
  ])
}

data "aws_iam_policy_document" "ecs_execution_extra" {
  statement {
    effect = "Allow"

    actions = [
      "secretsmanager:GetSecretValue",
      "ssm:GetParameter",
      "ssm:GetParameters",
    ]

    resources = local.secret_arns
  }

  statement {
    effect = "Allow"

    actions = [
      "kms:Decrypt",
    ]

    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "ecs_execution_extra" {
  name   = "${local.stack_name}-ecs-exec-extra"
  role   = aws_iam_role.ecs_task_execution.id
  policy = data.aws_iam_policy_document.ecs_execution_extra.json
}

resource "aws_iam_role" "ecs_task" {
  name               = "${local.stack_name}-ecs-task-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume_role.json

  tags = local.tags
}

data "aws_iam_policy_document" "ecs_task_s3" {
  statement {
    effect = "Allow"

    actions = [
      "s3:ListBucket",
    ]

    resources = [
      aws_s3_bucket.artifacts.arn,
    ]
  }

  statement {
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
    ]

    resources = [
      "${aws_s3_bucket.artifacts.arn}/*",
    ]
  }

  statement {
    effect = "Allow"

    actions = [
      "kms:Decrypt",
      "kms:Encrypt",
      "kms:GenerateDataKey",
      "kms:DescribeKey",
    ]

    resources = [
      local.artifact_bucket_kms_key_arn,
    ]
  }

  statement {
    effect = "Allow"

    actions = [
      "ses:SendEmail",
      "ses:SendRawEmail",
    ]

    resources = [
      var.ses_sender_identity_arn != "" ? var.ses_sender_identity_arn : "*",
    ]
  }
}

resource "aws_iam_role_policy" "ecs_task_s3" {
  name   = "${local.stack_name}-ecs-task-s3"
  role   = aws_iam_role.ecs_task.id
  policy = data.aws_iam_policy_document.ecs_task_s3.json
}
