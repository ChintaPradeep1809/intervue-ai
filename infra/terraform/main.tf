# Reference AWS layout (not applied by this repo). See docs/DEPLOYMENT.md.
# web  -> ECS Fargate service behind an ALB (or Vercel)
# api  -> ECS Fargate service, private subnets, ALB with WebSocket support (idle timeout >= 300s)
# worker -> dedicated EC2/ECS-on-EC2 capacity provider with gVisor runtime, no public ingress
# db   -> RDS PostgreSQL 16 (Multi-AZ in prod) + pgvector extension for RAG at scale
# storage -> S3 bucket (SSE-KMS, block public access), presigned URLs only
# secrets -> AWS Secrets Manager -> ECS task env

terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}

variable "region" { default = "ap-south-1" }
variable "project" { default = "intervueai" }

provider "aws" { region = var.region }

resource "aws_s3_bucket" "documents" {
  bucket_prefix = "${var.project}-documents-"
}

resource "aws_s3_bucket_public_access_block" "documents" {
  bucket                  = aws_s3_bucket.documents.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "aws:kms" }
  }
}

resource "aws_secretsmanager_secret" "app" {
  name_prefix = "${var.project}-app-"
  description = "AUTH_SECRET, AI_API_KEY, VOICE_API_KEY, WORKER_TOKEN, DATABASE_URL"
}
