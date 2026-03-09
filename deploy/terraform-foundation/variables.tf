variable "aws_region" {
  description = "AWS region for foundational resources"
  type        = string
  default     = "us-east-1"
}

variable "vpc_cidr" {
  description = "CIDR block for the managed VPC"
  type        = string
  default     = "10.20.0.0/16"
}

variable "domain_name" {
  description = "Primary domain name (e.g. acquittify.ai)"
  type        = string
  default     = "acquittify.ai"
}

variable "auth_secret_name" {
  description = "Name for the Secrets Manager secret that stores AUTH_SECRET_KEY"
  type        = string
  default     = "acquittify-auth-secret"
}
