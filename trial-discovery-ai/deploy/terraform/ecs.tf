resource "aws_ecs_cluster" "main" {
  name = "${local.stack_name}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = local.tags
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${local.stack_name}/api"
  retention_in_days = var.log_retention_days

  tags = local.tags
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/ecs/${local.stack_name}/worker"
  retention_in_days = var.log_retention_days

  tags = local.tags
}

resource "aws_cloudwatch_log_group" "frontend" {
  name              = "/ecs/${local.stack_name}/frontend"
  retention_in_days = var.log_retention_days

  tags = local.tags
}

locals {
  api_image      = "${aws_ecr_repository.api.repository_url}:${var.api_image_tag}"
  worker_image   = "${aws_ecr_repository.worker.repository_url}:${var.worker_image_tag}"
  frontend_image = "${aws_ecr_repository.frontend.repository_url}:${var.frontend_image_tag}"

  api_secrets = concat(
    [
      {
        name      = "DATABASE_URL"
        valueFrom = aws_secretsmanager_secret.database_url.arn
      },
      {
        name      = "AUTH_SECRET_KEY"
        valueFrom = var.auth_secret_arn
      },
    ],
    var.dropbox_access_token_secret_arn != "" ? [{ name = "DROPBOX_ACCESS_TOKEN", valueFrom = var.dropbox_access_token_secret_arn }] : [],
    var.dropbox_refresh_token_secret_arn != "" ? [{ name = "DROPBOX_REFRESH_TOKEN", valueFrom = var.dropbox_refresh_token_secret_arn }] : [],
    var.dropbox_app_key_secret_arn != "" ? [{ name = "DROPBOX_APP_KEY", valueFrom = var.dropbox_app_key_secret_arn }] : [],
    var.dropbox_app_secret_secret_arn != "" ? [{ name = "DROPBOX_APP_SECRET", valueFrom = var.dropbox_app_secret_secret_arn }] : [],
    var.dropbox_team_member_id_secret_arn != "" ? [{ name = "DROPBOX_TEAM_MEMBER_ID", valueFrom = var.dropbox_team_member_id_secret_arn }] : [],
    var.openai_api_key_secret_arn != "" ? [{ name = "OPENAI_API_KEY", valueFrom = var.openai_api_key_secret_arn }] : [],
    var.llm_api_key_secret_arn != "" ? [{ name = "LLM_API_KEY", valueFrom = var.llm_api_key_secret_arn }] : []
  )

  worker_secrets = local.api_secrets

  api_environment = concat(
    [
      { name = "REDIS_URL", value = local.redis_url },
      { name = "CORS_ALLOW_ORIGINS", value = local.effective_cors_allow_origins },
      { name = "AUTH_COOKIE_SECURE", value = "true" },
      { name = "AUTH_COOKIE_DOMAIN", value = local.effective_cookie_domain },
      { name = "AUTH_PASSWORD_RESET_DEV_RETURN_TOKEN", value = "false" },
      { name = "AUTH_RATE_LIMIT_ENABLED", value = var.auth_rate_limit_enabled ? "true" : "false" },
      { name = "AUTH_RATE_LIMIT_BACKEND", value = var.auth_rate_limit_backend },
      { name = "AUTH_RATE_LIMIT_WINDOW_SECONDS", value = tostring(var.auth_rate_limit_window_seconds) },
      { name = "AUTH_RATE_LIMIT_MAX_ATTEMPTS", value = tostring(var.auth_rate_limit_max_attempts) },
      { name = "S3_BUCKET", value = aws_s3_bucket.artifacts.bucket },
      { name = "MINIO_BUCKET", value = aws_s3_bucket.artifacts.bucket },
      { name = "S3_REGION", value = var.aws_region },
      { name = "S3_SECURE", value = "true" },
      { name = "S3_SSE_KMS_KEY_ID", value = aws_kms_key.artifacts.arn },
      { name = "ENFORCE_USER_DOCUMENT_SCOPE", value = var.enforce_user_document_scope ? "true" : "false" },
      { name = "UPLOAD_REQUIRE_USER_SCOPED_KEYS", value = var.upload_require_user_scoped_keys ? "true" : "false" },
      { name = "EMBEDDING_MODEL", value = var.embedding_model },
      { name = "EMBEDDING_DIM", value = tostring(var.embedding_dim) },
      { name = "LLM_MODEL", value = var.llm_model },
      { name = "LLM_REPAIR_MODEL", value = var.llm_repair_model },
      { name = "AGENT_MODEL", value = var.agent_model },
      { name = "OPENCLAW_AGENT_ID", value = var.openclaw_agent_id },
      { name = "DROPBOX_ROOT_PATH", value = var.dropbox_case_root_path },
      { name = "DROPBOX_CASE_ROOT_PATH", value = var.dropbox_case_root_link },
    ],
    var.llm_base_url != "" ? [{ name = "LLM_BASE_URL", value = var.llm_base_url }] : []
  )

  worker_environment = concat(
    [
      { name = "REDIS_URL", value = local.redis_url },
      { name = "S3_BUCKET", value = aws_s3_bucket.artifacts.bucket },
      { name = "MINIO_BUCKET", value = aws_s3_bucket.artifacts.bucket },
      { name = "S3_REGION", value = var.aws_region },
      { name = "S3_SECURE", value = "true" },
      { name = "S3_SSE_KMS_KEY_ID", value = aws_kms_key.artifacts.arn },
      { name = "EMBEDDING_MODEL", value = var.embedding_model },
      { name = "EMBEDDING_DIM", value = tostring(var.embedding_dim) },
      { name = "LLM_MODEL", value = var.llm_model },
      { name = "LLM_REPAIR_MODEL", value = var.llm_repair_model },
      { name = "AGENT_MODEL", value = var.agent_model },
      { name = "OPENCLAW_AGENT_ID", value = var.openclaw_agent_id },
      { name = "DROPBOX_ROOT_PATH", value = var.dropbox_case_root_path },
      { name = "DROPBOX_CASE_ROOT_PATH", value = var.dropbox_case_root_link },
    ],
    var.llm_base_url != "" ? [{ name = "LLM_BASE_URL", value = var.llm_base_url }] : []
  )

  frontend_environment = [
    { name = "PORT", value = "3000" },
    { name = "NEXT_PUBLIC_PEREGRINE_API_URL", value = local.effective_frontend_api_url },
    { name = "NEXT_PUBLIC_PEREGRINE_CSRF_COOKIE_NAME", value = "peregrine_csrf" },
    { name = "NEXT_PUBLIC_PEREGRINE_CSRF_HEADER_NAME", value = "X-CSRF-Token" },
  ]
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${local.stack_name}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(var.api_cpu)
  memory                   = tostring(var.api_memory)
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "api"
      image     = local.api_image
      essential = true
      command = [
        "uvicorn",
        "app.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8002",
        "--workers",
        tostring(var.api_uvicorn_workers),
      ]
      portMappings = [
        {
          containerPort = 8002
          hostPort      = 8002
          protocol      = "tcp"
        }
      ]
      environment = local.api_environment
      secrets     = local.api_secrets
      healthCheck = {
        command     = ["CMD-SHELL", "curl -fsS http://localhost:8002/healthz || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 30
      }
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.api.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "api"
        }
      }
    }
  ])

  tags = local.tags
}

resource "aws_ecs_task_definition" "worker" {
  family                   = "${local.stack_name}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(var.worker_cpu)
  memory                   = tostring(var.worker_memory)
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "worker"
      image     = local.worker_image
      essential = true
      command = [
        "celery",
        "-A",
        "app.workers.celery_app.celery_app",
        "worker",
        "--loglevel=info",
        "--concurrency",
        tostring(var.worker_celery_concurrency),
      ]
      environment = local.worker_environment
      secrets     = local.worker_secrets
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.worker.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "worker"
        }
      }
    }
  ])

  tags = local.tags
}

resource "aws_ecs_task_definition" "frontend" {
  family                   = "${local.stack_name}-frontend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(var.frontend_cpu)
  memory                   = tostring(var.frontend_memory)
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "frontend"
      image     = local.frontend_image
      essential = true
      portMappings = [
        {
          containerPort = 3000
          hostPort      = 3000
          protocol      = "tcp"
        }
      ]
      environment = local.frontend_environment
      healthCheck = {
        command     = ["CMD-SHELL", "wget -q -O /dev/null http://localhost:3000 || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 30
      }
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.frontend.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "frontend"
        }
      }
    }
  ])

  tags = local.tags
}

resource "aws_ecs_task_definition" "migrate" {
  family                   = "${local.stack_name}-migrate"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "migrate"
      image     = local.api_image
      essential = true
      command   = ["alembic", "upgrade", "head"]
      environment = [
        { name = "REDIS_URL", value = local.redis_url },
        { name = "S3_BUCKET", value = aws_s3_bucket.artifacts.bucket },
        { name = "MINIO_BUCKET", value = aws_s3_bucket.artifacts.bucket },
        { name = "S3_REGION", value = var.aws_region },
        { name = "S3_SECURE", value = "true" },
        { name = "S3_SSE_KMS_KEY_ID", value = aws_kms_key.artifacts.arn },
      ]
      secrets = [
        {
          name      = "DATABASE_URL"
          valueFrom = aws_secretsmanager_secret.database_url.arn
        },
        {
          name      = "AUTH_SECRET_KEY"
          valueFrom = var.auth_secret_arn
        },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.api.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "migrate"
        }
      }
    }
  ])

  tags = local.tags
}

resource "aws_ecs_service" "api" {
  name            = "${local.stack_name}-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.api_desired_count
  launch_type     = "FARGATE"

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8002
  }

  force_new_deployment = true

  depends_on = [aws_lb_listener.https]

  tags = local.tags
}

resource "aws_ecs_service" "worker" {
  name            = "${local.stack_name}-worker"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = var.worker_desired_count
  launch_type     = "FARGATE"

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  force_new_deployment = true

  tags = local.tags
}

resource "aws_ecs_service" "frontend" {
  name            = "${local.stack_name}-frontend"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.frontend.arn
  desired_count   = var.frontend_desired_count
  launch_type     = "FARGATE"

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.frontend.arn
    container_name   = "frontend"
    container_port   = 3000
  }

  force_new_deployment = true

  depends_on = [aws_lb_listener.https]

  tags = local.tags
}
