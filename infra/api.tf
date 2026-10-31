data "archive_file" "backend" {
  type        = "zip"
  output_path = "${path.module}/.lambda.zip"
  dynamic "source" {
    for_each = fileset("${path.module}/../backend", "*.py")
    content {
      content  = file("${path.module}/../backend/${source.value}")
      filename = "backend/${source.value}"
    }
  }
}

resource "aws_iam_role" "lambda" {
  for_each = toset(["api", "worker"])
  name     = "${local.name}-${each.key}"

  # Required by the GitHub apply role (infra/bootstrap); empty only for legacy local applies.
  permissions_boundary = var.permissions_boundary_arn == "" ? null : var.permissions_boundary_arn
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_cloudwatch_log_group" "lambda" {
  for_each          = toset(["api", "worker"])
  name              = "/aws/lambda/${local.name}-${each.key}"
  retention_in_days = 3
}

resource "aws_iam_role_policy" "lambda" {
  for_each = toset(["api", "worker"])
  role     = aws_iam_role.lambda[each.key].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.lambda[each.key].arn}:*" },
      { Effect = "Allow", Action = ["dynamodb:GetItem", "dynamodb:BatchGetItem", "dynamodb:PutItem"], Resource = aws_dynamodb_table.fleet.arn },
      { Effect = "Allow", Action = each.key == "api" ? ["sqs:SendMessage"] : ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"], Resource = aws_sqs_queue.telemetry.arn }
    ]
  })
}

resource "aws_lambda_function" "service" {
  for_each         = toset(["api", "worker"])
  function_name    = "${local.name}-${each.key}"
  role             = aws_iam_role.lambda[each.key].arn
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "backend.aws_handler.handler"
  filename         = data.archive_file.backend.output_path
  source_code_hash = data.archive_file.backend.output_base64sha256
  memory_size      = 128
  timeout          = 25
  environment {
    variables = {
      FLEET_TABLE = aws_dynamodb_table.fleet.name
      QUEUE_URL   = aws_sqs_queue.telemetry.url
    }
  }
  depends_on = [aws_iam_role_policy.lambda]
}

resource "aws_lambda_event_source_mapping" "telemetry" {
  event_source_arn        = aws_sqs_queue.telemetry.arn
  function_name           = aws_lambda_function.service["worker"].arn
  batch_size              = 5
  function_response_types = ["ReportBatchItemFailures"]
  scaling_config { maximum_concurrency = 2 }
}

resource "aws_apigatewayv2_api" "backend" {
  name          = local.name
  protocol_type = "HTTP"
  cors_configuration {
    allow_origins = [local.cloud_origin]
    allow_headers = ["authorization", "content-type"]
    allow_methods = ["GET", "POST", "OPTIONS"]
    max_age       = 300
  }
}

resource "aws_apigatewayv2_authorizer" "operators" {
  api_id           = aws_apigatewayv2_api.backend.id
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  name             = "cognito-operators"
  jwt_configuration {
    audience = [aws_cognito_user_pool_client.dashboard.id]
    issuer   = "https://cognito-idp.${var.region}.amazonaws.com/${aws_cognito_user_pool.operators.id}"
  }
}

resource "aws_apigatewayv2_integration" "backend" {
  api_id                 = aws_apigatewayv2_api.backend.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.service["api"].invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds   = 29000
}

resource "aws_apigatewayv2_route" "backend" {
  for_each           = toset(["GET /api/health", "GET /api/state", "GET /api/export", "POST /api/actions", "POST /api/telemetry", "POST /api/tick", "POST /api/reset"])
  api_id             = aws_apigatewayv2_api.backend.id
  route_key          = each.key
  target             = "integrations/${aws_apigatewayv2_integration.backend.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.operators.id
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/apigateway/${local.name}"
  retention_in_days = 3
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.backend.id
  name        = "$default"
  auto_deploy = true
  default_route_settings {
    throttling_burst_limit = 5
    throttling_rate_limit  = 2
  }
  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api.arn
    format          = jsonencode({ requestId = "$context.requestId", status = "$context.status", route = "$context.routeKey", latency = "$context.responseLatency" })
  }
}

resource "aws_lambda_permission" "api" {
  statement_id  = "AllowHttpApi"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.service["api"].function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.backend.execution_arn}/*/*"
}
