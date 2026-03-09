data "aws_vpc" "selected" {
  count = var.openclaw_gateway_enabled ? 1 : 0
  id    = var.vpc_id
}

data "aws_ssm_parameter" "openclaw_al2023_ami" {
  count = var.openclaw_gateway_enabled && var.openclaw_gateway_ami_id == "" ? 1 : 0
  name  = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

locals {
  openclaw_zone_name            = trimsuffix(var.openclaw_private_zone_name, ".")
  openclaw_gateway_dns_name     = var.openclaw_gateway_dns_record == "" ? local.openclaw_zone_name : "${var.openclaw_gateway_dns_record}.${local.openclaw_zone_name}"
  openclaw_gateway_base_url     = "http://${local.openclaw_gateway_dns_name}:${var.openclaw_gateway_port}/v1/responses"
  openclaw_gateway_effective_az = var.openclaw_gateway_subnet_id != "" ? var.openclaw_gateway_subnet_id : var.private_subnet_ids[0]
  openclaw_gateway_zone_id      = var.openclaw_private_zone_id != "" ? var.openclaw_private_zone_id : try(aws_route53_zone.openclaw_private[0].zone_id, "")
}

resource "aws_security_group" "openclaw_gateway" {
  count       = var.openclaw_gateway_enabled ? 1 : 0
  name        = "${local.stack_name}-openclaw-sg"
  description = "OpenClaw gateway ingress for ECS and internal health checks"
  vpc_id      = var.vpc_id

  ingress {
    description     = "OpenClaw API from ECS tasks"
    from_port       = var.openclaw_gateway_port
    to_port         = var.openclaw_gateway_port
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs_tasks.id]
  }

  ingress {
    description = "VPC internal (NLB health checks)"
    from_port   = var.openclaw_gateway_port
    to_port     = var.openclaw_gateway_port
    protocol    = "tcp"
    cidr_blocks = [data.aws_vpc.selected[0].cidr_block]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.tags, { Name = "${local.stack_name}-openclaw-sg" })
}

data "aws_iam_policy_document" "openclaw_gateway_assume_role" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "openclaw_gateway" {
  count              = var.openclaw_gateway_enabled ? 1 : 0
  name               = "${local.stack_name}-openclaw-ec2-role"
  assume_role_policy = data.aws_iam_policy_document.openclaw_gateway_assume_role.json
  tags               = local.tags
}

resource "aws_iam_role_policy_attachment" "openclaw_gateway_ssm" {
  count      = var.openclaw_gateway_enabled ? 1 : 0
  role       = aws_iam_role.openclaw_gateway[0].name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "openclaw_gateway_secrets" {
  statement {
    effect = "Allow"

    actions = [
      "secretsmanager:GetSecretValue",
    ]

    resources = compact([
      var.llm_api_key_secret_arn,
      var.openai_api_key_secret_arn,
    ])
  }
}

resource "aws_iam_role_policy" "openclaw_gateway_secrets" {
  count  = var.openclaw_gateway_enabled ? 1 : 0
  name   = "${local.stack_name}-openclaw-secrets"
  role   = aws_iam_role.openclaw_gateway[0].id
  policy = data.aws_iam_policy_document.openclaw_gateway_secrets.json
}

resource "aws_iam_instance_profile" "openclaw_gateway" {
  count = var.openclaw_gateway_enabled ? 1 : 0
  name  = "${local.stack_name}-openclaw-ec2-profile"
  role  = aws_iam_role.openclaw_gateway[0].name
}

resource "aws_instance" "openclaw_gateway" {
  count                       = var.openclaw_gateway_enabled ? 1 : 0
  ami                         = var.openclaw_gateway_ami_id != "" ? var.openclaw_gateway_ami_id : data.aws_ssm_parameter.openclaw_al2023_ami[0].value
  instance_type               = var.openclaw_gateway_instance_type
  subnet_id                   = local.openclaw_gateway_effective_az
  vpc_security_group_ids      = [aws_security_group.openclaw_gateway[0].id]
  iam_instance_profile        = aws_iam_instance_profile.openclaw_gateway[0].name
  associate_public_ip_address = false

  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }

  user_data = templatefile(
    "${path.module}/templates/openclaw-userdata.sh.tftpl",
    {
      aws_region        = var.aws_region
      gateway_bind      = var.openclaw_gateway_bind
      gateway_port      = var.openclaw_gateway_port
      openai_secret_arn = var.openai_api_key_secret_arn
      openclaw_agent_id = var.openclaw_gateway_agent_id
      openclaw_version  = var.openclaw_gateway_openclaw_version
      token_secret_arn  = var.llm_api_key_secret_arn
      node_version      = var.openclaw_gateway_node_version
    }
  )

  tags = merge(local.tags, { Name = "${local.stack_name}-openclaw-gateway" })

  lifecycle {
    precondition {
      condition     = var.llm_api_key_secret_arn != ""
      error_message = "llm_api_key_secret_arn must be set when openclaw_gateway_enabled=true."
    }
    precondition {
      condition     = var.openai_api_key_secret_arn != ""
      error_message = "openai_api_key_secret_arn must be set when openclaw_gateway_enabled=true."
    }
  }
}

resource "aws_lb" "openclaw_internal" {
  count              = var.openclaw_gateway_enabled ? 1 : 0
  name               = substr(replace("${local.stack_name}-openclaw-nlb", "_", "-"), 0, 32)
  load_balancer_type = "network"
  internal           = true
  subnets            = var.private_subnet_ids

  tags = merge(local.tags, { Name = "${local.stack_name}-openclaw-nlb" })
}

resource "aws_lb_target_group" "openclaw_internal" {
  count       = var.openclaw_gateway_enabled ? 1 : 0
  name        = substr(replace("${local.stack_name}-openclaw-tg", "_", "-"), 0, 32)
  port        = var.openclaw_gateway_port
  protocol    = "TCP"
  target_type = "instance"
  vpc_id      = var.vpc_id

  health_check {
    protocol = "TCP"
    port     = tostring(var.openclaw_gateway_port)
  }

  tags = merge(local.tags, { Name = "${local.stack_name}-openclaw-tg" })
}

resource "aws_lb_target_group_attachment" "openclaw_internal" {
  count            = var.openclaw_gateway_enabled ? 1 : 0
  target_group_arn = aws_lb_target_group.openclaw_internal[0].arn
  target_id        = aws_instance.openclaw_gateway[0].id
  port             = var.openclaw_gateway_port
}

resource "aws_lb_listener" "openclaw_internal" {
  count             = var.openclaw_gateway_enabled ? 1 : 0
  load_balancer_arn = aws_lb.openclaw_internal[0].arn
  port              = var.openclaw_gateway_port
  protocol          = "TCP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.openclaw_internal[0].arn
  }
}

resource "aws_route53_zone" "openclaw_private" {
  count = var.openclaw_gateway_enabled && var.openclaw_private_zone_id == "" ? 1 : 0
  name  = local.openclaw_zone_name

  vpc {
    vpc_id = var.vpc_id
  }

  tags = merge(local.tags, { Name = "${local.stack_name}-openclaw-private-zone" })
}

resource "aws_route53_record" "openclaw_internal" {
  count   = var.openclaw_gateway_enabled ? 1 : 0
  zone_id = local.openclaw_gateway_zone_id
  name    = local.openclaw_gateway_dns_name
  type    = "A"

  alias {
    name                   = aws_lb.openclaw_internal[0].dns_name
    zone_id                = aws_lb.openclaw_internal[0].zone_id
    evaluate_target_health = false
  }
}
