output "vpc_id" {
  description = "Managed VPC ID"
  value       = aws_vpc.primary.id
}

output "public_subnet_ids" {
  description = "Managed public subnet IDs"
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "Managed private subnet IDs"
  value       = aws_subnet.private[*].id
}

output "acm_certificate_arn" {
  description = "Validated ACM certificate ARN"
  value       = aws_acm_certificate_validation.primary.certificate_arn
}

output "route53_zone_id" {
  description = "Route53 hosted zone ID"
  value       = data.aws_route53_zone.primary.zone_id
}

output "auth_secret_arn" {
  description = "Secrets Manager ARN for AUTH_SECRET_KEY"
  value       = aws_secretsmanager_secret.auth.arn
}
