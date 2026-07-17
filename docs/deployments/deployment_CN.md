[English](deployment_EN.md)

# KF 智能客服 — 部署指南

---

## 选择部署场景

| 场景 | 适用情况 | 入口 |
|------|---------|------|
| **A. 本地开发** | 改代码、调试、单机跑起来看看 | [→ 本地开发指南](local-setup_CN.md) |
| **B. Docker Compose** | 单机部署、演示环境、不需要 K8s | [→ 场景 B](#b-docker-compose-部署) |
| **C. K8s（阿里云 ACK）** | 生产环境、弹性伸缩、已有 ACK 集群 | [→ 场景 C](#c-k8s-部署阿里云-ack) |
| **D. K8s（AWS EKS）** | 生产环境、多区域、已有 EKS 集群 | [→ 场景 D](#d-k8s-部署aws-eks) |

---

## 前提条件（所有 K8s 场景通用）

部署前请确认以下各项已就绪：

- [ ] **K8s 集群** 已创建，`kubectl` 可正常连接
- [ ] **Ingress Controller** 已安装（ACK: ALB Ingress Controller / EKS: AWS Load Balancer Controller）
- [ ] **容器镜像仓库** 可用（ACK: ACR / EKS: ECR）
- [ ] **MySQL 8.0+** 实例已创建（用于 metrics 存储）
- [ ] **PostgreSQL 14+** 实例已创建（用于分析查询）
- [ ] **Redis** 实例已创建（用于会话共享）
- [ ] **DeepSeek API Key** 已获取
- [ ] **对象存储**（OSS 或 S3）bucket 已创建（存储工作流配置 + SPA 静态文件）
- [ ] **域名** 已准备，DNS 记录可配置

---

## B. Docker Compose 部署

适用于单机部署或演示环境，不需要 K8s。

### B.1 前置条件

```bash
# 确认 Docker 版本 >= 20.10
docker --version

# 确认 docker compose 可用
docker compose version
```

### B.2 配置环境变量

```bash
# 1. 复制模板
cp .env.example .env

# 2. 编辑 .env，至少填写以下变量
vim .env
```

最小配置（SQLite 模式，无需外部数据库）：

```ini
DEEPSEEK_API_KEY=sk-your-deepseek-key     # 必填：LLM API Key
EMBED_API_KEY=                            # 可选：embed 内部鉴权，留空则不鉴权
KF_API_KEY=                               # 可选：API 鉴权，留空则不鉴权（开发推荐）
```

如需 MySQL/PostgreSQL，参考 `config/metrics.yaml` 和 `../deployments/metrics-db-setup.md`。

### B.3 启动所有服务

```bash
# 构建并启动（首次需构建 kf-api 和 kf-embed 镜像）
docker compose up -d --build

# 查看启动状态
docker compose ps

# 查看日志
docker compose logs -f api
```

### B.4 验证

```bash
# 健康检查
curl http://localhost:8000/health
# → {"status":"ok","timestamp":...,"startup_seconds":...}

# 就绪检查
curl http://localhost:8000/ready
# → {"status":"ready","workflows":["auto_film","default",...]}

# 工作流列表
curl http://localhost:8000/api/v1/workflows

# 发送消息
curl -X POST http://localhost:8000/api/v1/workflows/default/run \
  -H "Content-Type: application/json" \
  -d '{"query":"你好"}'
```

### B.5 切换 KF_MODE

默认 `docker-compose.yaml` 不设 `KF_MODE`（等价于 `full`），意味着同时启用 chat 和 admin 路由。如需分离：

```yaml
# docker-compose.yaml 中 api 服务添加
environment:
  KF_MODE: full          # full | chat | admin
```

### B.6 停止服务

```bash
docker compose down
```

---

## C. K8s 部署（阿里云 ACK）

### 系统架构

```
                      阿里云 ALB Ingress
                     ┌────────────────────────────────────┐
                     │  /api/v1/workflows/*/run → chat-api │
                     │  /metrics/*              → admin-api│
                     │  SPA 静态资源            → OSS + CDN│
                     └────────────────────────────────────┘
                                     │
           ┌─────────────────────────┼──────────────────────┐
           │                         │                      │
     ┌─────▼──────┐          ┌──────▼──────┐       ┌───────▼──────┐
     │  chat-api   │          │  admin-api  │       │   kf-embed   │
     │ KF_MODE=chat│          │KF_MODE=admin│       │   :8100      │
     │   :8000     │          │   :8000     │       └──────────────┘
     └──────┬──────┘          └──────┬──────┘
            │                        │
            │  ┌──────────────┐      │
            ├──►  Qdrant      │◄─────┘
            │  gRPC :6334    │
            │  └──────────────┘
            │
            ├──► Redis (外部)     — 会话共享
            ├──► MySQL RDS (外部)  — metrics 存储
            ├──► PG RDS (外部)     — 分析查询
            └──► DeepSeek API (外部)
```

### C.1 设置部署变量

```bash
# ═══════════════ 替换为实际值 ═══════════════
export NS="mb-test"                                        # K8s 命名空间
export ACR="registry.cn-hangzhou.aliyuncs.com/your-team"   # ACR 仓库地址
export API_TAG="v1.0.0"                                    # kf-api 镜像标签
export EMBED_TAG="v1.0.0"                                  # kf-embed 镜像标签
export DOMAIN="kf-test.example.com"                         # 域名
```

> **提示**：所有后续命令中的 `${NS}`、`${ACR}` 等都引用这些变量。先确认变量值正确再继续。

### C.2 构建并推送镜像

```bash
# 登录 ACR
docker login --username=<阿里云账号> ${ACR}

# 构建 kf-api（FastAPI 应用）
docker build -t ${ACR}/kf-api:${API_TAG} -f Dockerfile .
docker push ${ACR}/kf-api:${API_TAG}

# 构建 kf-embed（FastEmbed 向量化微服务）
docker build -t ${ACR}/kf-embed:${EMBED_TAG} -f Dockerfile.embed .
docker push ${ACR}/kf-embed:${EMBED_TAG}
```

> **说明**：Qdrant 使用官方镜像 `qdrant/qdrant:latest`，无需构建。

### C.3 创建命名空间

```bash
kubectl create namespace ${NS}
```

### C.4 创建 Secrets

> **重要：两步分开**。`kf-secrets` 给应用 pod 用，`kf-db-root-secret` 给数据库初始化 Job 用（用后即可删除）。

#### C.4.1 应用 Secret（kf-secrets）

```
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
  --from-literal=OSS_WORKFLOW_BUCKET="kf-config-${NS}" \
  --from-literal=OSS_UI_BUCKET="kf-ui-${NS}"
```

验证：

```bash
kubectl get secret kf-secrets -n ${NS}
# → NAME         TYPE    DATA   AGE
# → kf-secrets   Opaque  22     5s
```

#### C.4.2 数据库 Root Secret（一次性，可删除）

应用不使用 root 密码。此 Secret 仅供数据库初始化 Job 使用。

```bash
kubectl create secret generic kf-db-root-secret \
  --namespace=${NS} \
  --from-literal=DB_ROOT_USER="root" \
  --from-literal=DB_ROOT_PASSWORD="<MySQL-root-密码>"
```

### C.5 初始化数据库

在首次部署或数据库重新创建后，运行一次性 Job 创建 MySQL 数据库和应用用户：

```bash
kubectl apply -f deployment/k8s-aliyun/init-db-job.yaml
```

查看 Job 状态：

```bash
kubectl get job init-metrics-db -n ${NS}
kubectl logs job/init-metrics-db -n ${NS}
```

> **确认 Job 成功后再继续下一步**。应用启动时自动创建表结构，无需手动执行 DDL。

### C.6 部署基础服务（Qdrant + Embed）

```bash
# Qdrant StatefulSet（1 副本 + ESSD 云盘）
kubectl apply -f deployment/k8s-aliyun/qdrant/service.yaml
cat deployment/k8s-aliyun/qdrant/statefulset.yaml | sed "s|<NAMESPACE>|${NS}|g" | kubectl apply -f -

# kf-embed Deployment（向量化微服务，模型已烘焙进镜像）
cat deployment/k8s-aliyun/embed/service.yaml | sed "s|<NAMESPACE>|${NS}|g" | kubectl apply -f -
cat deployment/k8s-aliyun/embed/deployment.yaml \
  | sed "s|<NAMESPACE>|${NS}|g" \
  | sed "s|<ACR_REGISTRY>|${ACR}|g" \
  | sed "s|<EMBED_IMAGE_TAG>|${EMBED_TAG}|g" \
  | kubectl apply -f -

# 等待就绪
kubectl wait --for=condition=ready pod -l app=qdrant -n ${NS} --timeout=120s
kubectl wait --for=condition=ready pod -l app=embed -n ${NS} --timeout=120s
```

### C.7 部署应用（chat-api + admin-api）

```bash
# OSS CSI PVC（工作流 YAML 配置挂载）
cat deployment/k8s-aliyun/oss-pvc.yaml | sed "s|<NAMESPACE>|${NS}|g" | kubectl apply -f -

# chat-api Deployment（用户流量，KF_MODE=chat）
cat deployment/k8s-aliyun/chat-api/service.yaml | sed "s|<NAMESPACE>|${NS}|g" | kubectl apply -f -
cat deployment/k8s-aliyun/chat-api/deployment.yaml \
  | sed "s|<NAMESPACE>|${NS}|g" \
  | sed "s|<ACR_REGISTRY>|${ACR}|g" \
  | sed "s|<API_IMAGE_TAG>|${API_TAG}|g" \
  | kubectl apply -f -

# admin-api Deployment（内部管理，KF_MODE=admin）
cat deployment/k8s-aliyun/admin-api/service.yaml | sed "s|<NAMESPACE>|${NS}|g" | kubectl apply -f -
cat deployment/k8s-aliyun/admin-api/deployment.yaml \
  | sed "s|<NAMESPACE>|${NS}|g" \
  | sed "s|<ACR_REGISTRY>|${ACR}|g" \
  | sed "s|<API_IMAGE_TAG>|${API_TAG}|g" \
  | kubectl apply -f -

# 等待就绪
kubectl wait --for=condition=ready pod -l app=chat-api -n ${NS} --timeout=120s
kubectl wait --for=condition=ready pod -l app=admin-api -n ${NS} --timeout=120s
```

### C.8 配置 Ingress（ALB）

```bash
cat deployment/k8s-aliyun/ingress.yaml \
  | sed "s|<NAMESPACE>|${NS}|g" \
  | sed "s|<DOMAIN>|${DOMAIN}|g" \
  | kubectl apply -f -

# 等待 ALB 分配地址（可能需要 2-5 分钟）
kubectl get ingress -n ${NS} -w
```

### C.9 验证部署

```bash
# ── 1. 检查 Pod 状态 ──
kubectl get pods -n ${NS}
# 期望: 5 个 Pod，全部 Running 且 1/1 Ready

# ── 2. 检查 Service ──
kubectl get svc -n ${NS}

# ── 3. 获取 Ingress 地址 ──
INGRESS_ADDR=$(kubectl get ingress kf-ingress -n ${NS} \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
echo "Ingress: ${INGRESS_ADDR}"

# ── 4. 健康检查 ──
curl http://${INGRESS_ADDR}/health
curl http://${INGRESS_ADDR}/ready
curl http://${INGRESS_ADDR}/status

# ── 5. 功能测试 ──
curl http://${INGRESS_ADDR}/api/v1/workflows
curl -X POST http://${INGRESS_ADDR}/api/v1/workflows/default/run \
  -H "Content-Type: application/json" \
  -d '{"query":"你好"}'
```

### C.10 部署 SPA 前端（一次性）

```bash
cd src/gui/ui
npm ci && npm run build

# 上传到 OSS
ossutil cp -r dist/ oss://${OSS_UI_BUCKET}/ --update
```

### C.11 清理 Root Secret（建议）

数据库初始化 Job 完成后，删除 root Secret：

```bash
kubectl delete secret kf-db-root-secret -n ${NS}
```

### C.12 ACK 资源规格

| 组件 | requests | limits | 副本 | 存储 |
|------|----------|--------|------|------|
| chat-api | 0.5 CPU / 512Mi | 2 CPU / 2Gi | 1 | — |
| admin-api | 0.5 CPU / 512Mi | 2 CPU / 2Gi | 1 | — |
| kf-embed | 0.2 CPU / 256Mi | 0.5 CPU / 512Mi | 1 | — |
| Qdrant | 1 CPU / 2Gi | 2 CPU / 4Gi | 1 | ESSD 20Gi |

---

## D. K8s 部署（AWS EKS）

AWS EKS 与阿里云 ACK 的主要差异：

| 组件 | ACK | EKS |
|------|-----|-----|
| 镜像仓库 | ACR | ECR |
| Ingress | ALB Ingress Controller | AWS Load Balancer Controller |
| 向量存储 | Qdrant + ESSD | Qdrant + gp3 EBS |
| 配置挂载 | OSS CSI PVC | EFS CSI PVC |
| S3 访问 | OSS AccessKey (Secret) | IRSA (IAM 角色) |
| SPA 存储 | OSS bucket | S3 bucket + CloudFront |

### D.1 设置部署变量

```bash
export NS="kf-prod"
export AWS_ACCOUNT="123456789012"
export AWS_REGION="us-east-1"
export API_TAG="v1.0.0"
export EMBED_TAG="v1.0.0"
export DOMAIN="kf.example.com"
export ECR="${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com"
```

### D.2 构建并推送镜像到 ECR

```bash
# 登录 ECR
aws ecr get-login-password --region ${AWS_REGION} \
  | docker login --username AWS --password-stdin ${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com

# 确保 ECR 仓库存在
aws ecr describe-repositories --repository-names kf-api --region ${AWS_REGION} 2>/dev/null \
  || aws ecr create-repository --repository-name kf-api --region ${AWS_REGION}
aws ecr describe-repositories --repository-names kf-embed --region ${AWS_REGION} 2>/dev/null \
  || aws ecr create-repository --repository-name kf-embed --region ${AWS_REGION}

# 构建并推送
docker build -t kf-api:${API_TAG} -f Dockerfile .
docker tag kf-api:${API_TAG} ${ECR}/kf-api:${API_TAG}
docker push ${ECR}/kf-api:${API_TAG}

docker build -t kf-embed:${EMBED_TAG} -f Dockerfile.embed .
docker tag kf-embed:${EMBED_TAG} ${ECR}/kf-embed:${EMBED_TAG}
docker push ${ECR}/kf-embed:${EMBED_TAG}
```

### D.3 创建命名空间

```bash
kubectl create namespace ${NS}
```

### D.4 创建 AWS Secrets

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

> AWS 不使用 OSS 凭据。S3 访问通过 IRSA 授权，无需在 Secret 中存储 AWS Access Key。

### D.5 创建数据库 Root Secret

```bash
kubectl create secret generic kf-db-root-secret \
  --namespace=${NS} \
  --from-literal=DB_ROOT_USER="root" \
  --from-literal=DB_ROOT_PASSWORD="<RDS-root-密码>"
```

### D.6 初始化数据库

```bash
# 编辑 init-db-job.yaml 中的 DB_HOST（MySQL/PG），然后运行
kubectl apply -f deployment/k8s-aliyun/init-db-job.yaml

# 查看 Job 状态，等待 Successful
kubectl get job init-metrics-db -n ${NS} -w
```

### D.7 创建 AWS 专用存储资源

```bash
# StorageClass (gp3 EBS，用于 Qdrant)
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
```

> EFS CSI Driver 用于工作流配置 PVC（替代 ACK 的 OSS CSI）。需确保 EFS 文件系统和 EFS CSI Driver 已安装。

```bash
# Config PVC (EFS — 需要一个已创建的 EFS 文件系统 efs-sc)
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

### D.8 配置 IRSA（IAM Roles for Service Accounts）

> IRSA 允许 Pod 通过 IAM 角色访问 S3，无需在 Secret 中存储 AWS Access Key。

```bash
# 1. 创建 IAM 策略（允许访问 S3 bucket）
cat <<EOF > /tmp/kf-s3-policy.json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::kf-config-${NS}",
        "arn:aws:s3:::kf-config-${NS}/*",
        "arn:aws:s3:::kf-ui-${NS}",
        "arn:aws:s3:::kf-ui-${NS}/*"
      ]
    }
  ]
}
EOF

POLICY_ARN=$(aws iam create-policy \
  --policy-name kf-s3-access-${NS} \
  --policy-document file:///tmp/kf-s3-policy.json \
  --query 'Policy.Arn' --output text)

# 2. 创建 ServiceAccount 并关联 IAM 角色
eksctl create iamserviceaccount \
  --name kf-s3-access \
  --namespace ${NS} \
  --cluster <EKS_CLUSTER_NAME> \
  --attach-policy-arn ${POLICY_ARN} \
  --approve
```

### D.9 部署服务

AWS 部署清单与 ACK 的区别在于：
- 镜像地址：`${ECR}/kf-api:${API_TAG}` 替代 `${ACR}/kf-api:${API_TAG}`
- 工作流配置卷：`persistentVolumeClaim: workflow-config` (EFS) 替代 OSS CSI
- 无 `OSS_*` 环境变量，改为 `AWS_REGION`
- ServiceAccount 为 `kf-s3-access`

使用以下模板创建 `deployment/k8s-aws/` 目录下的清单（完整内容见附录），或直接参考 `deployment/k8s-aliyun/chat-api/deployment.yaml` 修改上述差异点后部署：

```bash
# Qdrant StatefulSet（使用 gp3 StorageClass）
cat deployment/k8s-aliyun/qdrant/statefulset.yaml \
  | sed "s|<NAMESPACE>|${NS}|g" \
  | sed "s|alicloud-disk-essd|qdrant-storage|g" \
  | kubectl apply -f -
kubectl apply -f deployment/k8s-aliyun/qdrant/service.yaml

# kf-embed
kubectl apply -f deployment/k8s-aliyun/embed/service.yaml
# 需修改 deployment.yaml 中镜像为 ECR 地址

# chat-api + admin-api
# 需修改 deployment.yaml 中镜像为 ECR 地址，新增 serviceAccountName: kf-s3-access

# Config PVC (EFS)
kubectl apply -f deployment/k8s-aws/config-pvc.yaml

# Ingress (ALB)
cat <<EOF | kubectl apply -f -
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: kf-ingress
  namespace: ${NS}
  annotations:
    alb.ingress.kubernetes.io/scheme: internet-facing
    alb.ingress.kubernetes.io/target-type: ip
    alb.ingress.kubernetes.io/healthcheck-path: /health
    alb.ingress.kubernetes.io/listen-ports: '[{"HTTP": 80}]'
spec:
  ingressClassName: alb
  rules:
    - host: ${DOMAIN}
      http:
        paths:
          - path: /api/v1/workflows
            pathType: Prefix
            backend:
              service: { name: chat-api, port: { number: 8000 } }
          - path: /api/v1/sessions
            pathType: Prefix
            backend:
              service: { name: chat-api, port: { number: 8000 } }
          - path: /export
            pathType: Prefix
            backend:
              service: { name: chat-api, port: { number: 8000 } }
          - path: /health
            pathType: Exact
            backend:
              service: { name: chat-api, port: { number: 8000 } }
          - path: /metrics
            pathType: Prefix
            backend:
              service: { name: admin-api, port: { number: 8000 } }
          - path: /collections
            pathType: Prefix
            backend:
              service: { name: admin-api, port: { number: 8000 } }
          - path: /documents
            pathType: Prefix
            backend:
              service: { name: admin-api, port: { number: 8000 } }
          - path: /status
            pathType: Exact
            backend:
              service: { name: admin-api, port: { number: 8000 } }
EOF

# 等待就绪
kubectl wait --for=condition=ready pod -l app=chat-api -n ${NS} --timeout=120s
kubectl wait --for=condition=ready pod -l app=admin-api -n ${NS} --timeout=120s
kubectl wait --for=condition=ready pod -l app=embed -n ${NS} --timeout=120s
kubectl wait --for=condition=ready pod -l app=qdrant -n ${NS} --timeout=120s
```

### D.10 验证部署

```bash
# 获取 ALB 地址
ALB_DNS=$(kubectl get ingress kf-ingress -n ${NS} \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')

# 健康检查
curl http://${ALB_DNS}/health
curl http://${ALB_DNS}/ready
curl http://${ALB_DNS}/status
curl http://${ALB_DNS}/api/v1/workflows
```

### D.11 部署 SPA 前端

```bash
cd src/gui/ui && npm ci && npm run build

# 上传到 S3
aws s3 cp dist/ s3://${S3_UI_BUCKET}/ --recursive

# 清除 CloudFront 缓存
aws cloudfront create-invalidation --distribution-id <DISTRIBUTION_ID> --paths "/*"
```

### D.12 EKS 资源规格

| 组件 | requests | limits | 副本 | 存储 |
|------|----------|--------|------|------|
| chat-api | 0.5 CPU / 512Mi | 2 CPU / 2Gi | 1 | — |
| admin-api | 0.5 CPU / 512Mi | 2 CPU / 2Gi | 1 | — |
| kf-embed | 0.2 CPU / 256Mi | 0.5 CPU / 512Mi | 1 | — |
| Qdrant | 1 CPU / 2Gi | 2 CPU / 4Gi | 1 | gp3 EBS 20Gi |

---

## 附录 A：数据库初始化详解

数据库初始化的完整说明见：

| 文档 | 内容 |
|------|------|
| `../deployments/metrics-db-setup.md` | 建库、建用户、环境变量、SQLite 迁移 → MySQL/PG |
| `db-schema-norm.md` | Schema 变更规范、新增迁移步骤 |
| `deployment/k8s-aliyun/init-db-job.yaml` | K8s 一次性 Job（用 root 密码建库 + 应用用户） |
| `deployment/scripts/init-metrics-db.sh` | 本地/单机一键初始化脚本 |

**要点**：表结构（DDL）由应用启动时的 `migrate()` 自动创建，无需手动执行 SQL 建表语句。

---

## 附录 B：SPA 前端部署

Web 前端（Vue 3 + Vite）独立于 API 部署：

| 步骤 | ACK | EKS |
|------|-----|-----|
| 构建 | `cd src/gui/ui && npm ci && npm run build` | 同左 |
| 上传 | `ossutil cp -r dist/ oss://kf-ui-${NS}/ --update` | `aws s3 cp dist/ s3://kf-ui-${NS}/ --recursive` |
| CDN | 阿里云 CDN（自动回源 OSS） | CloudFront（自动回源 S3） |
| 缓存刷新 | `aliyun cdn RefreshObjectCaches` | `aws cloudfront create-invalidation` |

---

## 附录 C：凭证注入原理

```
kubectl create secret kf-secrets  ← 手工 / Jenkins withCredentials
    │
    ▼
Secret "kf-secrets" (Opaque)
    │ 包含 22 个 key-value
    │
    ├── envFrom.secretRef → chat-api / admin-api Pod
    │    注入全部 key 作为环境变量
    │
    └── valueFrom.secretKeyRef → kf-embed Pod
         仅注入 EMBED_API_KEY

Pod 环境变量
    │
    ├── _resolve_env() 解析 YAML 中的 ${VAR:-default} 占位符
    │   如: api_key: ${DEEPSEEK_API_KEY} → os.environ["DEEPSEEK_API_KEY"]
    │
    └── os.environ.get() 直接读取（factory.py, app.py）
```

---

## 附录 D：常见问题

| 问题 | 排查方向 |
|------|---------|
| Pod 一直 `CrashLoopBackOff` | `kubectl logs <pod> -n ${NS}` 查看启动日志 |
| `/ready` 返回 `degraded` | Qdrant/Embed 连接失败，检查 Service 名称和端口 |
| Ingress 返回 404 | 域名未解析到 ALB，或 Ingress 路径不匹配 |
| 工作流执行报 LLM 错误 | `DEEPSEEK_API_KEY` 是否正确，检查 `kubectl get secret` |
| 数据库表不存在 | 确认 `init-db-job` 执行成功，检查 `migration.py` 日志 |

---

## 附录 E：K8s 清单文件索引

| 文件 | 说明 | K8s 对象 |
|------|------|----------|
| `deployment/k8s-aliyun/namespace.yaml` | 命名空间 | Namespace |
| `deployment/k8s-aliyun/secret.yaml` | **模板**（非运行文件） | Secret |
| `deployment/k8s-aliyun/init-db-job.yaml` | 数据库初始化 | Job |
| `deployment/k8s-aliyun/chat-api/deployment.yaml` | chat-api 部署 | Deployment |
| `deployment/k8s-aliyun/chat-api/service.yaml` | chat-api 服务 | Service |
| `deployment/k8s-aliyun/admin-api/deployment.yaml` | admin-api 部署 | Deployment |
| `deployment/k8s-aliyun/admin-api/service.yaml` | admin-api 服务 | Service |
| `deployment/k8s-aliyun/embed/deployment.yaml` | embed 向量化微服务 | Deployment |
| `deployment/k8s-aliyun/embed/service.yaml` | embed 服务 | Service |
| `deployment/k8s-aliyun/qdrant/statefulset.yaml` | Qdrant 向量数据库 | StatefulSet |
| `deployment/k8s-aliyun/qdrant/service.yaml` | Qdrant 服务 | Service |
| `deployment/k8s-aliyun/oss-pvc.yaml` | OSS CSI 持久卷（ACK） | PVC |
| `deployment/k8s-aliyun/ingress.yaml` | ALB Ingress（ACK） | Ingress |
| `deployment/k8s-aliyun/prometheus-rules.yaml` | Prometheus 告警规则 | PrometheusRule |
| `deployment/k8s-aliyun/grafana-dashboard.json` | Grafana 监控面板 | ConfigMap |
| `deployment/k8s-aliyun/job-build.yaml` | 文档构建 Job | Job |
