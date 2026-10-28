resource "aws_dynamodb_table" "state" {
  name           = "${local.name}-state"
  billing_mode   = "PROVISIONED"
  read_capacity  = 5
  write_capacity = 25
  hash_key       = "pk"
  attribute {
    name = "pk"
    type = "S"
  }
  server_side_encryption { enabled = true }
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
