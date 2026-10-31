terraform {
  required_version = ">= 1.10, < 2.0"
  # Partial S3 backend with native locking (use_lockfile). Settings come from
  # backend.hcl at init time; see backend.hcl.example and infra/bootstrap.
  backend "s3" {}
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.7"
    }
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = { Project = var.project, Environment = "portfolio", ManagedBy = "terraform" }
  }
}

variable "region" {
  description = "AWS region for regional resources. Verify pricing before apply."
  type        = string
  default     = "ap-south-1"
}

variable "project" {
  type    = string
  default = "edgeops-demo"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,25}$", var.project))
    error_message = "Use 3-26 lowercase letters, digits, and hyphens, starting with a letter."
  }
}

variable "permissions_boundary_arn" {
  description = "Boundary attached to the Lambda roles; the deploy role can only create roles that carry it."
  type        = string
  default     = ""
}

variable "point_in_time_recovery" {
  description = "DynamoDB PITR for the fleet table. Billed per GB-month; the demo table is a few KB."
  type        = bool
  default     = true
}

variable "alarm_email" {
  description = "Optional verified recipient. SNS sends a subscription confirmation after deployment."
  type        = string
  default     = ""
}

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

locals {
  name         = var.project
  frontend_dir = "${path.module}/../frontend"
  cloud_origin = "https://${aws_cloudfront_distribution.frontend.domain_name}"
}
