resource "random_password" "auth" {
  length  = 64
  special = true
}

resource "aws_secretsmanager_secret" "auth" {
  name = var.auth_secret_name

  tags = merge(local.tags, {
    Name = var.auth_secret_name
  })
}

resource "aws_secretsmanager_secret_version" "auth" {
  secret_id     = aws_secretsmanager_secret.auth.id
  secret_string = random_password.auth.result
}
