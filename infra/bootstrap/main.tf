# One-time account setup for GitHub Actions deploys. The owner applies this root
# with their own admin credentials and keeps its state locally, outside the repo:
# it creates the remote-state bucket the main stack uses (see docs/guides/github-actions-deploy.md).
terraform {
  required_version = ">= 1.10, < 2.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = { Project = var.project, Environment = "portfolio", ManagedBy = "terraform-bootstrap" }
  }
}

variable "region" {
  type    = string
  default = "ap-southeast-2"
}

variable "project" {
  description = "Must match the main stack's project variable; workload permissions are scoped to this prefix."
  type        = string
  default     = "edgeops-demo"
}

variable "github_repository" {
  description = "owner/name of the repository whose workflows may deploy. Forks set their own."
  type        = string
  default     = "Atharvabagul84/edgeops"
  validation {
    condition     = can(regex("^[A-Za-z0-9-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "Use owner/name."
  }
}

variable "deploy_environment" {
  description = "Protected GitHub environment whose jobs may assume the apply role."
  type        = string
  default     = "production"
}

variable "state_admin_principal_arns" {
  description = "ARNs (wildcards allowed) of the humans who may still read or repair state, e.g. your admin SSO role."
  type        = list(string)
  validation {
    condition     = length(var.state_admin_principal_arns) > 0
    error_message = "List at least one admin principal, or the bucket policy locks everyone else out."
  }
}

variable "create_oidc_provider" {
  description = "Set false if the account already has the GitHub OIDC provider."
  type        = bool
  default     = true
}

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

locals {
  account_id         = data.aws_caller_identity.current.account_id
  partition          = data.aws_partition.current.partition
  deploy_role_prefix = "edgeops-github-"
  state_bucket       = "edgeops-tfstate-${local.account_id}-${var.region}"
  state_key          = "${var.project}/terraform.tfstate"
  oidc_provider_arn  = "arn:${local.partition}:iam::${local.account_id}:oidc-provider/token.actions.githubusercontent.com"
  provider_arn       = var.create_oidc_provider ? aws_iam_openid_connect_provider.github[0].arn : local.oidc_provider_arn
  state_principals   = concat([for role in aws_iam_role.deploy : role.arn], var.state_admin_principal_arns)
  policy_vars = {
    partition          = local.partition
    region             = var.region
    account_id         = local.account_id
    project            = var.project
    state_bucket       = local.state_bucket
    state_key          = local.state_key
    deploy_role_prefix = local.deploy_role_prefix
    boundary_arn       = aws_iam_policy.workload_boundary.arn
  }
}

# Remote state ---------------------------------------------------------------
resource "aws_s3_bucket" "state" {
  bucket = local.state_bucket
  lifecycle { prevent_destroy = true }
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "state" {
  bucket = aws_s3_bucket.state.id
  rule { object_ownership = "BucketOwnerEnforced" }
}

resource "aws_s3_bucket_lifecycle_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    id     = "expire-old-state-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration { noncurrent_days = 90 }
    abort_incomplete_multipart_upload { days_after_initiation = 1 }
  }
}

resource "aws_s3_bucket_policy" "state" {
  bucket = aws_s3_bucket.state.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "TlsOnly"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource  = [aws_s3_bucket.state.arn, "${aws_s3_bucket.state.arn}/*"]
        Condition = { Bool = { "aws:SecureTransport" = "false" } }
      },
      {
        Sid       = "OnlyDeployRolesAndAdmins"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource  = [aws_s3_bucket.state.arn, "${aws_s3_bucket.state.arn}/*"]
        Condition = { ArnNotLike = { "aws:PrincipalArn" = local.state_principals } }
      }
    ]
  })
  depends_on = [aws_s3_bucket_public_access_block.state]
}

# GitHub OIDC and deploy roles -------------------------------------------------
resource "aws_iam_openid_connect_provider" "github" {
  count          = var.create_oidc_provider ? 1 : 0
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

# Ceiling for every role the stack creates: even a malicious plan that writes
# an admin policy onto a Lambda role gets at most these permissions.
resource "aws_iam_policy" "workload_boundary" {
  name        = "${var.project}-workload-boundary"
  description = "Permissions boundary required on every role the EdgeOps stack creates."
  policy = templatefile("${path.module}/policies/workload-boundary.json.tpl", {
    partition = local.partition, region = var.region, account_id = local.account_id, project = var.project
  })
}

locals {
  # Plan runs on pull requests (read-only plus the state lock file). Apply runs only
  # in the protected environment, so a PR token's `sub` can never match it.
  deploy_subjects = {
    plan  = ["repo:${var.github_repository}:pull_request"]
    apply = ["repo:${var.github_repository}:environment:${var.deploy_environment}"]
  }
}

resource "aws_iam_role" "deploy" {
  for_each             = local.deploy_subjects
  name                 = "${local.deploy_role_prefix}${each.key}"
  max_session_duration = 3600
  assume_role_policy = templatefile("${path.module}/policies/github-trust.json.tpl", {
    provider_arn = local.provider_arn, subjects = jsonencode(each.value)
  })
}

resource "aws_iam_role_policy" "deploy_read" {
  for_each = aws_iam_role.deploy
  name     = "terraform-read"
  role     = each.value.id
  policy   = templatefile("${path.module}/policies/deploy-read.json.tpl", local.policy_vars)
}

resource "aws_iam_role_policy" "deploy_apply" {
  name   = "terraform-apply"
  role   = aws_iam_role.deploy["apply"].id
  policy = templatefile("${path.module}/policies/deploy-apply.json.tpl", local.policy_vars)
}

output "state_bucket" { value = aws_s3_bucket.state.id }
output "state_key" { value = local.state_key }
output "plan_role_arn" { value = aws_iam_role.deploy["plan"].arn }
output "apply_role_arn" { value = aws_iam_role.deploy["apply"].arn }
output "permissions_boundary_arn" { value = aws_iam_policy.workload_boundary.arn }
