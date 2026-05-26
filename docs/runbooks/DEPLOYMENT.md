# Deployment Runbook

## Prerequisites
- AWS CLI configured (`aws configure`)
- Docker running
- Terraform installed

## AWS Region
All resources are in `us-east-2`.

---

## First Deploy

### 1. Create ECR repository
```bash
cd terraform
terraform init
terraform apply -target=aws_ecr_repository.backend
```

### 2. Build and push image
From the project root:
```bash
aws ecr get-login-password --region us-east-2 | docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-2.amazonaws.com

docker build --platform linux/amd64 -f backend/Dockerfile -t lab-data-integrations-backend .
docker tag lab-data-integrations-backend:latest <account-id>.dkr.ecr.us-east-2.amazonaws.com/lab-data-integrations-backend:latest
docker push <account-id>.dkr.ecr.us-east-2.amazonaws.com/lab-data-integrations-backend:latest
```

### 3. Create ECS infrastructure
```bash
cd terraform
terraform apply
```

---

## Subsequent Deploys (code changes only)

Build and push a new image from the project root:
```bash
aws ecr get-login-password --region us-east-2 | docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-2.amazonaws.com

docker build --platform linux/amd64 -f backend/Dockerfile -t lab-data-integrations-backend .
docker tag lab-data-integrations-backend:latest <account-id>.dkr.ecr.us-east-2.amazonaws.com/lab-data-integrations-backend:latest
docker push <account-id>.dkr.ecr.us-east-2.amazonaws.com/lab-data-integrations-backend:latest
```

Then force a new ECS deployment to pick up the new image:
```bash
aws ecs update-service --cluster lab-data-integrations-backend --service lab-data-integrations-backend --force-new-deployment --region us-east-2
```

---

## Infrastructure changes only
```bash
cd terraform
terraform apply
```

---

## Verify
```bash
curl http://<alb-url>/health
```
Get the ALB URL from Terraform output:
```bash
terraform output backend_url
```
Expected response: `{"status": "ok"}`
