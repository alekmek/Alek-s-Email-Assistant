# Terraform Plan

This document explains how to stand up this project in your own cloud account using the Terraform configuration in `terraform/`.

## Goal

Deploy a production-style baseline with:

- VPC networking (public + private subnets)
- ALB for backend ingress
- ECS Fargate backend service
- Secrets Manager for API credentials
- ECR for backend image
- S3 bucket for frontend artifacts
- CloudWatch logs

## Prerequisites

- AWS account with permissions for VPC, ECS, ECR, ALB, IAM, S3, Secrets Manager, CloudWatch.
- Terraform CLI (`>= 1.6`).
- AWS CLI configured (`aws configure`) for target account/region.
- Docker for building/pushing backend image.

## Files Used

- `terraform/versions.tf`
- `terraform/providers.tf`
- `terraform/variables.tf`
- `terraform/main.tf`
- `terraform/outputs.tf`
- `terraform/terraform.tfvars.example`

## Setup Steps

1. Copy variables template:

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

2. Edit `terraform.tfvars` with your values:
- Environment identifiers (`project_name`, `environment`)
- Region/network sizing
- Backend image URI (or use generated ECR repo + `latest`)
- Provider keys/secrets
- Nylas identifier using `nylas_grant_id` (or `nylas_sid` alias)
- Frontend URL used by backend CORS

3. Initialize and validate:

```bash
terraform init
terraform fmt
terraform validate
```

4. Review and apply:

```bash
terraform plan -var-file=terraform.tfvars
terraform apply -var-file=terraform.tfvars
```

5. Capture outputs:
- `alb_dns_name` for backend base URL
- `ecr_backend_repository_url` for image pushes
- `frontend_bucket_name` for frontend artifact uploads

## Recommended Deployment Order

1. Build backend container image.
2. Push image to ECR.
3. Run `terraform apply`.
4. Confirm ECS service is healthy behind ALB.
5. Build frontend (`npm run build` in `frontend/`).
6. Upload `frontend/dist` to S3 bucket output by Terraform.
7. Point frontend API/WebSocket base URL to ALB DNS.

## Post-Deploy Verification Checklist

- `GET /health` returns healthy.
- WebSocket connection to `/ws/audio` succeeds.
- Assistant can complete search/count/breakdown requests.
- Logs are visible in CloudWatch Log Group.
- Credentials are present in Secrets Manager and mapped to ECS task.
