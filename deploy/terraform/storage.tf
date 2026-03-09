resource "random_id" "bucket_suffix" {
  byte_length = 4
}

locals {
  artifact_bucket_name = (
    var.s3_bucket_name != ""
    ? var.s3_bucket_name
    : "${local.stack_name}-artifacts-${random_id.bucket_suffix.hex}"
  )

  artifact_bucket_kms_key_arn = (
    var.s3_kms_key_arn != ""
    ? var.s3_kms_key_arn
    : aws_kms_key.artifacts[0].arn
  )
}

resource "aws_kms_key" "artifacts" {
  count = var.s3_kms_key_arn == "" ? 1 : 0

  description             = "KMS key for ${local.stack_name} artifacts bucket"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  tags = local.tags
}

resource "aws_kms_alias" "artifacts" {
  count = var.s3_kms_key_arn == "" ? 1 : 0

  name          = "alias/${local.stack_name}-artifacts"
  target_key_id = aws_kms_key.artifacts[0].key_id
}

resource "aws_s3_bucket" "artifacts" {
  bucket        = local.artifact_bucket_name
  force_destroy = var.s3_force_destroy

  tags = local.tags
}

resource "aws_s3_bucket_ownership_controls" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  versioning_configuration {
    status = var.s3_versioning_enabled ? "Enabled" : "Suspended"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = local.artifact_bucket_kms_key_arn
      sse_algorithm     = "aws:kms"
    }
  }
}

data "aws_iam_policy_document" "artifacts_tls_only" {
  statement {
    sid    = "DenyInsecureTransport"
    effect = "Deny"

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    actions = ["s3:*"]

    resources = [
      aws_s3_bucket.artifacts.arn,
      "${aws_s3_bucket.artifacts.arn}/*",
    ]

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  policy = data.aws_iam_policy_document.artifacts_tls_only.json
}

resource "aws_s3_bucket_cors_configuration" "artifacts" {
  count = length(var.s3_cors_allowed_origins) > 0 ? 1 : 0

  bucket = aws_s3_bucket.artifacts.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "HEAD", "PUT"]
    allowed_origins = var.s3_cors_allowed_origins
    expose_headers  = ["ETag"]
    max_age_seconds = 3000
  }
}
