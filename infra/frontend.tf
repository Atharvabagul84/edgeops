resource "aws_s3_bucket" "frontend" {
  bucket        = "${local.name}-${data.aws_caller_identity.current.account_id}-${var.region}"
  force_destroy = false
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket                  = aws_s3_bucket.frontend.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_cloudfront_origin_access_control" "frontend" {
  name                              = local.name
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_response_headers_policy" "frontend" {
  name = local.name
  security_headers_config {
    content_security_policy {
      content_security_policy = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' https://*.execute-api.${var.region}.amazonaws.com https://cognito-idp.${var.region}.amazonaws.com; object-src 'none'; frame-ancestors 'none'; base-uri 'none'"
      override                = true
    }
    content_type_options { override = true }
    frame_options {
      frame_option = "DENY"
      override     = true
    }
    referrer_policy {
      referrer_policy = "same-origin"
      override        = true
    }
    strict_transport_security {
      access_control_max_age_sec = 31536000
      include_subdomains         = true
      override                   = true
    }
  }
}

resource "aws_cloudfront_distribution" "frontend" {
  enabled             = true
  default_root_object = "index.html"
  price_class         = "PriceClass_100"
  origin {
    domain_name              = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_id                = "private-s3"
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id
  }
  default_cache_behavior {
    target_origin_id           = "private-s3"
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    min_ttl                    = 0
    default_ttl                = 60
    max_ttl                    = 300
    response_headers_policy_id = aws_cloudfront_response_headers_policy.frontend.id
    forwarded_values {
      query_string = false
      cookies { forward = "none" }
    }
  }
  restrictions {
    geo_restriction { restriction_type = "none" }
  }
  viewer_certificate { cloudfront_default_certificate = true }
}

resource "aws_s3_bucket_policy" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "CloudFrontReadOnly"
        Effect    = "Allow"
        Principal = { Service = "cloudfront.amazonaws.com" }
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.frontend.arn}/*"
        Condition = { StringEquals = { "AWS:SourceArn" = aws_cloudfront_distribution.frontend.arn } }
      },
      {
        Sid       = "RequireTLS"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource  = [aws_s3_bucket.frontend.arn, "${aws_s3_bucket.frontend.arn}/*"]
        Condition = { Bool = { "aws:SecureTransport" = "false" } }
      }
    ]
  })
}

locals {
  asset_types    = { html = "text/html; charset=utf-8", css = "text/css; charset=utf-8", js = "application/javascript; charset=utf-8", svg = "image/svg+xml", json = "application/json" }
  frontend_files = setsubtract(fileset(local.frontend_dir, "**"), fileset(local.frontend_dir, "**/*.test.*"))
}

resource "aws_s3_object" "frontend" {
  for_each      = local.frontend_files
  bucket        = aws_s3_bucket.frontend.id
  key           = each.value
  source        = "${local.frontend_dir}/${each.value}"
  etag          = filemd5("${local.frontend_dir}/${each.value}")
  content_type  = lookup(local.asset_types, reverse(split(".", each.value))[0], "application/octet-stream")
  cache_control = "public, max-age=60"
}

resource "aws_s3_object" "cloud_config" {
  bucket        = aws_s3_bucket.frontend.id
  key           = "cloud-config.json"
  content_type  = "application/json"
  cache_control = "no-store"
  content = jsonencode({
    mode       = "aws"
    apiBaseUrl = aws_apigatewayv2_api.backend.api_endpoint
    region     = var.region
    userPoolId = aws_cognito_user_pool.operators.id
    clientId   = aws_cognito_user_pool_client.dashboard.id
  })
}
