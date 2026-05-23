# Deployment Runbook

## Prerequisites
- AWS CLI configured (`aws configure`)
- Docker running
- Terraform installed

## AWS Region
All resources are in `us-east-1`.

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
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com

docker build -f backend/Dockerfile -t lab-data-integrations-backend .
docker tag lab-data-integrations-backend:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/lab-data-integrations-backend:latest
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/lab-data-integrations-backend:latest
```

### 3. Create App Runner service
```bash
cd terraform
terraform apply
```

---

## Subsequent Deploys (code changes only)

Build and push a new image from the project root:
```bash
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com

docker build -f backend/Dockerfile -t lab-data-integrations-backend .
docker tag lab-data-integrations-backend:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/lab-data-integrations-backend:latest
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/lab-data-integrations-backend:latest
```

Auto-deploy is enabled on the App Runner service. When a new image is pushed to ECR with the `latest` tag, App Runner detects it and automatically pulls the new image and restarts the service — no manual trigger needed. Note: if a broken image is pushed, it will auto-deploy that too, so push carefully.

---

## Infrastructure changes only
```bash
cd terraform
terraform apply
```

---

## Verify
```bash
curl https://<service-url>/health
```
Expected response: `{"status": "ok"}`
