variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "us-east-1"
}

variable "name_prefix" {
  description = "Project name prefix used in resource names"
  type        = string
  default     = "peregrine"
}

variable "environment" {
  description = "Deployment environment label"
  type        = string
  default     = "prod"
}

variable "tags" {
  description = "Additional tags applied to all resources"
  type        = map(string)
  default     = {}
}

variable "vpc_id" {
  description = "Existing VPC ID"
  type        = string
}

variable "public_subnet_ids" {
  description = "Public subnet IDs used by the ALB"
  type        = list(string)
}

variable "private_subnet_ids" {
  description = "Private subnet IDs used by ECS, RDS, and Redis"
  type        = list(string)
}

variable "route53_zone_id" {
  description = "Route53 hosted zone ID for domain records"
  type        = string
}

variable "domain_name" {
  description = "Base domain name (example.com)"
  type        = string
}

variable "frontend_subdomain" {
  description = "Subdomain label for frontend"
  type        = string
  default     = "peregrine"
}

variable "api_subdomain" {
  description = "Subdomain label for API"
  type        = string
  default     = "peregrine-api"
}

variable "acm_certificate_arn" {
  description = "ACM certificate ARN for HTTPS listener"
  type        = string
}

variable "api_image_tag" {
  description = "Container image tag for API service"
  type        = string
  default     = "latest"
}

variable "worker_image_tag" {
  description = "Container image tag for worker service"
  type        = string
  default     = "latest"
}

variable "frontend_image_tag" {
  description = "Container image tag for frontend service"
  type        = string
  default     = "latest"
}

variable "ecr_image_tag_mutability" {
  description = "ECR image tag mutability"
  type        = string
  default     = "MUTABLE"
}

variable "ecr_scan_on_push" {
  description = "Enable ECR image scanning on push"
  type        = bool
  default     = true
}

variable "api_desired_count" {
  description = "Desired API tasks"
  type        = number
  default     = 2
}

variable "api_min_count" {
  description = "Minimum API tasks"
  type        = number
  default     = 2
}

variable "api_max_count" {
  description = "Maximum API tasks"
  type        = number
  default     = 12
}

variable "api_cpu" {
  description = "API task CPU"
  type        = number
  default     = 1024
}

variable "api_memory" {
  description = "API task memory in MiB"
  type        = number
  default     = 2048
}

variable "api_uvicorn_workers" {
  description = "Uvicorn worker count for API container"
  type        = number
  default     = 2
}

variable "api_target_cpu_utilization" {
  description = "API autoscaling CPU target percent"
  type        = number
  default     = 60
}

variable "worker_desired_count" {
  description = "Desired worker tasks"
  type        = number
  default     = 2
}

variable "worker_min_count" {
  description = "Minimum worker tasks"
  type        = number
  default     = 2
}

variable "worker_max_count" {
  description = "Maximum worker tasks"
  type        = number
  default     = 20
}

variable "worker_cpu" {
  description = "Worker task CPU"
  type        = number
  default     = 2048
}

variable "worker_memory" {
  description = "Worker task memory in MiB"
  type        = number
  default     = 4096
}

variable "worker_celery_concurrency" {
  description = "Celery worker concurrency"
  type        = number
  default     = 2
}

variable "worker_target_cpu_utilization" {
  description = "Worker autoscaling CPU target percent"
  type        = number
  default     = 65
}

variable "frontend_desired_count" {
  description = "Desired frontend tasks"
  type        = number
  default     = 2
}

variable "frontend_min_count" {
  description = "Minimum frontend tasks"
  type        = number
  default     = 2
}

variable "frontend_max_count" {
  description = "Maximum frontend tasks"
  type        = number
  default     = 8
}

variable "frontend_cpu" {
  description = "Frontend task CPU"
  type        = number
  default     = 512
}

variable "frontend_memory" {
  description = "Frontend task memory in MiB"
  type        = number
  default     = 1024
}

variable "frontend_target_cpu_utilization" {
  description = "Frontend autoscaling CPU target percent"
  type        = number
  default     = 60
}

variable "log_retention_days" {
  description = "CloudWatch log retention"
  type        = number
  default     = 30
}

variable "db_name" {
  description = "RDS database name"
  type        = string
  default     = "trialai"
}

variable "db_username" {
  description = "RDS database username"
  type        = string
  default     = "trialai_app"
}

variable "db_engine_version" {
  description = "RDS Postgres engine version"
  type        = string
  default     = "16.4"
}

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.r6g.large"
}

variable "db_allocated_storage" {
  description = "RDS allocated storage GB"
  type        = number
  default     = 100
}

variable "db_max_allocated_storage" {
  description = "RDS autoscaling max storage GB"
  type        = number
  default     = 500
}

variable "db_backup_retention_days" {
  description = "RDS backup retention days"
  type        = number
  default     = 7
}

variable "db_multi_az" {
  description = "Enable multi-AZ RDS"
  type        = bool
  default     = true
}

variable "db_deletion_protection" {
  description = "Enable RDS deletion protection"
  type        = bool
  default     = true
}

variable "db_skip_final_snapshot" {
  description = "Skip final snapshot on RDS deletion"
  type        = bool
  default     = false
}

variable "redis_node_type" {
  description = "ElastiCache node type"
  type        = string
  default     = "cache.r7g.large"
}

variable "redis_engine_version" {
  description = "ElastiCache Redis engine version"
  type        = string
  default     = "7.1"
}

variable "redis_num_cache_clusters" {
  description = "Number of Redis cache clusters"
  type        = number
  default     = 2
}

variable "redis_at_rest_encryption_enabled" {
  description = "Enable Redis at-rest encryption"
  type        = bool
  default     = true
}

variable "redis_transit_encryption_enabled" {
  description = "Enable Redis in-transit encryption"
  type        = bool
  default     = true
}

variable "s3_bucket_name" {
  description = "Existing S3 bucket name. Leave empty to create a generated name."
  type        = string
  default     = ""
}

variable "s3_force_destroy" {
  description = "Allow Terraform to delete non-empty artifact bucket"
  type        = bool
  default     = false
}

variable "s3_versioning_enabled" {
  description = "Enable S3 bucket versioning"
  type        = bool
  default     = false
}

variable "s3_kms_key_arn" {
  description = "Existing KMS key ARN for S3 encryption. Leave empty to create one."
  type        = string
  default     = ""
}

variable "s3_cors_allowed_origins" {
  description = "Allowed origins for S3 browser uploads via presigned URLs"
  type        = list(string)
  default     = []
}

variable "auth_secret_arn" {
  description = "Secrets Manager ARN containing AUTH_SECRET_KEY"
  type        = string
}

variable "cookie_domain" {
  description = "Cookie domain (defaults to .<domain_name>)"
  type        = string
  default     = ""
}

variable "cors_allow_origins" {
  description = "CORS allow origins for API"
  type        = list(string)
  default     = []
}

variable "auth_rate_limit_enabled" {
  description = "Enable auth endpoint rate limiting"
  type        = bool
  default     = true
}

variable "auth_rate_limit_backend" {
  description = "Auth rate limit backend"
  type        = string
  default     = "redis"
}

variable "auth_rate_limit_window_seconds" {
  description = "Auth rate limit window seconds"
  type        = number
  default     = 60
}

variable "auth_rate_limit_max_attempts" {
  description = "Auth rate limit max attempts per window"
  type        = number
  default     = 10
}

variable "auth_email_sender" {
  description = "From address used for password reset emails"
  type        = string
  default     = ""
}

variable "auth_email_region" {
  description = "AWS SES region for password reset emails"
  type        = string
  default     = ""
}

variable "auth_mfa_issuer" {
  description = "Issuer label shown in authenticator apps"
  type        = string
  default     = "Acquittify"
}

variable "ses_sender_identity_arn" {
  description = "Optional SES identity ARN allowed for SendEmail"
  type        = string
  default     = ""
}

variable "frontend_next_public_api_url" {
  description = "Frontend API base URL baked at image build time"
  type        = string
  default     = ""
}

variable "dropbox_case_root_path" {
  description = "Dropbox case root path"
  type        = string
  default     = ""
}

variable "dropbox_case_root_link" {
  description = "Dropbox shared link root if using shared links"
  type        = string
  default     = ""
}

variable "llm_model" {
  description = "Default LLM model"
  type        = string
  default     = "acquittify-qwen"
}

variable "agent_model" {
  description = "Agent model used by /agent/chat (if empty, uses llm_model)"
  type        = string
  default     = ""
}

variable "openclaw_agent_id" {
  description = "OpenClaw agent ID sent as x-openclaw-agent-id when LLM_BASE_URL is set"
  type        = string
  default     = "main"
}

variable "llm_base_url" {
  description = "Optional LLM API base URL (OpenAI-compatible, e.g. Ollama gateway)"
  type        = string
  default     = ""
}

variable "llm_repair_model" {
  description = "LLM repair model"
  type        = string
  default     = "acquittify-qwen"
}

variable "embedding_model" {
  description = "Embedding model"
  type        = string
  default     = "nomic-embed-text"
}

variable "embedding_dim" {
  description = "Embedding dimensions"
  type        = number
  default     = 768
}

variable "dropbox_access_token_secret_arn" {
  description = "Optional Dropbox access token secret ARN"
  type        = string
  default     = ""
}

variable "dropbox_refresh_token_secret_arn" {
  description = "Optional Dropbox refresh token secret ARN"
  type        = string
  default     = ""
}

variable "dropbox_app_key_secret_arn" {
  description = "Optional Dropbox app key secret ARN"
  type        = string
  default     = ""
}

variable "dropbox_app_secret_secret_arn" {
  description = "Optional Dropbox app secret secret ARN"
  type        = string
  default     = ""
}

variable "dropbox_team_member_id_secret_arn" {
  description = "Optional Dropbox team member ID secret ARN"
  type        = string
  default     = ""
}

variable "openai_api_key_secret_arn" {
  description = "Optional OpenAI API key secret ARN"
  type        = string
  default     = ""
}

variable "llm_api_key_secret_arn" {
  description = "Optional LLM API key secret ARN for LLM_BASE_URL providers"
  type        = string
  default     = ""
}

variable "courtlistener_api_token_secret_arn" {
  description = "Optional CourtListener API token secret ARN for caselaw ingest scheduler job"
  type        = string
  default     = ""
}

variable "caselaw_scheduler_enabled" {
  description = "Enable EventBridge Scheduler for caselaw ingest ECS task"
  type        = bool
  default     = true
}

variable "caselaw_schedule_expression" {
  description = "EventBridge schedule expression for caselaw ingest (for example, rate(30 minutes) or cron(...))"
  type        = string
  default     = "rate(30 minutes)"
}

variable "caselaw_schedule_timezone" {
  description = "Timezone for cron-based caselaw schedule expressions"
  type        = string
  default     = "America/Detroit"
}

variable "caselaw_task_cpu" {
  description = "Caselaw ingest ECS task CPU units"
  type        = number
  default     = 1024
}

variable "caselaw_task_memory" {
  description = "Caselaw ingest ECS task memory in MiB"
  type        = number
  default     = 2048
}

variable "caselaw_job_max_runtime_hours" {
  description = "Maximum runtime hours per scheduled caselaw ingest task"
  type        = number
  default     = 0.33
}

variable "caselaw_job_backfill_start_date" {
  description = "Earliest filing date to scan while backfilling (YYYY-MM-DD)"
  type        = string
  default     = "2011-01-01"
}

variable "caselaw_job_max_court_date_queries" {
  description = "Maximum court/date query steps per scheduled run"
  type        = number
  default     = 120
}

variable "caselaw_job_page_size" {
  description = "CourtListener search page size per query"
  type        = number
  default     = 40
}

variable "caselaw_job_max_pages_per_query" {
  description = "Maximum result pages fetched per court/date query"
  type        = number
  default     = 20
}

variable "caselaw_job_request_timeout_seconds" {
  description = "CourtListener request timeout in seconds"
  type        = number
  default     = 30
}

variable "caselaw_job_request_pause_seconds" {
  description = "Pause between CourtListener requests in seconds"
  type        = number
  default     = 0.1
}

variable "caselaw_job_request_retries" {
  description = "Retry attempts for CourtListener requests"
  type        = number
  default     = 5
}

variable "caselaw_job_include_quasi_criminal" {
  description = "Include quasi-criminal cases (habeas/post-conviction) in scheduled caselaw ingest"
  type        = bool
  default     = true
}

variable "caselaw_job_only_courts" {
  description = "Optional comma-separated court IDs to restrict scheduled ingest"
  type        = string
  default     = ""
}

variable "openclaw_gateway_enabled" {
  description = "Enable internal OpenClaw gateway infrastructure (EC2 + internal NLB + private DNS)"
  type        = bool
  default     = false
}

variable "openclaw_gateway_instance_type" {
  description = "Instance type for the OpenClaw gateway host"
  type        = string
  default     = "t3.small"
}

variable "openclaw_gateway_subnet_id" {
  description = "Optional subnet ID override for OpenClaw gateway EC2 (defaults to first private subnet)"
  type        = string
  default     = ""
}

variable "openclaw_gateway_ami_id" {
  description = "Optional AMI ID override for OpenClaw gateway EC2 (defaults to latest Amazon Linux 2023)"
  type        = string
  default     = ""
}

variable "openclaw_gateway_node_version" {
  description = "Node.js version installed on the OpenClaw gateway host"
  type        = string
  default     = "v22.14.0"
}

variable "openclaw_gateway_openclaw_version" {
  description = "OpenClaw npm version installed on the OpenClaw gateway host"
  type        = string
  default     = "2026.3.8"
}

variable "openclaw_gateway_bind" {
  description = "OpenClaw gateway bind mode on EC2 (loopback|lan|tailnet|auto|custom)"
  type        = string
  default     = "lan"
}

variable "openclaw_gateway_port" {
  description = "OpenClaw gateway TCP port"
  type        = number
  default     = 18789
}

variable "openclaw_gateway_agent_id" {
  description = "OpenClaw dedicated agent ID used by Acquittify traffic"
  type        = string
  default     = "acquittify"
}

variable "openclaw_private_zone_name" {
  description = "Private Route53 zone name used for OpenClaw internal DNS"
  type        = string
  default     = "acquittify.internal"
}

variable "openclaw_private_zone_id" {
  description = "Optional existing private Route53 hosted zone ID for OpenClaw DNS (leave empty to create)"
  type        = string
  default     = ""
}

variable "openclaw_gateway_dns_record" {
  description = "Record name in the private OpenClaw zone (for example openclaw-gateway)"
  type        = string
  default     = "openclaw-gateway"
}
