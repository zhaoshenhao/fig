[中文](deployment_CN.md)

# KF AI Customer Service — Deployment Guide

---

## Choose Your Scenario

| Scenario | When to Use | Entry |
|----------|-------------|-------|
| **A. Local Dev** | Coding, debugging, quick test | [→ Local Setup Guide](local-setup_EN.md) |
| **B. Docker Compose** | Single server, demo, no K8s | [→ Scenario B](#b-docker-compose-deployment) |
| **C. K8s (Alibaba ACK)** | Production, uses ACK cluster | [→ Scenario C](#c-k8s-deployment-alibaba-ack) |
| **D. K8s (AWS EKS)** | Production, uses EKS cluster | [→ Scenario D](#d-k8s-deployment-aws-eks) |

---

## Prerequisites (All K8s Scenarios)

- [ ] **K8s cluster** created, `kubectl` connected
- [ ] **Ingress Controller** installed (ACK: ALB / EKS: AWS Load Balancer Controller)
- [ ] **Container registry** available (ACK: ACR / EKS: ECR)
- [ ] **MySQL 8.0+** instance created (metrics storage)
- [ ] **PostgreSQL 14+** instance created (analytics queries)
- [ ] **Redis** instance created (session sharing)
- [ ] **DeepSeek API Key** acquired
- [ ] **Object storage** (OSS or S3) buckets created (workflow configs + SPA)
- [ ] **Domain name** ready with configurable DNS

---

## B. Docker Compose Deployment

Single-server or demo environment. No K8s required.

### B.1 Prerequisites

```bash
docker --version          # >= 20.10
docker compose version
```

### B.2 Configure Environment

```bash
cp .env.example .env
vim .env
```

Minimum config (SQLite mode, no external DB):

```ini
DEEPSEEK_API_KEY=sk-your-deepseek-key
EMBED_API_KEY=               # optional
KF_API_KEY=                  # optional, leave empty for dev
```

For MySQL/PostgreSQL, see `../deployments/metrics-db-setup_EN.md`.

### B.3 Start All Services

```bash
docker compose up -d --build

# Check status
docker compose ps
docker compose logs -f api
```

### B.4 Verify

```bash
curl http://localhost:8000/health
# → {"status":"ok","timestamp":...,"startup_seconds":...}

curl http://localhost:8000/ready
curl http://localhost:8000/api/v1/workflows

curl -X POST http://localhost:8000/api/v1/workflows/default/run \
  -H "Content-Type: application/json" -d '{"query":"hello"}'
```

### B.5 Switch KF_MODE

Default docker-compose uses `full` mode (both chat + admin routes). To separate:

```yaml
# docker-compose.yaml → api service → environment:
KF_MODE: chat     # or admin
```

### B.6 Stop

```bash
docker compose down
```

---

## C. K8s Deployment (Alibaba ACK)

### System Architecture

```
                       Alibaba ALB Ingress
                    ┌──────────────────────────────┐
                    │  All /api/* paths     → kf-api
                    │  SPA static assets    → OSS + CDN
                    └──────────────────────────────┘
                                   │
           ┌─────────────────────────┼──────────────────────┐
           │                         │                      │
     ┌─────▼──────┐                                ┌───────▼──────┐
     │   kf-api    │                                │   kf-embed   │
     │ KF_MODE=full│                                │   :8100      │
     │   :8000     │                                └──────────────┘
     └──────┬──────┘
            │
            ├──► Qdrant gRPC :6334     — vector search
            ├──► Redis (external)       — session sharing
            ├──► MySQL RDS (external)    — metrics storage
            ├──► PG RDS (external)       — analytics
            └──► DeepSeek API (external)
```

### C.1 Set Deployment Variables

```bash
# ═══════════════ Replace with actual values ═══════════════
export NS="mb-test"
export ACR="registry.cn-hangzhou.aliyuncs.com/your-team"
export API_TAG="v1.0.0"
export EMBED_TAG="v1.0.0"
export DOMAIN="kf-test.example.com"
```

> All subsequent commands reference `${NS}`, `${ACR}`, etc. Verify values before proceeding.

### C.2 Build & Push Images

```bash
docker login --username=<Alibaba-account> ${ACR}

docker build -t ${ACR}/kf-api:${API_TAG} -f Dockerfile .
docker push ${ACR}/kf-api:${API_TAG}

docker build -t ${ACR}/kf-embed:${EMBED_TAG} -f Dockerfile.embed .
docker push ${ACR}/kf-embed:${EMBED_TAG}
```

> Qdrant uses the official image `qdrant/qdrant:latest` — no build needed.

### C.3 Create Namespace

```bash
kubectl create namespace ${NS}
```

### C.4 Create Secrets

> **Two separate steps.** `kf-secrets` is for app pods. `kf-db-root-secret` is for the one-time DB init Job (delete it afterwards).

#### C.4.1 App Secret (kf-secrets)

```bash
kubectl create secret generic kf-secrets \
  --namespace=${NS} \
  \
  --from-literal=DEEPSEEK_API_KEY="sk-..." \
  --from-literal=KF_API_KEY="your-api-key" \
  --from-literal=EMBED_API_KEY="embed-internal-key" \
  \
  --from-literal=REDIS_URL="redis://r-xxx.redis.rds.aliyuncs.com:6379/0" \
  \
  --from-literal=MYSQL_HOST="rm-xxx.mysql.rds.aliyuncs.com" \
  --from-literal=MYSQL_PORT="3306" \
  --from-literal=MYSQL_USER="kf" \
  --from-literal=MYSQL_PASSWORD="your-mysql-password" \
  --from-literal=MYSQL_DB="kf_metrics" \
  --from-literal=KF_METRICS_DB_HOST="rm-xxx.mysql.rds.aliyuncs.com" \
  --from-literal=KF_METRICS_DB_PORT="3306" \
  --from-literal=KF_METRICS_DB_USER="kf" \
  --from-literal=KF_METRICS_DB_PASSWORD="your-mysql-password" \
  --from-literal=KF_METRICS_DB_NAME="kf_metrics" \
  --from-literal=KF_METRICS_DB_TYPE="mysql" \
  \
  --from-literal=PG_HOST="pgm-xxx.pg.rds.aliyuncs.com" \
  --from-literal=PG_PORT="5432" \
  --from-literal=PG_USER="kf" \
  --from-literal=PG_PASSWORD="your-pg-password" \
  --from-literal=PG_DB="kf_analytics" \
  \
  --from-literal=OSS_ACCESS_KEY_ID="LTAI..." \
  --from-literal=OSS_ACCESS_KEY_SECRET="..." \
  --from-literal=OSS_ENDPOINT="oss-cn-hangzhou.aliyuncs.com" \
  --from-literal=OSS_INT_ENDPOINT="oss-cn-hangzhou-internal.aliyuncs.com" \
  --from-literal=OSS_WORKFLOW_BUCKET="kf-config-${NS}" \
  --from-literal=OSS_UI_BUCKET="kf-ui-${NS}"

# Verify
kubectl get secret kf-secrets -n ${NS}
```

#### C.4.2 DB Root Secret (one-time)

Apps never use root credentials. This secret is only for the DB init Job.

```bash
kubectl create secret generic kf-db-root-secret \
  --namespace=${NS} \
  --from-literal=DB_ROOT_USER="root" \
  --from-literal=DB_ROOT_PASSWORD="<MySQL-root-password>"
```

### C.5 Initialize Database

Run the one-time Job to create the MySQL database and app user:

```bash
kubectl apply -f deployment/k8s-aliyun/init-db-job.yaml

kubectl get job init-metrics-db -n ${NS} -w
kubectl logs job/init-metrics-db -n ${NS}
```

> **Confirm Job success before continuing.** Table schemas are auto-created on app startup — no manual DDL needed.

### C.6 Deploy Foundation Services (Qdrant + Embed)

```bash
# Qdrant StatefulSet
kubectl apply -f deployment/k8s-aliyun/qdrant/service.yaml
cat deployment/k8s-aliyun/qdrant/statefulset.yaml | sed "s|<NAMESPACE>|${NS}|g" | kubectl apply -f -

# kf-embed
cat deployment/k8s-aliyun/embed/service.yaml | sed "s|<NAMESPACE>|${NS}|g" | kubectl apply -f -
cat deployment/k8s-aliyun/embed/deployment.yaml \
  | sed "s|<NAMESPACE>|${NS}|g" \
  | sed "s|<ACR_REGISTRY>|${ACR}|g" \
  | sed "s|<EMBED_IMAGE_TAG>|${EMBED_TAG}|g" \
  | kubectl apply -f -

# Wait for readiness
kubectl wait --for=condition=ready pod -l app=qdrant -n ${NS} --timeout=120s
kubectl wait --for=condition=ready pod -l app=embed -n ${NS} --timeout=120s
```

### C.7 Deploy Application (kf-api)

```bash
# OSS CSI PVC (workflow configs)
cat deployment/k8s-aliyun/oss-pvc.yaml | sed "s|<NAMESPACE>|${NS}|g" | kubectl apply -f -

# kf-api (user traffic + admin, KF_MODE=full)
cat deployment/k8s-aliyun/kf-api/service.yaml | sed "s|<NAMESPACE>|${NS}|g" | kubectl apply -f -
cat deployment/k8s-aliyun/kf-api/deployment.yaml \
  | sed "s|<NAMESPACE>|${NS}|g" \
  | sed "s|<ACR_REGISTRY>|${ACR}|g" \
  | sed "s|<API_IMAGE_TAG>|${API_TAG}|g" \
  | kubectl apply -f -

kubectl wait --for=condition=ready pod -l app=kf-api -n ${NS} --timeout=120s
```

### C.8 Configure Ingress (ALB)

```bash
cat deployment/k8s-aliyun/ingress.yaml \
  | sed "s|<NAMESPACE>|${NS}|g" \
  | sed "s|<DOMAIN>|${DOMAIN}|g" \
  | kubectl apply -f -

kubectl get ingress -n ${NS} -w
```

### C.9 Verify

```bash
kubectl get pods -n ${NS}
# Expected: 3 pods, all Running, 1/1 Ready

INGRESS_ADDR=$(kubectl get ingress kf-ingress -n ${NS} \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

curl http://${INGRESS_ADDR}/health
curl http://${INGRESS_ADDR}/ready
curl http://${INGRESS_ADDR}/api/v1/workflows

curl -X POST http://${INGRESS_ADDR}/api/v1/workflows/default/run \
  -H "Content-Type: application/json" -d '{"query":"hello"}'
```

### C.10 Deploy SPA Frontend

```bash
cd src/gui/ui && npm ci && npm run build
ossutil cp -r dist/ oss://kf-ui-${NS}/ --update
```

### C.11 Cleanup Root Secret (Recommended)

```bash
kubectl delete secret kf-db-root-secret -n ${NS}
```

### C.12 ACK Resource Specs

| Component | requests | limits | Replicas | Storage |
|-----------|----------|--------|----------|---------|
| kf-api | 0.5 CPU / 512Mi | 2 CPU / 2Gi | 1 | — |
| kf-embed | 0.2 CPU / 256Mi | 0.5 CPU / 512Mi | 1 | — |
| Qdrant | 1 CPU / 2Gi | 2 CPU / 4Gi | 1 | ESSD 20Gi |

---

## D. K8s Deployment (AWS EKS)

Key differences from ACK:

| Component | ACK | EKS |
|-----------|-----|-----|
| Registry | ACR | ECR |
| Ingress | ALB Ingress Controller | AWS Load Balancer Controller |
| Vector DB | Qdrant + ESSD | Qdrant + gp3 EBS |
| Config mount | OSS CSI PVC | EFS CSI PVC |
| S3 access | OSS AccessKey (Secret) | IRSA (IAM role) |
| SPA storage | OSS bucket | S3 + CloudFront |

### D.1 Set Deployment Variables

```bash
export NS="kf-prod"
export AWS_ACCOUNT="123456789012"
export AWS_REGION="us-east-1"
export API_TAG="v1.0.0"
export EMBED_TAG="v1.0.0"
export DOMAIN="kf.example.com"
export ECR="${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com"
```

### D.2 Build & Push to ECR

```bash
aws ecr get-login-password --region ${AWS_REGION} \
  | docker login --username AWS --password-stdin ${ECR}

aws ecr describe-repositories --repository-names kf-api --region ${AWS_REGION} 2>/dev/null \
  || aws ecr create-repository --repository-name kf-api --region ${AWS_REGION}
aws ecr describe-repositories --repository-names kf-embed --region ${AWS_REGION} 2>/dev/null \
  || aws ecr create-repository --repository-name kf-embed --region ${AWS_REGION}

docker build -t kf-api:${API_TAG} -f Dockerfile .
docker tag kf-api:${API_TAG} ${ECR}/kf-api:${API_TAG}
docker push ${ECR}/kf-api:${API_TAG}

docker build -t kf-embed:${EMBED_TAG} -f Dockerfile.embed .
docker tag kf-embed:${EMBED_TAG} ${ECR}/kf-embed:${EMBED_TAG}
docker push ${ECR}/kf-embed:${EMBED_TAG}
```

### D.3 Create Namespace

```bash
kubectl create namespace ${NS}
```

### D.4 Create Secrets

```bash
kubectl create secret generic kf-secrets \
  --namespace=${NS} \
  \
  --from-literal=DEEPSEEK_API_KEY="sk-..." \
  --from-literal=KF_API_KEY="your-api-key" \
  --from-literal=EMBED_API_KEY="embed-internal-key" \
  \
  --from-literal=REDIS_URL="rediss://<elasticache-endpoint>:6379/0" \
  \
  --from-literal=MYSQL_HOST="<RDS MySQL endpoint>" \
  --from-literal=MYSQL_PORT="3306" \
  --from-literal=MYSQL_USER="kf" \
  --from-literal=MYSQL_PASSWORD="<mysql-password>" \
  --from-literal=MYSQL_DB="kf_metrics" \
  --from-literal=KF_METRICS_DB_HOST="<RDS MySQL endpoint>" \
  --from-literal=KF_METRICS_DB_PORT="3306" \
  --from-literal=KF_METRICS_DB_USER="kf" \
  --from-literal=KF_METRICS_DB_PASSWORD="<mysql-password>" \
  --from-literal=KF_METRICS_DB_NAME="kf_metrics" \
  --from-literal=KF_METRICS_DB_TYPE="mysql" \
  \
  --from-literal=PG_HOST="<RDS PostgreSQL endpoint>" \
  --from-literal=PG_PORT="5432" \
  --from-literal=PG_USER="kf" \
  --from-literal=PG_PASSWORD="<pg-password>" \
  --from-literal=PG_DB="kf_analytics" \
  \
  --from-literal=AWS_REGION="${AWS_REGION}" \
  --from-literal=S3_CONFIG_BUCKET="kf-config-${NS}" \
  --from-literal=S3_UI_BUCKET="kf-ui-${NS}"
```

### D.5 Create DB Root Secret

```bash
kubectl create secret generic kf-db-root-secret \
  --namespace=${NS} \
  --from-literal=DB_ROOT_USER="root" \
  --from-literal=DB_ROOT_PASSWORD="<RDS-root-password>"
```

### D.6 Initialize Database

```bash
# Update DB_HOST in init-db-job.yaml for your MySQL/PG endpoints, then:
kubectl apply -f deployment/k8s-aliyun/init-db-job.yaml
kubectl get job init-metrics-db -n ${NS} -w
```

### D.7 Create AWS Storage Resources

```bash
# gp3 StorageClass for Qdrant
cat <<EOF | kubectl apply -f -
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: qdrant-storage
provisioner: ebs.csi.aws.com
parameters:
  type: gp3
  fsType: ext4
reclaimPolicy: Retain
volumeBindingMode: WaitForFirstConsumer
EOF

# EFS PVC for workflow configs (requires pre-created EFS + EFS CSI Driver)
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: workflow-config
  namespace: ${NS}
spec:
  accessModes: ["ReadWriteMany"]
  storageClassName: efs-sc
  resources:
    requests:
      storage: 1Gi
EOF
```

### D.8 Configure IRSA

```bash
# Create IAM policy for S3 access
POLICY_ARN=$(aws iam create-policy \
  --policy-name kf-s3-access-${NS} \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::kf-config-*",
        "arn:aws:s3:::kf-config-*/*",
        "arn:aws:s3:::kf-ui-*",
        "arn:aws:s3:::kf-ui-*/*"
      ]
    }]
  }' \
  --query 'Policy.Arn' --output text)

# Create ServiceAccount with IAM role
eksctl create iamserviceaccount \
  --name kf-s3-access \
  --namespace ${NS} \
  --cluster <EKS_CLUSTER_NAME> \
  --attach-policy-arn ${POLICY_ARN} \
  --approve
```

### D.9 Deploy Services

Modify ACK manifests to use ECR images, `serviceAccountName: kf-s3-access`, and EFS PVC. Then deploy as in C.6-C.8, adjusting image references from `${ACR}` to `${ECR}` and storage from `alicloud-disk-essd` to `qdrant-storage`.

### D.10 Verify

```bash
ALB_DNS=$(kubectl get ingress kf-ingress -n ${NS} \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')

curl http://${ALB_DNS}/health
curl http://${ALB_DNS}/ready
curl http://${ALB_DNS}/api/v1/workflows
```

### D.11 Deploy SPA

```bash
cd src/gui/ui && npm ci && npm run build
aws s3 cp dist/ s3://kf-ui-${NS}/ --recursive
aws cloudfront create-invalidation --distribution-id <DIST_ID> --paths "/*"
```

### D.12 EKS Resource Specs

| Component | requests | limits | Replicas | Storage |
|-----------|----------|--------|----------|---------|
| kf-api | 0.5 CPU / 512Mi | 2 CPU / 2Gi | 1 | — |
| kf-embed | 0.2 CPU / 256Mi | 0.5 CPU / 512Mi | 1 | — |
| Qdrant | 1 CPU / 2Gi | 2 CPU / 4Gi | 1 | gp3 EBS 20Gi |

---

## Appendix A: Database Initialization

| Resource | Purpose |
|----------|---------|
| `../deployments/metrics-db-setup_EN.md` | Create DB, user, env vars, SQLite → MySQL/PG migration |
| `db-schema-norm_EN.md` | Schema change norm, how to add migrations |
| `deployment/k8s-aliyun/init-db-job.yaml` | K8s one-time Job (root creds → create DB + app user) |
| `deployment/scripts/init-metrics-db.sh` | Local/single-server one-command init script |

**Key point**: Table schemas (DDL) are auto-created on app startup via `migrate()`. No manual SQL needed.

---

## Appendix B: SPA Deployment

| Step | ACK | EKS |
|------|-----|-----|
| Build | `cd src/gui/ui && npm ci && npm run build` | Same |
| Upload | `ossutil cp -r dist/ oss://kf-ui-${NS}/ --update` | `aws s3 cp dist/ s3://kf-ui-${NS}/ --recursive` |
| CDN | Alibaba CDN | CloudFront |
| Cache bust | `aliyun cdn RefreshObjectCaches` | `aws cloudfront create-invalidation` |

---

## Appendix C: Credential Injection Flow

```
kubectl create secret kf-secrets
    │
    ▼
Secret "kf-secrets" (Opaque, 22 keys)
    │
    ├── envFrom.secretRef → kf-api Pod
    │    Injects all keys as environment variables
    │
    └── valueFrom.secretKeyRef → kf-embed Pod
         Injects only EMBED_API_KEY

Pod environment variables
    │
    ├── _resolve_env() resolves ${VAR:-default} placeholders in YAML configs
    └── os.environ.get() for direct reads (factory.py, app.py)
```

---

## Appendix D: Troubleshooting

| Issue | Check |
|-------|-------|
| Pod `CrashLoopBackOff` | `kubectl logs <pod> -n ${NS}` |
| `/ready` returns `degraded` | Qdrant/Embed connectivity — verify Service DNS |
| Ingress returns 404 | DNS not pointing to ALB, or path mismatch |
| LLM errors in workflows | `DEEPSEEK_API_KEY` valid? Check `kubectl get secret` |
| Missing tables | `init-db-job` completed successfully? Check `migration.py` logs |

---

## Appendix E: K8s Manifest Index

| File | Description | Resource |
|------|-------------|----------|
| `deployment/k8s-aliyun/namespace.yaml` | Namespace | Namespace |
| `deployment/k8s-aliyun/secret.yaml` | Template (not runnable) | Secret |
| `deployment/k8s-aliyun/init-db-job.yaml` | DB init | Job |
| `deployment/k8s-aliyun/kf-api/deployment.yaml` | kf-api | Deployment |
| `deployment/k8s-aliyun/kf-api/service.yaml` | kf-api | Service |
| `deployment/k8s-aliyun/embed/deployment.yaml` | embed microservice | Deployment |
| `deployment/k8s-aliyun/embed/service.yaml` | embed | Service |
| `deployment/k8s-aliyun/qdrant/statefulset.yaml` | Qdrant vector DB | StatefulSet |
| `deployment/k8s-aliyun/qdrant/service.yaml` | Qdrant | Service |
| `deployment/k8s-aliyun/oss-pvc.yaml` | OSS CSI PVC (ACK) | PVC |
| `deployment/k8s-aliyun/ingress.yaml` | ALB Ingress (ACK) | Ingress |
| `deployment/k8s-aliyun/prometheus-rules.yaml` | Prometheus alert rules | PrometheusRule |
| `deployment/k8s-aliyun/grafana-dashboard.json` | Grafana dashboard | ConfigMap |
| `deployment/k8s-aliyun/job-build.yaml` | Doc builder Job | Job |
