locals {
  caselaw_schedule_is_cron = startswith(trimspace(var.caselaw_schedule_expression), "cron(")
}

data "aws_iam_policy_document" "caselaw_scheduler_assume_role" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "caselaw_scheduler" {
  count = var.caselaw_scheduler_enabled ? 1 : 0

  name               = "${local.stack_name}-caselaw-scheduler-role"
  assume_role_policy = data.aws_iam_policy_document.caselaw_scheduler_assume_role.json

  tags = local.tags
}

data "aws_iam_policy_document" "caselaw_scheduler_run_task" {
  statement {
    effect = "Allow"
    actions = [
      "ecs:RunTask",
    ]
    resources = [
      aws_ecs_task_definition.caselaw_ingest.arn,
    ]

    condition {
      test     = "ArnEquals"
      variable = "ecs:cluster"
      values = [
        aws_ecs_cluster.main.arn,
      ]
    }
  }

  statement {
    effect = "Allow"
    actions = [
      "iam:PassRole",
    ]
    resources = [
      aws_iam_role.ecs_task_execution.arn,
      aws_iam_role.ecs_task.arn,
    ]

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values = [
        "ecs-tasks.amazonaws.com",
      ]
    }
  }
}

resource "aws_iam_role_policy" "caselaw_scheduler_run_task" {
  count = var.caselaw_scheduler_enabled ? 1 : 0

  name   = "${local.stack_name}-caselaw-scheduler-run-task"
  role   = aws_iam_role.caselaw_scheduler[0].id
  policy = data.aws_iam_policy_document.caselaw_scheduler_run_task.json
}

resource "aws_scheduler_schedule" "caselaw_ingest" {
  count = var.caselaw_scheduler_enabled ? 1 : 0

  name        = "${local.stack_name}-caselaw-ingest"
  description = "Runs Acquittify caselaw ingest task on ECS"
  state       = "ENABLED"

  schedule_expression          = var.caselaw_schedule_expression
  schedule_expression_timezone = local.caselaw_schedule_is_cron ? var.caselaw_schedule_timezone : null

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_ecs_cluster.main.arn
    role_arn = aws_iam_role.caselaw_scheduler[0].arn

    ecs_parameters {
      task_definition_arn = aws_ecs_task_definition.caselaw_ingest.arn
      launch_type         = "FARGATE"
      platform_version    = "LATEST"
      task_count          = 1

      network_configuration {
        subnets          = var.private_subnet_ids
        security_groups  = [aws_security_group.ecs_tasks.id]
        assign_public_ip = false
      }
    }

    retry_policy {
      maximum_event_age_in_seconds = 3600
      maximum_retry_attempts       = 1
    }
  }

  depends_on = [
    aws_iam_role_policy.caselaw_scheduler_run_task,
  ]
}
