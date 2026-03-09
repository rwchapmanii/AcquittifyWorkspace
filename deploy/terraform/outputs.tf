output "ecs_cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "api_service_name" {
  value = aws_ecs_service.api.name
}

output "worker_service_name" {
  value = aws_ecs_service.worker.name
}

output "frontend_service_name" {
  value = aws_ecs_service.frontend.name
}

output "migrate_task_definition_arn" {
  value = aws_ecs_task_definition.migrate.arn
}

output "caselaw_ingest_task_definition_arn" {
  value = aws_ecs_task_definition.caselaw_ingest.arn
}

output "caselaw_scheduler_arn" {
  value = var.caselaw_scheduler_enabled ? aws_scheduler_schedule.caselaw_ingest[0].arn : null
}

output "ecs_task_security_group_id" {
  value = aws_security_group.ecs_tasks.id
}

output "private_subnet_ids_csv" {
  value = join(",", var.private_subnet_ids)
}

output "frontend_url" {
  value = "https://${local.frontend_fqdn}"
}

output "api_url" {
  value = "https://${local.api_fqdn}"
}

output "alb_dns_name" {
  value = aws_lb.main.dns_name
}

output "artifact_bucket_name" {
  value = aws_s3_bucket.artifacts.bucket
}

output "artifact_bucket_kms_key_arn" {
  value = local.artifact_bucket_kms_key_arn
}

output "database_endpoint" {
  value = aws_db_instance.main.address
}

output "database_url_secret_arn" {
  value = aws_secretsmanager_secret.database_url.arn
}

output "redis_primary_endpoint" {
  value = aws_elasticache_replication_group.main.primary_endpoint_address
}

output "ecr_api_repository_url" {
  value = aws_ecr_repository.api.repository_url
}

output "ecr_worker_repository_url" {
  value = aws_ecr_repository.worker.repository_url
}

output "ecr_frontend_repository_url" {
  value = aws_ecr_repository.frontend.repository_url
}
