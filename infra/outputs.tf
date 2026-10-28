output "website_url" {
  description = "CloudFront dashboard URL. Create a Cognito operator and complete cloud acceptance checks after deployment."
  value       = local.cloud_origin
}

output "api_url" { value = aws_apigatewayv2_api.backend.api_endpoint }
output "user_pool_id" { value = aws_cognito_user_pool.operators.id }
output "user_pool_client_id" { value = aws_cognito_user_pool_client.dashboard.id }
output "frontend_bucket" { value = aws_s3_bucket.frontend.id }
output "distribution_id" { value = aws_cloudfront_distribution.frontend.id }
output "telemetry_queue_url" { value = aws_sqs_queue.telemetry.url }
output "dead_letter_queue_url" { value = aws_sqs_queue.dead_letter.url }

output "cloud_config" {
  value = {
    mode       = "aws"
    apiBaseUrl = aws_apigatewayv2_api.backend.api_endpoint
    region     = var.region
    userPoolId = aws_cognito_user_pool.operators.id
    clientId   = aws_cognito_user_pool_client.dashboard.id
  }
}
