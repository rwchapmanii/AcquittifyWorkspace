resource "aws_elasticache_subnet_group" "main" {
  name       = "${local.stack_name}-redis-subnets"
  subnet_ids = var.private_subnet_ids

  tags = local.tags
}

resource "aws_elasticache_replication_group" "main" {
  replication_group_id       = replace("${local.stack_name}-redis", "_", "-")
  description                = "${local.stack_name} redis"
  node_type                  = var.redis_node_type
  engine                     = "redis"
  engine_version             = var.redis_engine_version
  parameter_group_name       = "default.redis7"
  port                       = 6379
  automatic_failover_enabled = true
  multi_az_enabled           = true
  num_cache_clusters         = var.redis_num_cache_clusters
  subnet_group_name          = aws_elasticache_subnet_group.main.name
  security_group_ids         = [aws_security_group.redis.id]

  at_rest_encryption_enabled = var.redis_at_rest_encryption_enabled
  transit_encryption_enabled = var.redis_transit_encryption_enabled

  tags = local.tags
}

locals {
  redis_scheme = var.redis_transit_encryption_enabled ? "rediss" : "redis"
  redis_url = format(
    "%s://%s:6379/0",
    local.redis_scheme,
    aws_elasticache_replication_group.main.primary_endpoint_address
  )
}
