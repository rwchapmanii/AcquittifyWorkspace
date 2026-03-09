resource "random_password" "db_password" {
  length  = 32
  special = true
}

resource "aws_db_subnet_group" "main" {
  name       = "${local.stack_name}-db-subnets"
  subnet_ids = var.private_subnet_ids

  tags = local.tags
}

resource "aws_db_instance" "main" {
  identifier                   = "${local.stack_name}-pg"
  engine                       = "postgres"
  engine_version               = var.db_engine_version
  instance_class               = var.db_instance_class
  db_name                      = var.db_name
  username                     = var.db_username
  password                     = random_password.db_password.result
  port                         = 5432
  allocated_storage            = var.db_allocated_storage
  max_allocated_storage        = var.db_max_allocated_storage
  storage_encrypted            = true
  backup_retention_period      = var.db_backup_retention_days
  multi_az                     = var.db_multi_az
  deletion_protection          = var.db_deletion_protection
  skip_final_snapshot          = var.db_skip_final_snapshot
  final_snapshot_identifier    = var.db_skip_final_snapshot ? null : "${local.stack_name}-final"
  publicly_accessible          = false
  auto_minor_version_upgrade   = true
  performance_insights_enabled = true

  vpc_security_group_ids = [aws_security_group.rds.id]
  db_subnet_group_name   = aws_db_subnet_group.main.name

  tags = local.tags
}

locals {
  database_url = format(
    "postgresql+psycopg://%s:%s@%s:5432/%s?sslmode=require",
    var.db_username,
    urlencode(random_password.db_password.result),
    aws_db_instance.main.address,
    var.db_name
  )
}

resource "aws_secretsmanager_secret" "database_url" {
  name = "${local.stack_name}/database-url"

  tags = local.tags
}

resource "aws_secretsmanager_secret_version" "database_url" {
  secret_id     = aws_secretsmanager_secret.database_url.id
  secret_string = local.database_url
}
