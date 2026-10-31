# One item per device and per accepted reading (docs/decisions/0004-per-device-dynamodb-items.md).
resource "aws_dynamodb_table" "fleet" {
  name         = "${local.name}-fleet"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"
  attribute {
    name = "pk"
    type = "S"
  }
  attribute {
    name = "sk"
    type = "S"
  }
  ttl {
    attribute_name = "expiresAt"
    enabled        = true
  }
  point_in_time_recovery { enabled = var.point_in_time_recovery }
  server_side_encryption { enabled = true }
}

# The v1.0.0 single-item table leaves Terraform state without being deleted, so
# the previous release can be restored. Delete it by hand after the cut-over.
removed {
  from = aws_dynamodb_table.state
  lifecycle {
    destroy = false
  }
}

resource "aws_sqs_queue" "dead_letter" {
  name                      = "${local.name}-dead-letter"
  message_retention_seconds = 604800
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "telemetry" {
  name                       = "${local.name}-telemetry"
  message_retention_seconds  = 86400
  visibility_timeout_seconds = 180
  sqs_managed_sse_enabled    = true
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dead_letter.arn
    maxReceiveCount     = 5
  })
}

resource "aws_sqs_queue_redrive_allow_policy" "dead_letter" {
  queue_url = aws_sqs_queue.dead_letter.id
  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.telemetry.arn]
  })
}

resource "aws_cognito_user_pool" "operators" {
  name                     = "${local.name}-operators"
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]
  admin_create_user_config { allow_admin_create_user_only = true }
  password_policy {
    minimum_length                   = 12
    require_lowercase                = true
    require_uppercase                = true
    require_numbers                  = true
    require_symbols                  = true
    temporary_password_validity_days = 1
  }
}

resource "aws_cognito_user_pool_client" "dashboard" {
  name                          = "${local.name}-dashboard"
  user_pool_id                  = aws_cognito_user_pool.operators.id
  generate_secret               = false
  prevent_user_existence_errors = "ENABLED"
  explicit_auth_flows           = ["ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]
  access_token_validity         = 1
  id_token_validity             = 1
  refresh_token_validity        = 1
  enable_token_revocation       = true
  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }
}
