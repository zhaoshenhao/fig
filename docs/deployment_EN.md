# KF Deployment Guide

[中文](deployment_CN.md)

---

## Overview

The system deploys as 3 container images on Kubernetes:

| Image | Runtime | K8s Object | Description |
|-------|---------|------------|-------------|
| **kf-api** | FastAPI (uvicorn) | 2 Deployments | chat-api + admin-api, same image, routed by `KF_MODE` env var |
| **kf-embed** | FastEmbed (ONNX) | 1 Deployment | Model baked into image, no runtime download |
| **Qdrant** | Official qdrant/qdrant | StatefulSet 1 replica | Vector database, persisted via cloud disk |

External managed services: DeepSeek API (LLM), Redis (session sharing), MySQL RDS (metrics/primary), PostgreSQL RDS (analytics), OSS/S3 (config + SPA hosting)

### Architecture Diagram

```
ALB / AWS ALB Ingress
  ├── /api/v1/workflows/*/run → chat-api (Deployment, KF_MODE=chat)
  ├── /metrics/*              → admin-api (Deployment, KF_MODE=admin)
  ├── SPA static assets       → OSS/S3 + CDN
  │
  Internal services:
  ├── chat-api  → Qdrant (StatefulSet, gRPC:6334)
  ├── chat-api  → kf-embed (Deployment, HTTP:8100)
  ├── chat-api  → Redis      (external, session)
  ├── chat-api  → MySQL RDS  (external, metrics)
  ├── admin-api → MySQL RDS  (external, metrics)
  └── chat-api  → DeepSeek API (external)
```

### Service Inventory

| Service | K8s Object | Image | Replicas | Port |
|---------|-----------|-------|----------|------|
| chat-api | Deployment | kf-api | 1 | 8000 |
| admin-api | Deployment | kf-api | 1 | 8000 |
| kf-embed | Deployment | kf-embed | 1 | 8100 |
| Qdrant | StatefulSet | qdrant/qdrant | 1 | 6334(gRPC) / 6333(HTTP) |

---

## Prerequisites (Both Platforms)

- Existing Kubernetes cluster (ACK or EKS)
- kubectl configured to connect to the cluster
- Ingress Controller installed (ACK: ALB Ingress Controller / EKS: AWS Load Balancer Controller)
- Container registry ready (ACK: ACR / EKS: ECR)
- External managed services ready: RDS MySQL, RDS PostgreSQL, Redis, DeepSeek API key

---

## A. Alibaba Cloud ACK Deployment

### A.1 Build & Push Images

```bash
# kf-api (FastAPI)
docker build -t <ACR_REGISTRY>/kf-api:<TAG> -f Dockerfile .
docker push <ACR_REGISTRY>/kf-api:<TAG>

# kf-embed (FastEmbed)
docker build -t <ACR_REGISTRY>/kf-embed:<TAG> -f Dockerfile.embed .
docker push <ACR_REGISTRY>/kf-embed:<TAG>
```

### A.2 Create Namespace

```bash
kubectl apply -f k8s/namespace.yaml
```

> `k8s/namespace.yaml` defines namespace `<NAMESPACE>`. Replace `<NAMESPACE>` with the actual value (e.g., `mb-test`, `mb-pr`) before applying, or use sed substitution.

### A.3 Create Secret

> `k8s/secret.yaml` is a structural template and **does not contain real credentials**. Use the following command to inject actual values at deploy time.

```bash
kubectl create secret generic kf-secrets \
  --namespace=<NAMESPACE> \
  \
  --from-literal=DEEPSEEK_API_KEY="<DeepSeek API Key>" \
  --from-literal=KF_API_KEY="<API gateway auth key>" \
  --from-literal=EMBED_API_KEY="<internal embed auth key>" \
  \
  --from-literal=REDIS_URL="redis://<Redis internal endpoint>:6379/0" \
  \
  --from-literal=MYSQL_HOST="<MySQL internal endpoint>" \
  --from-literal=MYSQL_PORT="3306" \
  --from-literal=MYSQL_USER="<MySQL username>" \
  --from-literal=MYSQL_PASSWORD="<MySQL password>" \
  --from-literal=MYSQL_DB="kf_metrics" \
  --from-literal=KF_METRICS_DB_HOST="<same as MYSQL_HOST>" \
  --from-literal=KF_METRICS_DB_PORT="3306" \
  --from-literal=KF_METRICS_DB_USER="<same as MYSQL_USER>" \
  --from-literal=KF_METRICS_DB_PASSWORD="<same as MYSQL_PASSWORD>" \
  --from-literal=KF_METRICS_DB_NAME="kf_metrics" \
  --from-literal=KF_METRICS_DB_TYPE="mysql" \
  \
  --from-literal=PG_HOST="<PostgreSQL internal endpoint>" \
  --from-literal=PG_PORT="5432" \
  --from-literal=PG_USER="<PostgreSQL username>" \
  --from-literal=PG_PASSWORD="<PostgreSQL password>" \
  --from-literal=PG_DB="kf_analytics" \
  \
  --from-literal=OSS_ACCESS_KEY_ID="<OSS AccessKey ID>" \
  --from-literal=OSS_ACCESS_KEY_SECRET="<OSS AccessKey Secret>" \
  --from-literal=OSS_ENDPOINT="oss-cn-hangzhou.aliyuncs.com" \
  --from-literal=OSS_WORKFLOW_BUCKET="kf-config-<ENV>" \
  --from-literal=OSS_UI_BUCKET="kf-ui-<ENV>"
```

> **Note**: OSS credentials are used only by CI/CD pipelines to upload UI static files to OSS. The running application does not consume them.

**Verify Secret**:

```bash
kubectl get secret kf-secrets -n <NAMESPACE> -o jsonpath='{.data}' | python3 -c "
import json, sys
for k, v in sorted(json.load(sys.stdin).items()):
    print(f'  {k:30s} = {v[:4]}***')
"
```

### A.4 Deploy K8s Resources

Set the following placeholder values:

| Placeholder | Description | Example |
|---|---|---|
| `<NAMESPACE>` | K8s namespace | `mb-test` |
| `<ACR_REGISTRY>` | ACR image registry URL | `registry.cn-hangzhou.aliyuncs.com/your-team` |
| `<API_IMAGE_TAG>` | kf-api image tag | `v1.0.0` |
| `<EMBED_IMAGE_TAG>` | kf-embed image tag | `v1.0.0` |
| `<DOMAIN>` | ALB Ingress domain | `kf-test.example.com` |

**One-shot Deployment**:

```bash
export NS=<NAMESPACE>
export ACR=<ACR_REGISTRY>
export API_TAG=<API_IMAGE_TAG>
export EMBED_TAG=<EMBED_IMAGE_TAG>
export DOMAIN=<DOMAIN>

# chat-api
cat k8s/chat-api/deployment.yaml | sed "s|<NAMESPACE>|$NS|g; s|<ACR_REGISTRY>|$ACR|g; s|<API_IMAGE_TAG>|$API_TAG|g" | kubectl apply -f -
cat k8s/chat-api/service.yaml | sed "s|<NAMESPACE>|$NS|g" | kubectl apply -f -

# admin-api
cat k8s/admin-api/deployment.yaml | sed "s|<NAMESPACE>|$NS|g; s|<ACR_REGISTRY>|$ACR|g; s|<API_IMAGE_TAG>|$API_TAG|g" | kubectl apply -f -
cat k8s/admin-api/service.yaml | sed "s|<NAMESPACE>|$NS|g" | kubectl apply -f -

# kf-embed
cat k8s/embed/deployment.yaml | sed "s|<NAMESPACE>|$NS|g; s|<ACR_REGISTRY>|$ACR|g; s|<EMBED_IMAGE_TAG>|$EMBED_TAG|g" | kubectl apply -f -
cat k8s/embed/service.yaml | sed "s|<NAMESPACE>|$NS|g" | kubectl apply -f -

# Qdrant (StatefulSet + Service)
cat k8s/qdrant/statefulset.yaml | sed "s|<NAMESPACE>|$NS|g" | kubectl apply -f -
cat k8s/qdrant/service.yaml | sed "s|<NAMESPACE>|$NS|g" | kubectl apply -f -

# OSS CSI PVC (workflow config mount)
cat k8s/oss-pvc.yaml | sed "s|<NAMESPACE>|$NS|g" | kubectl apply -f -

# Ingress (ALB, dual backend routing)
cat k8s/ingress.yaml | sed "s|<NAMESPACE>|$NS|g; s|<DOMAIN>|$DOMAIN|g" | kubectl apply -f -
```

**Step-by-step Deployment**:

```bash
# 1. chat-api (user-facing traffic)
kubectl apply -f k8s/chat-api/

# 2. admin-api (internal management)
kubectl apply -f k8s/admin-api/

# 3. kf-embed (FastEmbed vectorization microservice, model baked in, loads in seconds)
kubectl apply -f k8s/embed/

# 4. Qdrant (1 replica StatefulSet + ESSD)
kubectl apply -f k8s/qdrant/

# 5. OSS CSI PVC (workflow YAML config mount)
kubectl apply -f k8s/oss-pvc.yaml

# 6. Ingress (ALB dual backend routing)
kubectl apply -f k8s/ingress.yaml
```

### A.5 Verify Deployment

```bash
# Check Pod status
kubectl get pods -n <NAMESPACE>

# Check Services
kubectl get svc -n <NAMESPACE>

# Check Ingress (ALB)
kubectl get ingress -n <NAMESPACE>

# Health checks
curl http://<DOMAIN>/health   # chat-api health
curl http://<DOMAIN>/status   # admin-api status

# Wait for all Pods to be ready
kubectl wait --for=condition=ready pod -l app=chat-api -n <NAMESPACE> --timeout=120s
kubectl wait --for=condition=ready pod -l app=admin-api -n <NAMESPACE> --timeout=120s
kubectl wait --for=condition=ready pod -l app=embed -n <NAMESPACE> --timeout=120s
kubectl wait --for=condition=ready pod -l app=qdrant -n <NAMESPACE> --timeout=120s
```

### A.6 Secret Injection Architecture

```
kubectl create secret kf-secrets   ← manual / Jenkins withCredentials
    │
    ▼
┌───────────────────────────────────┐
│  K8s Secret (kf-secrets)          │
│  type: Opaque                     │
│  stringData: {                    │
│    DEEPSEEK_API_KEY, KF_API_KEY,  │
│    EMBED_API_KEY, REDIS_URL,      │
│    MYSQL_*, PG_*, OSS_* ...       │
│  }                                │
└────────┬──────────────────────────┘
         │
    ┌────┴──── Two injection modes ─────┐
    │                                    │
    ▼                                    ▼
envFrom.secretRef                  valueFrom.secretKeyRef
(chat-api / admin-api)             (kf-embed)
→ injects all 20+ keys            → injects only EMBED_API_KEY
    │                                    │
    ▼                                    ▼
  Pod environment vars ←── os.environ
    │
    ├── _resolve_env()
    │    Resolves ${VAR:-default} placeholders in YAML files against env vars
    │    → LLMConfig, DBConfig, SessionConfig, EmbedConfig...
    │
    └── os.environ.get("VAR")  direct access
         → factory.py, embed_service/app.py, logger
```

#### Credential Consumption Chain

| Secret Key | Injection Method | Consumed By |
|---|---|---|
| `DEEPSEEK_API_KEY` | envFrom → `_resolve_env()` | `config/llm.yaml` (LLM calls), `config/session.yaml` (session summarization) |
| `KF_API_KEY` | envFrom → `_resolve_env()` | `config/auth.yaml` (API authentication) |
| `EMBED_API_KEY` | envFrom + valueFrom | `config/embed.yaml` (chat/admin calling embed), `src/embed_service/app.py:40` (embed self-auth) |
| `REDIS_URL` | envFrom → `_resolve_env()` | `config/session.yaml` → `src/session/redis_store.py` |
| `MYSQL_HOST/PORT/USER/PASSWORD/DB` | envFrom → `_resolve_env()` | `config/db.yaml` → DB connection pool |
| `KF_METRICS_DB_*` | envFrom → `_resolve_env()` / `os.environ.get()` | `config/db.yaml`, `config/metrics.yaml`, `src/metrics/factory.py` |
| `PG_HOST/PORT/USER/PASSWORD/DB` | envFrom → `_resolve_env()` | `config/db.yaml` → PostgreSQL connection pool |
| `OSS_ACCESS_KEY_ID/SECRET/ENDPOINT` | envFrom (Jenkins injection) | CI/CD pipeline for ossutil UI static file uploads, **not consumed at runtime** |
| `OSS_WORKFLOW_BUCKET/UI_BUCKET` | envFrom (Jenkins injection) | Same as above |

#### Config File Placeholder Resolution

`src/config.py:_resolve_env()` uses regex to resolve `${VAR}` / `${VAR:-default}` placeholders in YAML files:

```
config/llm.yaml:     api_key: ${DEEPSEEK_API_KEY}            → os.environ["DEEPSEEK_API_KEY"]
config/db.yaml:      host: ${MYSQL_HOST:-127.0.0.1}          → os.environ["MYSQL_HOST"]
config/session.yaml: url: ${REDIS_URL:-redis://localhost}     → os.environ["REDIS_URL"]
config/embed.yaml:   api_key: ${EMBED_API_KEY:-}              → os.environ["EMBED_API_KEY"]
config/metrics.yaml: engine: ${KF_METRICS_ENGINE:-sqlite}    → "mysql"
```

### A.7 Resource Requirements (ACK)

| Component | requests | limits | Notes |
|---|---|---|---|
| chat-api | 0.5 CPU / 512Mi | 2 CPU / 2Gi | 1 replica |
| admin-api | 0.5 CPU / 512Mi | 2 CPU / 2Gi | 1 replica |
| kf-embed | 0.2 CPU / 256Mi | 0.5 CPU / 512Mi | Model baked in, no PVC needed |
| Qdrant | 1 CPU / 2Gi | 2 CPU / 4Gi | 1 replica + ESSD |

---

## B. AWS EKS Deployment

### B.1 Additional Prerequisites

- EKS cluster created, kubectl configured
- AWS Load Balancer Controller installed
- ECR repositories created: `kf-api`, `kf-embed`
- EFS CSI Driver or S3 CSI Driver installed (for workflow config persistent volume)
- External managed services ready: RDS MySQL, RDS PostgreSQL, ElastiCache Redis, S3 buckets (`kf-config-prod` / `kf-ui-prod`)
- IAM roles prepared for IRSA (S3 access)

### B.2 Build & Push to ECR

```bash
# Login to ECR
aws ecr get-login-password --region <REGION> | docker login --username AWS --password-stdin <ACCOUNT>.dkr.ecr.<REGION>.amazonaws.com

# kf-api
docker build -t kf-api:<TAG> -f Dockerfile .
docker tag kf-api:<TAG> <ACCOUNT>.dkr.ecr.<REGION>.amazonaws.com/kf-api:<TAG>
docker push <ACCOUNT>.dkr.ecr.<REGION>.amazonaws.com/kf-api:<TAG>

# kf-embed
docker build -t kf-embed:<TAG> -f Dockerfile.embed .
docker tag kf-embed:<TAG> <ACCOUNT>.dkr.ecr.<REGION>.amazonaws.com/kf-embed:<TAG>
docker push <ACCOUNT>.dkr.ecr.<REGION>.amazonaws.com/kf-embed:<TAG>
```

### B.3 Create Namespace

```bash
kubectl create namespace kf-prod
```

### B.4 Create Secret (AWS)

```bash
kubectl create secret generic kf-secrets \
  --namespace=kf-prod \
  \
  --from-literal=DEEPSEEK_API_KEY="<DeepSeek API Key>" \
  --from-literal=KF_API_KEY="<API gateway auth key>" \
  --from-literal=EMBED_API_KEY="<internal embed auth key>" \
  \
  --from-literal=REDIS_URL="rediss://<elasticache-endpoint>:6379/0" \
  \
  --from-literal=MYSQL_HOST="<RDS MySQL endpoint>" \
  --from-literal=MYSQL_PORT="3306" \
  --from-literal=MYSQL_USER="<MySQL username>" \
  --from-literal=MYSQL_PASSWORD="<MySQL password>" \
  --from-literal=MYSQL_DB="kf_metrics" \
  --from-literal=KF_METRICS_DB_HOST="<same as MYSQL_HOST>" \
  --from-literal=KF_METRICS_DB_PORT="3306" \
  --from-literal=KF_METRICS_DB_USER="<same as MYSQL_USER>" \
  --from-literal=KF_METRICS_DB_PASSWORD="<same as MYSQL_PASSWORD>" \
  --from-literal=KF_METRICS_DB_NAME="kf_metrics" \
  --from-literal=KF_METRICS_DB_TYPE="mysql" \
  \
  --from-literal=PG_HOST="<RDS PostgreSQL endpoint>" \
  --from-literal=PG_PORT="5432" \
  --from-literal=PG_USER="<PostgreSQL username>" \
  --from-literal=PG_PASSWORD="<PostgreSQL password>" \
  --from-literal=PG_DB="kf_analytics" \
  \
  --from-literal=AWS_REGION="<REGION>" \
  --from-literal=S3_CONFIG_BUCKET="kf-config-prod" \
  --from-literal=S3_UI_BUCKET="kf-ui-prod"
```

> **Note**: AWS EKS does not use OSS credentials. Instead, `AWS_REGION` + S3 bucket names are used. IRSA provides S3 access permissions, so AWS Access Keys are not stored in the Secret.

**Verify Secret**:

```bash
kubectl get secret kf-secrets -n kf-prod -o jsonpath='{.data}' | python3 -c "
import json, sys
for k, v in sorted(json.load(sys.stdin).items()):
    print(f'  {k:30s} = {v[:4]}***')
"
```

### B.5 AWS EKS-Specific K8s Manifests

The following manifests highlight key differences from the ACK version. For complete Deployment/Service manifests, reference the templates in `k8s/` and replace placeholders accordingly.

#### StorageClass: gp3 (replaces ESSD)

```yaml
# k8s-aws/storageclass.yaml
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
```

#### Qdrant StatefulSet (AWS)

Modify `storageClassName` from the ACK version:

```yaml
# k8s-aws/qdrant-statefulset.yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: qdrant
  namespace: kf-prod
spec:
  serviceName: qdrant
  replicas: 1
  selector:
    matchLabels:
      app: qdrant
  template:
    metadata:
      labels:
        app: qdrant
    spec:
      containers:
        - name: qdrant
          image: qdrant/qdrant:latest
          ports:
            - containerPort: 6333
              name: http
            - containerPort: 6334
              name: grpc
          volumeMounts:
            - name: qdrant-storage
              mountPath: /qdrant/storage
          resources:
            requests:
              cpu: "1"
              memory: "2Gi"
            limits:
              cpu: "2"
              memory: "4Gi"
          livenessProbe:
            httpGet:
              path: /health
              port: 6333
            initialDelaySeconds: 10
            periodSeconds: 5
          readinessProbe:
            httpGet:
              path: /readyz
              port: 6333
            initialDelaySeconds: 5
            periodSeconds: 5
  volumeClaimTemplates:
    - metadata:
        name: qdrant-storage
      spec:
        accessModes: ["ReadWriteOnce"]
        storageClassName: qdrant-storage
        resources:
          requests:
            storage: 20Gi
```

#### Config PVC: EFS CSI (replaces OSS CSI)

```yaml
# k8s-aws/config-pvc.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: workflow-config
  namespace: kf-prod
spec:
  accessModes:
    - ReadWriteMany
  storageClassName: efs-sc
  resources:
    requests:
      storage: 1Gi
```

#### Ingress: AWS Load Balancer Controller

```yaml
# k8s-aws/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: kf-ingress
  namespace: kf-prod
  annotations:
    alb.ingress.kubernetes.io/scheme: internet-facing
    alb.ingress.kubernetes.io/target-type: ip
    alb.ingress.kubernetes.io/healthcheck-path: /health
    alb.ingress.kubernetes.io/listen-ports: '[{"HTTP": 80}]'
spec:
  ingressClassName: alb
  rules:
    - host: kf.example.com
      http:
        paths:
          - path: /api/v1/workflows
            pathType: Prefix
            backend:
              service:
                name: chat-api
                port:
                  number: 8000
          - path: /api/v1/sessions
            pathType: Prefix
            backend:
              service:
                name: chat-api
                port:
                  number: 8000
          - path: /export
            pathType: Prefix
            backend:
              service:
                name: chat-api
                port:
                  number: 8000
          - path: /health
            pathType: Exact
            backend:
              service:
                name: chat-api
                port:
                  number: 8000
          - path: /ready
            pathType: Exact
            backend:
              service:
                name: chat-api
                port:
                  number: 8000
          - path: /metrics
            pathType: Prefix
            backend:
              service:
                name: admin-api
                port:
                  number: 8000
          - path: /collections
            pathType: Prefix
            backend:
              service:
                name: admin-api
                port:
                  number: 8000
          - path: /documents
            pathType: Prefix
            backend:
              service:
                name: admin-api
                port:
                  number: 8000
          - path: /status
            pathType: Exact
            backend:
              service:
                name: admin-api
                port:
                  number: 8000
```

#### Deployment Adjustments (AWS)

Compared to the ACK version, image references change to ECR and some env vars adjust to AWS format. Example for chat-api:

```yaml
# k8s-aws/chat-api-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: chat-api
  namespace: kf-prod
spec:
  replicas: 1
  selector:
    matchLabels:
      app: chat-api
  template:
    metadata:
      labels:
        app: chat-api
    spec:
      serviceAccountName: kf-s3-access    # IRSA role binding
      containers:
        - name: chat-api
          image: <ACCOUNT>.dkr.ecr.<REGION>.amazonaws.com/kf-api:<TAG>
          ports:
            - containerPort: 8000
          env:
            - name: KF_MODE
              value: "chat"
            - name: QDRANT_HOST
              value: "qdrant.kf-prod.svc.cluster.local"
            - name: QDRANT_PORT
              value: "6334"
            - name: EMBED_BASE_URL
              value: "http://embed.kf-prod.svc.cluster.local:8100/v1"
            - name: EMBED_MODEL
              value: "nomic-embed-text"
            - name: LOG_LEVEL
              value: "INFO"
            - name: CONFIG_PATH
              value: "/app/config"
            - name: KF_METRICS_ENGINE
              value: "mysql"
            - name: AWS_REGION
              value: "<REGION>"
          envFrom:
            - secretRef:
                name: kf-secrets
          volumeMounts:
            - name: workflows
              mountPath: /app/config/workflows
          resources:
            requests:
              cpu: "500m"
              memory: "512Mi"
            limits:
              cpu: "2"
              memory: "2Gi"
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 10
            periodSeconds: 15
          readinessProbe:
            httpGet:
              path: /ready
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 5
      volumes:
        - name: workflows
          persistentVolumeClaim:
            claimName: workflow-config
```

> Adjust admin-api (change `KF_MODE=admin`) and kf-embed Deployments similarly.

### B.6 Deployment Commands (AWS)

```bash
export NAMESPACE=kf-prod
export AWS_ACCOUNT=<ACCOUNT>
export REGION=<REGION>
export API_TAG=<TAG>
export EMBED_TAG=<TAG>
export ECR="${AWS_ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com"

# StorageClass
kubectl apply -f k8s-aws/storageclass.yaml

# chat-api
kubectl apply -f k8s-aws/chat-api-deployment.yaml
kubectl apply -f k8s-aws/chat-api-service.yaml

# admin-api
kubectl apply -f k8s-aws/admin-api-deployment.yaml
kubectl apply -f k8s-aws/admin-api-service.yaml

# kf-embed
kubectl apply -f k8s-aws/embed-deployment.yaml
kubectl apply -f k8s-aws/embed-service.yaml

# Qdrant
kubectl apply -f k8s-aws/qdrant-statefulset.yaml
kubectl apply -f k8s-aws/qdrant-service.yaml

# Config PVC (EFS)
kubectl apply -f k8s-aws/config-pvc.yaml

# Ingress (ALB)
kubectl apply -f k8s-aws/ingress.yaml
```

### B.7 IAM Roles for Service Accounts (IRSA)

Create an IAM ServiceAccount for S3 access (config mount and UI upload):

```bash
# Create IAM ServiceAccount
eksctl create iamserviceaccount \
  --name kf-s3-access \
  --namespace kf-prod \
  --cluster <CLUSTER_NAME> \
  --attach-policy-arn arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess \
  --approve
```

> For write access (e.g., UI uploads), replace with a custom policy that includes `s3:PutObject`.

### B.8 Verify Deployment (AWS)

```bash
# Check Pod status
kubectl get pods -n kf-prod

# Check Services
kubectl get svc -n kf-prod

# Check Ingress (ALB)
kubectl get ingress -n kf-prod

# Get ALB DNS and health check
ALB_DNS=$(kubectl get ingress kf-ingress -n kf-prod -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
curl http://${ALB_DNS}/health

# Wait for all Pods to be ready
kubectl wait --for=condition=ready pod -l app=chat-api -n kf-prod --timeout=120s
kubectl wait --for=condition=ready pod -l app=admin-api -n kf-prod --timeout=120s
kubectl wait --for=condition=ready pod -l app=embed -n kf-prod --timeout=120s
kubectl wait --for=condition=ready pod -l app=qdrant -n kf-prod --timeout=120s
```

### B.9 Resource Requirements (AWS)

| Component | requests | limits | Notes |
|---|---|---|---|
| chat-api | 0.5 CPU / 512Mi | 2 CPU / 2Gi | 1 replica |
| admin-api | 0.5 CPU / 512Mi | 2 CPU / 2Gi | 1 replica |
| kf-embed | 0.2 CPU / 256Mi | 0.5 CPU / 512Mi | Model baked in, no PVC needed |
| Qdrant | 1 CPU / 2Gi | 2 CPU / 4Gi | 1 replica + gp3 EBS (20Gi) |

---

## C. CI/CD (Jenkinsfile)

The Jenkins pipeline (`Jenkinsfile`) automates build, upload, and deployment. Key stages:

| Stage | Description |
|---|---|
| **Build Images** | Builds kf-api (Dockerfile) and kf-embed (Dockerfile.embed) in parallel, pushes to ACR/ECR |
| **Resolve Image Tags** | When skipping build (REBUILD_IMAGES=false), verifies the specified image tag exists |
| **Upload Web GUI to OSS/S3** | `npm ci && npm run build`, uploads `dist/` to OSS or S3 bucket |
| **Deploy Secrets to K8s** | `withCredentials` injects creds → `scripts/create-k8s-secrets.sh` upserts Secret |
| **Deploy to K8s** | Parallel deploy of chat-api, admin-api, embed, qdrant, global (namespace + pvc + ingress) |
| **Health Check** | `kubectl wait --for=condition=ready` verifies each service's Pod readiness |

Parameterized build supports:
- `ENV`: Deployment environment (test / production)
- `SERVICES`: Select services to deploy (chat-api, admin-api, web-gui, embed, qdrant)
- `IMAGE_TAG`: Specify image tag (to reuse existing images)
- `REBUILD_IMAGES`: Whether to rebuild images
- `DOMAIN`: Ingress domain

---

## D. SPA Static Asset Deployment

The web frontend (Vue 3 + Vite SPA) is deployed independently of the API, hosted on object storage with CDN distribution.

| | ACK (Alibaba Cloud) | EKS (AWS) |
|---|---|---|
| **Storage** | OSS bucket (`kf-ui-{env}`) | S3 bucket (`kf-ui-prod`) |
| **CDN** | Alibaba Cloud CDN | CloudFront |
| **Access** | CDN domain | CloudFront domain |
| **Upload** | `ossutil cp -r dist/ oss://bucket/ --update` | `aws s3 cp dist/ s3://bucket/ --recursive` |

**Build & Upload Commands**:

```bash
# Build SPA
cd src/gui/ui && npm ci && npm run build

# ACK: Upload to OSS
ossutil cp -r dist/ oss://kf-ui-<ENV>/ --update

# AWS: Upload to S3
aws s3 cp dist/ s3://kf-ui-prod/ --recursive

# Invalidate CDN cache (ACK)
aliyun cdn RefreshObjectCaches --ObjectPath https://<CDN_DOMAIN>/

# Invalidate CDN cache (AWS)
aws cloudfront create-invalidation --distribution-id <DISTRIBUTION_ID> --paths "/*"
```

---

## Configuration Reference

| Resource | File (ACK) | Description |
|---|---|---|
| Namespace | `k8s/namespace.yaml` | Application isolation |
| Secret | `k8s/secret.yaml` | **Template file**, structure reference only |
| chat-api | `k8s/chat-api/` | User-facing traffic (KF_MODE=chat) |
| admin-api | `k8s/admin-api/` | Internal management (KF_MODE=admin) |
| kf-embed | `k8s/embed/` | FastEmbed vectorization microservice |
| Qdrant | `k8s/qdrant/` | StatefulSet + ESSD |
| OSS PVC | `k8s/oss-pvc.yaml` | Workflow YAML config mount |
| Ingress | `k8s/ingress.yaml` | Dual-backend ALB Ingress |
