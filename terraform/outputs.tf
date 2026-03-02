output "aws_account_id" {
  description = "AWS account ID used for deployment."
  value       = data.aws_caller_identity.current.account_id
}

output "alb_dns_name" {
  description = "Public DNS name for the backend ALB."
  value       = aws_lb.api.dns_name
}

output "ecs_cluster_name" {
  description = "ECS cluster name."
  value       = aws_ecs_cluster.main.name
}

output "ecs_service_name" {
  description = "ECS backend service name."
  value       = aws_ecs_service.backend.name
}

output "ecr_backend_repository_url" {
  description = "ECR repository URL for backend image pushes."
  value       = aws_ecr_repository.backend.repository_url
}

output "frontend_bucket_name" {
  description = "S3 bucket used for frontend artifacts."
  value       = aws_s3_bucket.frontend.bucket
}

output "private_subnet_ids" {
  description = "Private subnet IDs for ECS tasks."
  value       = aws_subnet.private[*].id
}

output "app_secret_arns" {
  description = "Secrets Manager ARNs injected into ECS task."
  value = {
    for key, secret in aws_secretsmanager_secret.app : key => secret.arn
  }
  sensitive = true
}
