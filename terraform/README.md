# Terraform Deployment (AWS)

This folder now contains a full phase-2 deployment stack for the Voice Email Assistant.

## What is provisioned

- Networking:
  - VPC
  - 2 public subnets
  - 2 private subnets
  - Internet Gateway
  - NAT Gateway + private route table
- Backend runtime:
  - ECR repository
  - ECS cluster
  - ECS Fargate task definition + service
  - Application Load Balancer + target group + HTTP listener
  - Security groups for ALB and ECS tasks
- Secrets and IAM:
  - Secrets Manager secrets for app credentials
  - ECS execution role with permission to read those secrets
  - ECS task role
- Platform:
  - CloudWatch Log Group
  - S3 bucket for frontend artifacts

## Credential handling

Terraform creates one Secrets Manager secret per app credential and injects them into the ECS container as environment variables:

- `ANTHROPIC_API_KEY`
- `NYLAS_API_KEY`
- `NYLAS_CLIENT_ID`
- `NYLAS_CLIENT_SECRET`
- `NYLAS_GRANT_ID`
- `NYLAS_SID` (optional alias)
- `DEEPGRAM_API_KEY`
- `CARTESIA_API_KEY`

## Deploy

1. Create variables file:

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

2. Fill `terraform.tfvars` with:
- AWS settings (`aws_region`, sizing, etc.)
- backend image URI (or leave blank and use ECR `:latest`)
- all credential values

3. Apply:

```bash
terraform init
terraform fmt
terraform validate
terraform plan -var-file=terraform.tfvars
terraform apply -var-file=terraform.tfvars
```

4. Use output `alb_dns_name` as backend API base for frontend configuration.
