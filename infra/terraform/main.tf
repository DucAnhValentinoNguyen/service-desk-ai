terraform {
  required_version = ">= 1.6.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  type    = string
  default = "eu-north-1"
}

variable "project_name" {
  type    = string
  default = "service-desk-ai"
}

resource "aws_s3_bucket" "artifacts" {
  bucket = "${var.project_name}-${data.aws_caller_identity.current.account_id}"
}

resource "aws_sqs_queue" "jobs" {
  name                      = "${var.project_name}-jobs"
  visibility_timeout_seconds = 120
  redrive_policy = jsonencode({ deadLetterTargetArn = aws_sqs_queue.dlq.arn, maxReceiveCount = 3 })
}

resource "aws_sqs_queue" "dlq" {
  name = "${var.project_name}-jobs-dlq"
}

data "aws_caller_identity" "current" {}
