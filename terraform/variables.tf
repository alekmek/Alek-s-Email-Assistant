variable "project_name" {
  description = "Project identifier used in resource names."
  type        = string
  default     = "voice-email-assistant"
}

variable "environment" {
  description = "Environment name (dev/staging/prod)."
  type        = string
  default     = "dev"
}

variable "aws_region" {
  description = "AWS region for deployment."
  type        = string
  default     = "us-west-2"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.42.0.0/16"
}

variable "az_count" {
  description = "Number of availability zones to use (minimum 2 recommended)."
  type        = number
  default     = 2
}

variable "frontend_bucket_name" {
  description = "Optional explicit S3 bucket name for frontend artifacts."
  type        = string
  default     = ""
}

variable "backend_image_uri" {
  description = "Backend container image URI (ECR URI with tag). If empty, uses ECR repo + latest tag."
  type        = string
  default     = ""
}

variable "api_container_port" {
  description = "Container port exposed by the backend API."
  type        = number
  default     = 8000
}

variable "api_desired_count" {
  description = "Desired task count for backend ECS service."
  type        = number
  default     = 1
}

variable "ecs_task_cpu" {
  description = "Fargate task CPU units."
  type        = number
  default     = 1024
}

variable "ecs_task_memory" {
  description = "Fargate task memory in MiB."
  type        = number
  default     = 2048
}

variable "frontend_url" {
  description = "Frontend origin allowed by backend CORS."
  type        = string
  default     = "http://localhost:5173"
}

variable "health_check_path" {
  description = "Backend health check path used by ALB target group."
  type        = string
  default     = "/health"
}

variable "enable_execute_command" {
  description = "Enable ECS execute-command for debugging."
  type        = bool
  default     = true
}

variable "log_retention_days" {
  description = "Retention period for CloudWatch logs."
  type        = number
  default     = 14
}

variable "anthropic_api_key" {
  description = "Anthropic API key for the backend service."
  type        = string
  default     = ""
  sensitive   = true
}

variable "nylas_api_key" {
  description = "Nylas API key for the backend service."
  type        = string
  default     = ""
  sensitive   = true
}

variable "nylas_client_id" {
  description = "Nylas client ID."
  type        = string
  default     = ""
  sensitive   = true
}

variable "nylas_client_secret" {
  description = "Nylas client secret."
  type        = string
  default     = ""
  sensitive   = true
}

variable "nylas_grant_id" {
  description = "Nylas grant ID."
  type        = string
  default     = ""
  sensitive   = true
}

variable "deepgram_api_key" {
  description = "Deepgram API key."
  type        = string
  default     = ""
  sensitive   = true
}

variable "cartesia_api_key" {
  description = "Cartesia API key."
  type        = string
  default     = ""
  sensitive   = true
}
