locals {
  stack_name = "${var.name_prefix}-${var.environment}"

  frontend_fqdn = (
    var.frontend_subdomain != ""
    ? "${var.frontend_subdomain}.${var.domain_name}"
    : var.domain_name
  )
  api_fqdn = (
    var.api_subdomain != ""
    ? "${var.api_subdomain}.${var.domain_name}"
    : var.domain_name
  )

  effective_cookie_domain = var.cookie_domain != "" ? var.cookie_domain : ".${var.domain_name}"

  effective_cors_allow_origins = (
    length(var.cors_allow_origins) > 0
    ? join(",", var.cors_allow_origins)
    : "https://${local.frontend_fqdn}"
  )
  effective_cors_origin_list = (
    length(var.cors_allow_origins) > 0
    ? var.cors_allow_origins
    : ["https://${local.frontend_fqdn}"]
  )

  effective_frontend_api_url = (
    var.frontend_next_public_api_url != ""
    ? var.frontend_next_public_api_url
    : "https://${local.api_fqdn}"
  )

  tags = merge(
    {
      Project     = "AcquittifyPeregrine"
      Environment = var.environment
      ManagedBy   = "Terraform"
    },
    var.tags
  )
}
