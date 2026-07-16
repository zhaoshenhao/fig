# KF 部署指南

[English](deployment_EN.md)

---

## 概述

系统以 3 个容器镜像部署在 Kubernetes 上：

| 镜像 | 运行时 | K8s 对象 | 说明 |
|------|--------|----------|------|
| **kf-api** | FastAPI (uvicorn) | 2 个 Deployment | chat-api + admin-api，同一镜像，通过 `KF_MODE` 环境变量区分路由组 |
| **kf-embed** | FastEmbed (ONNX) | 1 个 Deployment | 模型已烘焙进镜像，运行时不联网 |
| **Qdrant** | 官方 qdrant/qdrant | StatefulSet 1 副本 | 向量数据库，通过云盘持久化 |

外部托管服务：DeepSeek API (LLM)、Redis (会话共享)、MySQL RDS (metrics/主库)、PostgreSQL RDS (分析库)、OSS/S3 (配置 + SPA 静态资源)

### 架构图

```
ALB / AWS ALB Ingress
  ├── /api/v1/workflows/*/run → chat-api (Deployment, KF_MODE=chat)
  ├── /metrics/*              → admin-api (Deployment, KF_MODE=admin)
  ├── SPA 静态资源             → OSS/S3 + CDN
  │
  Internal services:
  ├── chat-api  → Qdrant (StatefulSet, gRPC:6334)
  ├── chat-api  → kf-embed (Deployment, HTTP:8100)
  ├── chat-api  → Redis      (external, session)
  ├── chat-api  → MySQL RDS  (external, metrics)
  ├── admin-api → MySQL RDS  (external, metrics)
  └── chat-api  → DeepSeek API (external)
```

### 服务清单

| 服务 | K8s 对象 | 镜像 | 副本 | 端口 |
|---------|-----------|-------|----------|------|
| chat-api | Deployment | kf-api | 1 | 8000 |
| admin-api | Deployment | kf-api | 1 | 8000 |
| kf-embed | Deployment | kf-embed | 1 | 8100 |
| Qdrant | StatefulSet | qdrant/qdrant | 1 | 6334(gRPC) / 6333(HTTP) |

---

## 前提条件（双平台通用）

- 已有 Kubernetes 集群（ACK 或 EKS）
- kubectl 已配置连接集群
- Ingress Controller 已安装（ACK: ALB Ingress Controller / EKS: AWS Load Balancer Controller）
- 容器镜像仓库已就绪（ACK: ACR / EKS: ECR）
- 外部托管服务已就绪：RDS MySQL、RDS PostgreSQL、Redis、DeepSeek API key

---

## A. 阿里云 ACK 部署

### A.1 构建并推送镜像

```bash
# kf-api (FastAPI)
docker build -t <ACR_REGISTRY>/kf-api:<TAG> -f Dockerfile .
docker push <ACR_REGISTRY>/kf-api:<TAG>

# kf-embed (FastEmbed)
docker build -t <ACR_REGISTRY>/kf-embed:<TAG> -f Dockerfile.embed .
docker push <ACR_REGISTRY>/kf-embed:<TAG>
```

### A.2 创建命名空间

```bash
kubectl apply -f k8s/namespace.yaml
```

> `k8s/namespace.yaml` 定义了 `<NAMESPACE>` 命名空间。请先将文件中的 `<NAMESPACE>` 替换为实际值（如 `mb-test`、`mb-pr`），或直接用 sed 替换。

### A.3 创建 Secret

> `k8s/secret.yaml` 是结构模板，**不含真实密钥**。实际部署必须通过以下命令注入。

```bash
kubectl create secret generic kf-secrets \
  --namespace=<NAMESPACE> \
  \
  --from-literal=DEEPSEEK_API_KEY="<DeepSeek API Key>" \
  --from-literal=KF_API_KEY="<API 网关鉴权 Key>" \
  --from-literal=EMBED_API_KEY="<embed 服务内部鉴权 Key>" \
  \
  --from-literal=REDIS_URL="redis://<Redis 内网地址>:6379/0" \
  \
  --from-literal=MYSQL_HOST="<MySQL 内网地址>" \
  --from-literal=MYSQL_PORT="3306" \
  --from-literal=MYSQL_USER="<MySQL 用户名>" \
  --from-literal=MYSQL_PASSWORD="<MySQL 密码>" \
  --from-literal=MYSQL_DB="kf_metrics" \
  --from-literal=KF_METRICS_DB_HOST="<同 MYSQL_HOST>" \
  --from-literal=KF_METRICS_DB_PORT="3306" \
  --from-literal=KF_METRICS_DB_USER="<同 MYSQL_USER>" \
  --from-literal=KF_METRICS_DB_PASSWORD="<同 MYSQL_PASSWORD>" \
  --from-literal=KF_METRICS_DB_NAME="kf_metrics" \
  --from-literal=KF_METRICS_DB_TYPE="mysql" \
  \
  --from-literal=PG_HOST="<PostgreSQL 内网地址>" \
  --from-literal=PG_PORT="5432" \
  --from-literal=PG_USER="<PostgreSQL 用户名>" \
  --from-literal=PG_PASSWORD="<PostgreSQL 密码>" \
  --from-literal=PG_DB="kf_analytics" \
  \
  --from-literal=OSS_ACCESS_KEY_ID="<OSS AccessKey ID>" \
  --from-literal=OSS_ACCESS_KEY_SECRET="<OSS AccessKey Secret>" \
  --from-literal=OSS_ENDPOINT="oss-cn-hangzhou.aliyuncs.com" \
  --from-literal=OSS_WORKFLOW_BUCKET="kf-config-<ENV>" \
  --from-literal=OSS_UI_BUCKET="kf-ui-<ENV>"
```

> **注意**：OSS 凭据仅用于 CI/CD 流水线上传 UI 静态文件到 OSS，运行时应用不消费。

**验证 Secret**：

```bash
kubectl get secret kf-secrets -n <NAMESPACE> -o jsonpath='{.data}' | python3 -c "
import json, sys
for k, v in sorted(json.load(sys.stdin).items()):
    print(f'  {k:30s} = {v[:4]}***')
"
```

### A.4 部署 K8s 资源

设以下占位符（按实际值替换）：

| 占位符 | 说明 | 示例 |
|---|---|---|
| `<NAMESPACE>` | K8s 命名空间 | `mb-test` |
| `<ACR_REGISTRY>` | ACR 镜像仓库地址 | `registry.cn-hangzhou.aliyuncs.com/your-team` |
| `<API_IMAGE_TAG>` | kf-api 镜像标签 | `v1.0.0` |
| `<EMBED_IMAGE_TAG>` | kf-embed 镜像标签 | `v1.0.0` |
| `<DOMAIN>` | ALB Ingress 域名 | `kf-test.example.com` |

**一键部署**：

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

# OSS CSI PVC (工作流配置挂载)
cat k8s/oss-pvc.yaml | sed "s|<NAMESPACE>|$NS|g" | kubectl apply -f -

# Ingress (ALB, 双后端路由)
cat k8s/ingress.yaml | sed "s|<NAMESPACE>|$NS|g; s|<DOMAIN>|$DOMAIN|g" | kubectl apply -f -
```

**分步部署**：

```bash
# 1. chat-api（用户流量）
kubectl apply -f k8s/chat-api/

# 2. admin-api（内部管理）
kubectl apply -f k8s/admin-api/

# 3. kf-embed（FastEmbed 向量化微服务，模型已烘焙进镜像，启动仅需加载进内存）
kubectl apply -f k8s/embed/

# 4. Qdrant（1 副本 StatefulSet + ESSD）
kubectl apply -f k8s/qdrant/

# 5. OSS CSI PVC（工作流 YAML 配置挂载）
kubectl apply -f k8s/oss-pvc.yaml

# 6. Ingress（ALB 双后端路由）
kubectl apply -f k8s/ingress.yaml
```

### A.5 验证部署

```bash
# 检查 Pod 状态
kubectl get pods -n <NAMESPACE>

# 检查 Service
kubectl get svc -n <NAMESPACE>

# 检查 Ingress (ALB)
kubectl get ingress -n <NAMESPACE>

# 健康检查
curl http://<DOMAIN>/health   # chat-api 健康
curl http://<DOMAIN>/status   # admin-api 状态

# 等待所有 Pod Ready
kubectl wait --for=condition=ready pod -l app=chat-api -n <NAMESPACE> --timeout=120s
kubectl wait --for=condition=ready pod -l app=admin-api -n <NAMESPACE> --timeout=120s
kubectl wait --for=condition=ready pod -l app=embed -n <NAMESPACE> --timeout=120s
kubectl wait --for=condition=ready pod -l app=qdrant -n <NAMESPACE> --timeout=120s
```

### A.6 凭证注入架构

```
kubectl create secret kf-secrets   ← 手工创建 / Jenkins withCredentials
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
    ┌────┴──── 两种注入方式 ─────────┐
    │                                │
    ▼                                ▼
envFrom.secretRef              valueFrom.secretKeyRef
(chat-api / admin-api)         (kf-embed)
→ 注入全部 20+ key             → 仅注入 EMBED_API_KEY
    │                                │
    ▼                                ▼
  Pod 环境变量 ←── os.environ
    │
    ├── _resolve_env()
    │   将 YAML 中的 ${VAR:-default} 替换为环境变量值
    │   → LLMConfig, DBConfig, SessionConfig, EmbedConfig...
    │
    └── os.environ.get("VAR")  直接读取
         → factory.py, embed_service/app.py, logger
```

#### 凭证消费链路表

| Secret Key | 注入方式 | 消费位置 |
|---|---|---|
| `DEEPSEEK_API_KEY` | envFrom → `_resolve_env()` | `config/llm.yaml` (LLM 调用), `config/session.yaml` (会话摘要) |
| `KF_API_KEY` | envFrom → `_resolve_env()` | `config/auth.yaml` (API 鉴权) |
| `EMBED_API_KEY` | envFrom + valueFrom | `config/embed.yaml` (chat/admin 调用 embed), `src/embed_service/app.py:40` (embed 服务自身鉴权) |
| `REDIS_URL` | envFrom → `_resolve_env()` | `config/session.yaml` → `src/session/redis_store.py` |
| `MYSQL_HOST/PORT/USER/PASSWORD/DB` | envFrom → `_resolve_env()` | `config/db.yaml` → 数据库连接池 |
| `KF_METRICS_DB_*` | envFrom → `_resolve_env()` / `os.environ.get()` | `config/db.yaml`, `config/metrics.yaml`, `src/metrics/factory.py` |
| `PG_HOST/PORT/USER/PASSWORD/DB` | envFrom → `_resolve_env()` | `config/db.yaml` → PostgreSQL 连接池 |
| `OSS_ACCESS_KEY_ID/SECRET/ENDPOINT` | envFrom (Jenkins 注入) | CI/CD 流水线用于 ossutil 上传 UI 静态文件，**运行时应用不消费** |
| `OSS_WORKFLOW_BUCKET/UI_BUCKET` | envFrom (Jenkins 注入) | 同上 |

#### 配置文件占位符解析

`src/config.py:_resolve_env()` 用正则匹配 YAML 中的 `${VAR}` / `${VAR:-default}` 占位符：

```
config/llm.yaml:     api_key: ${DEEPSEEK_API_KEY}            → os.environ["DEEPSEEK_API_KEY"]
config/db.yaml:      host: ${MYSQL_HOST:-127.0.0.1}          → os.environ["MYSQL_HOST"]
config/session.yaml: url: ${REDIS_URL:-redis://localhost}     → os.environ["REDIS_URL"]
config/embed.yaml:   api_key: ${EMBED_API_KEY:-}              → os.environ["EMBED_API_KEY"]
config/metrics.yaml: engine: ${KF_METRICS_ENGINE:-sqlite}    → "mysql"
```

### A.7 资源需求 (ACK)

| 组件 | requests | limits | 备注 |
|---|---|---|---|
| chat-api | 0.5 CPU / 512Mi | 2 CPU / 2Gi | 1 副本 |
| admin-api | 0.5 CPU / 512Mi | 2 CPU / 2Gi | 1 副本 |
| kf-embed | 0.2 CPU / 256Mi | 0.5 CPU / 512Mi | 模型已烘焙，不需要 PVC |
| Qdrant | 1 CPU / 2Gi | 2 CPU / 4Gi | 1 副本 + ESSD 云盘 |

---

## B. AWS EKS 部署

### B.1 额外前提条件

- EKS 集群已创建，kubectl 已配置
- AWS Load Balancer Controller 已安装
- ECR 仓库已创建：`kf-api`、`kf-embed`
- EFS CSI Driver 或 S3 CSI Driver 已安装（用于工作流配置持久卷）
- 外部托管服务已就绪：RDS MySQL、RDS PostgreSQL、ElastiCache Redis、S3 buckets (`kf-config-prod` / `kf-ui-prod`)
- IAM 角色已准备（用于 IRSA 授权 S3 访问）

### B.2 构建并推送镜像到 ECR

```bash
# 登录 ECR
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

### B.3 创建命名空间

```bash
kubectl create namespace kf-prod
```

### B.4 创建 Secret (AWS)

```bash
kubectl create secret generic kf-secrets \
  --namespace=kf-prod \
  \
  --from-literal=DEEPSEEK_API_KEY="<DeepSeek API Key>" \
  --from-literal=KF_API_KEY="<API 网关鉴权 Key>" \
  --from-literal=EMBED_API_KEY="<embed 服务内部鉴权 Key>" \
  \
  --from-literal=REDIS_URL="rediss://<elasticache-endpoint>:6379/0" \
  \
  --from-literal=MYSQL_HOST="<RDS MySQL endpoint>" \
  --from-literal=MYSQL_PORT="3306" \
  --from-literal=MYSQL_USER="<MySQL 用户名>" \
  --from-literal=MYSQL_PASSWORD="<MySQL 密码>" \
  --from-literal=MYSQL_DB="kf_metrics" \
  --from-literal=KF_METRICS_DB_HOST="<同 MYSQL_HOST>" \
  --from-literal=KF_METRICS_DB_PORT="3306" \
  --from-literal=KF_METRICS_DB_USER="<同 MYSQL_USER>" \
  --from-literal=KF_METRICS_DB_PASSWORD="<同 MYSQL_PASSWORD>" \
  --from-literal=KF_METRICS_DB_NAME="kf_metrics" \
  --from-literal=KF_METRICS_DB_TYPE="mysql" \
  \
  --from-literal=PG_HOST="<RDS PostgreSQL endpoint>" \
  --from-literal=PG_PORT="5432" \
  --from-literal=PG_USER="<PostgreSQL 用户名>" \
  --from-literal=PG_PASSWORD="<PostgreSQL 密码>" \
  --from-literal=PG_DB="kf_analytics" \
  \
  --from-literal=AWS_REGION="<REGION>" \
  --from-literal=S3_CONFIG_BUCKET="kf-config-prod" \
  --from-literal=S3_UI_BUCKET="kf-ui-prod"
```

> **注意**：AWS EKS 不使用 OSS 凭据，改为 `AWS_REGION` + S3 bucket 名称。IRSA 提供 S3 访问权限，无需在 Secret 中存储 AWS Access Key。

**验证 Secret**：

```bash
kubectl get secret kf-secrets -n kf-prod -o jsonpath='{.data}' | python3 -c "
import json, sys
for k, v in sorted(json.load(sys.stdin).items()):
    print(f'  {k:30s} = {v[:4]}***')
"
```

### B.5 AWS EKS 专用 K8s 清单

以下清单与 ACK 版本的关键差异点。完整的 Deployment/Service 清单可参考 `k8s/` 目录中的模板，替换占位符即可。

#### StorageClass: gp3 (替代 ESSD)

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

在 ACK 版本基础上修改 `storageClassName`：

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

#### Config PVC: EFS CSI (替代 OSS CSI)

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

#### Deployment 调整 (AWS)

与 ACK 版本相比，Deployment 镜像引用改为 ECR，部分环境变量调整为 AWS 格式。以 chat-api 为例：

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
      serviceAccountName: kf-s3-access    # IRSA 角色绑定
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

> 同理调整 admin-api（改 `KF_MODE=admin`）和 kf-embed 的 Deployment。

### B.6 部署命令 (AWS)

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

为 ServiceAccount 绑定 IAM 角色以实现对 S3 的访问权限（用于配置挂载和 UI 上传）：

```bash
# 创建 IAM ServiceAccount
eksctl create iamserviceaccount \
  --name kf-s3-access \
  --namespace kf-prod \
  --cluster <CLUSTER_NAME> \
  --attach-policy-arn arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess \
  --approve
```

> 如需写入权限（如 UI 上传），可将 policy 替换为自定义策略包含 `s3:PutObject` 权限。

### B.8 验证部署 (AWS)

```bash
# 检查 Pod 状态
kubectl get pods -n kf-prod

# 检查 Service
kubectl get svc -n kf-prod

# 检查 Ingress (ALB)
kubectl get ingress -n kf-prod

# 获取 ALB DNS 并健康检查
ALB_DNS=$(kubectl get ingress kf-ingress -n kf-prod -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
curl http://${ALB_DNS}/health

# 等待所有 Pod Ready
kubectl wait --for=condition=ready pod -l app=chat-api -n kf-prod --timeout=120s
kubectl wait --for=condition=ready pod -l app=admin-api -n kf-prod --timeout=120s
kubectl wait --for=condition=ready pod -l app=embed -n kf-prod --timeout=120s
kubectl wait --for=condition=ready pod -l app=qdrant -n kf-prod --timeout=120s
```

### B.9 资源需求 (AWS)

| 组件 | requests | limits | 备注 |
|---|---|---|---|
| chat-api | 0.5 CPU / 512Mi | 2 CPU / 2Gi | 1 副本 |
| admin-api | 0.5 CPU / 512Mi | 2 CPU / 2Gi | 1 副本 |
| kf-embed | 0.2 CPU / 256Mi | 0.5 CPU / 512Mi | 模型已烘焙，不需要 PVC |
| Qdrant | 1 CPU / 2Gi | 2 CPU / 4Gi | 1 副本 + gp3 EBS (20Gi) |

---

## C. CI/CD (Jenkinsfile)

Jenkins 流水线（`Jenkinsfile`）自动化构建、上传、部署流程。关键阶段：

| 阶段 | 说明 |
|---|---|
| **Build Images** | 并行构建 kf-api (Dockerfile) 和 kf-embed (Dockerfile.embed)，推送到 ACR/ECR |
| **Resolve Image Tags** | 当跳过构建时（REBUILD_IMAGES=false），验证指定镜像 tag 是否存在 |
| **Upload Web GUI to OSS/S3** | `npm ci && npm run build`，上传 `dist/` 到 OSS bucket 或 S3 bucket |
| **Deploy Secrets to K8s** | `withCredentials` 注入凭据 → `scripts/create-k8s-secrets.sh` 创建/更新 Secret |
| **Deploy to K8s** | 并行部署 chat-api、admin-api、embed、qdrant、global（namespace + pvc + ingress） |
| **Health Check** | `kubectl wait --for=condition=ready` 验证每个 service 的 Pod 就绪 |

参数化构建支持：
- `ENV`: 部署环境 (test / production)
- `SERVICES`: 选择部署服务 (chat-api, admin-api, web-gui, embed, qdrant)
- `IMAGE_TAG`: 指定镜像标签（复用已有镜像）
- `REBUILD_IMAGES`: 是否重新构建镜像
- `DOMAIN`: Ingress 域名

---

## D. SPA 静态资源部署

Web 前端（Vue 3 + Vite SPA）独立于 API 部署，托管在对象存储上通过 CDN 分发。

| | ACK (阿里云) | EKS (AWS) |
|---|---|---|
| **存储** | OSS bucket (`kf-ui-{env}`) | S3 bucket (`kf-ui-prod`) |
| **CDN** | Alibaba Cloud CDN | CloudFront |
| **访问** | CDN 域名直接访问 | CloudFront 域名直接访问 |
| **上传** | `ossutil cp -r dist/ oss://bucket/ --update` | `aws s3 cp dist/ s3://bucket/ --recursive` |

**构建 & 上传命令**：

```bash
# 构建 SPA
cd src/gui/ui && npm ci && npm run build

# ACK: 上传到 OSS
ossutil cp -r dist/ oss://kf-ui-<ENV>/ --update

# AWS: 上传到 S3
aws s3 cp dist/ s3://kf-ui-prod/ --recursive

# 清除 CDN 缓存 (ACK)
aliyun cdn RefreshObjectCaches --ObjectPath https://<CDN_DOMAIN>/

# 清除 CDN 缓存 (AWS)
aws cloudfront create-invalidation --distribution-id <DISTRIBUTION_ID> --paths "/*"
```

---

## 配置参考

| 资源 | 文件 (ACK) | 说明 |
|---|---|---|
| 命名空间 | `k8s/namespace.yaml` | 应用隔离 |
| 保密字典 | `k8s/secret.yaml` | **模板文件**，仅作结构参考 |
| chat-api | `k8s/chat-api/` | 用户流量 (KF_MODE=chat) |
| admin-api | `k8s/admin-api/` | 内部管理 (KF_MODE=admin) |
| kf-embed | `k8s/embed/` | FastEmbed 向量化微服务 |
| Qdrant | `k8s/qdrant/` | StatefulSet + ESSD |
| OSS PVC | `k8s/oss-pvc.yaml` | 工作流 YAML 配置挂载 |
| Ingress | `k8s/ingress.yaml` | 双后端 ALB Ingress |
