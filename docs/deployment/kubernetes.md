# K8s 部署指南（阿里云 ACK 托管版）

## 前提条件

- 已有 ACK 托管版集群
- kubectl 已配置连接集群
- ALB Ingress Controller + OSS CSI Driver（`alicloud-oss` storage class）已安装
- 镜像已推送至 ACR（阿里云容器镜像服务）
- 外部托管服务就绪：ApsaraDB RDS（MySQL）、ApsaraDB RDS（PostgreSQL）、Redis

## 架构

```
                    ┌──── ALB Ingress ────┐
                    │                      │
    /api/v1/workflows/*/run               /api/v1/workflows (list)
    /api/v1/sessions/*                    /metrics/*
    /export/*           chat-api          /collections/*       admin-api
    /health /ready     (Deployment)       /documents/*        (Deployment)
    SPA 静态资源 → OSS/CDN (外部)         /status (外部)
         │                                      │
         ├── Qdrant (StatefulSet 1副本 + ESSD)
         ├── kf-embed (Deployment, FastEmbed 向量化)
         ├── kf-secrets (Secret, 所有敏感凭据)
         ├── OSS CSI PVC (工作流 YAML 配置挂载)
         ├── Redis        (外部托管, 会话共享)
         ├── MySQL RDS    (外部托管, metrics/主库)
         ├── PostgreSQL RDS(外部托管, 分析库)
         └── DeepSeek API (外部 LLM, 走公网)
```

### 服务清单

| # | 模块 | K8s 对象 | 镜像 | 副本 | 端口 |
|---|------|----------|------|------|------|
| 1 | chat-api | Deployment | `<ACR>/kf-api` | 1 | 8000 |
| 2 | admin-api | Deployment | `<ACR>/kf-api` | 1 | 8000 |
| 3 | kf-embed | Deployment | `<ACR>/kf-embed` | 1 | 8100 |
| 4 | Qdrant | StatefulSet | `qdrant/qdrant` | 1 + ESSD | 6334(gRPC) |
| 5 | Secret | Secret (Opaque) | — | — | — |
| 6 | OSS PVC | PersistentVolumeClaim | — | — | — |

> chat-api 与 admin-api 使用同一 Docker 镜像，通过 `KF_MODE` 环境变量区分路由组。
> Web SPA 静态文件独立托管于阿里云 OSS（`kf-ui-{env}` bucket），通过 CDN 分发，**不与 API 同进程部署**。

---

## 1. 构建并推送镜像

```bash
# kf-api（纯 Python，无前端构建阶段）
docker build -t <ACR>/kf-api:<TAG> -f Dockerfile .
docker push <ACR>/kf-api:<TAG>

# kf-embed（FastEmbed 向量化微服务）
docker build -t <ACR>/kf-embed:<TAG> -f Dockerfile.embed .
docker push <ACR>/kf-embed:<TAG>
```

---

## 2. 创建命名空间

```bash
kubectl apply -f k8s/namespace.yaml
```

> 此处创建 `mb-test` 和 `mb-pr` 两个命名空间。如仅需一个，编辑 `k8s/namespace.yaml`。

---

## 3. 配置 Secret（手工创建）

> `k8s/secret.yaml` 是结构模板，**不含真实密钥**。实际部署必须通过以下命令注入。

### 3.1 mb-test（测试环境）

```bash
kubectl create secret generic kf-secrets \
  --namespace=mb-test \
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
  --from-literal=OSS_WORKFLOW_BUCKET="kf-config-mb-test" \
  --from-literal=OSS_UI_BUCKET="kf-ui-mb-test"
```

### 3.2 mb-pr（生产环境）

```bash
kubectl create secret generic kf-secrets \
  --namespace=mb-pr \
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
  --from-literal=OSS_WORKFLOW_BUCKET="kf-config-mb-pr" \
  --from-literal=OSS_UI_BUCKET="kf-ui-mb-pr"
```

> 替换所有 `<...>` 占位符为真实值。Metrics 库通常与主 MySQL 同实例，名称固定 `kf_metrics`。
> OSS 凭据仅用于 CI/CD 管道上传 Web GUI 静态文件，运行时不需要。

### 3.3 验证 Secret

```bash
kubectl get secret kf-secrets -n mb-test   -o jsonpath='{.data}' | python3 -c "
import json, sys
for k, v in sorted(json.load(sys.stdin).items()):
    print(f'  {k:30s} = {v[:4]}***')
"

kubectl get secret kf-secrets -n mb-pr     -o jsonpath='{.data}' | python3 -c "
import json, sys
for k, v in sorted(json.load(sys.stdin).items()):
    print(f'  {k:30s} = {v[:4]}***')
"
```

---

## 4. 部署剩余 K8s 资源

### 4.1 一键部署（含占位符替换）

```bash
# 设置占位符（按实际值替换）
export NS=mb-test
export ACR=registry.cn-hangzhou.aliyuncs.com/your-team
export API_TAG=v1.0.0
export EMBED_TAG=v1.0.0
export DOMAIN=kf-test.example.com

# 部署（chat-api + admin-api + embed + qdrant + oss-pvc + ingress）
cat k8s/chat-api/deployment.yaml   | sed "s|<NAMESPACE>|$NS|g; s|<ACR_REGISTRY>|$ACR|g; s|<API_IMAGE_TAG>|$API_TAG|g" | kubectl apply -f -
cat k8s/chat-api/service.yaml      | sed "s|<NAMESPACE>|$NS|g" | kubectl apply -f -
cat k8s/admin-api/deployment.yaml  | sed "s|<NAMESPACE>|$NS|g; s|<ACR_REGISTRY>|$ACR|g; s|<API_IMAGE_TAG>|$API_TAG|g" | kubectl apply -f -
cat k8s/admin-api/service.yaml     | sed "s|<NAMESPACE>|$NS|g" | kubectl apply -f -
cat k8s/embed/deployment.yaml      | sed "s|<NAMESPACE>|$NS|g; s|<ACR_REGISTRY>|$ACR|g; s|<EMBED_IMAGE_TAG>|$EMBED_TAG|g" | kubectl apply -f -
cat k8s/embed/service.yaml         | sed "s|<NAMESPACE>|$NS|g" | kubectl apply -f -
cat k8s/qdrant/statefulset.yaml    | sed "s|<NAMESPACE>|$NS|g" | kubectl apply -f -
cat k8s/qdrant/service.yaml        | sed "s|<NAMESPACE>|$NS|g" | kubectl apply -f -
cat k8s/oss-pvc.yaml               | sed "s|<NAMESPACE>|$NS|g" | kubectl apply -f -
cat k8s/ingress.yaml               | sed "s|<NAMESPACE>|$NS|g; s|<DOMAIN>|$DOMAIN|g" | kubectl apply -f -
```

### 4.2 分步部署

```bash
# chat-api（用户流量）
kubectl apply -f k8s/chat-api/

# admin-api（内部管理）
kubectl apply -f k8s/admin-api/

# kf-embed（模型已烘焙进镜像，启动仅需加载进内存，数秒）
kubectl apply -f k8s/embed/

# Qdrant（1 副本 + ESSD）
kubectl apply -f k8s/qdrant/

# OSS CSI PVC（工作流配置挂载）
kubectl apply -f k8s/oss-pvc.yaml

# Ingress（ALB）
kubectl apply -f k8s/ingress.yaml
```

---

## 5. 验证部署

```bash
# 检查 Pod 状态
kubectl get pods -n mb-test

# 检查 Service
kubectl get svc -n mb-test

# 检查 Ingress
kubectl get ingress -n mb-test

# 健康检查
curl http://<DOMAIN>/health  # chat-api 健康
curl http://<DOMAIN>/status   # admin-api 状态
```

---

## 6. 凭证注入机制

### 6.1 双层注入架构

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
→ 注入全部 20 个 key           → 仅注入 EMBED_API_KEY
    │                                │
    ▼                                ▼
  Pod 环境变量 ←── os.environ
    │
    ├── config/_load_yaml() ──→ _resolve_env()
    │    将 YAML 中的 ${VAR:-default} 替换为环境变量值
    │    → LLMConfig, DBConfig, SessionConfig, EmbedConfig...
    │
    └── os.environ.get("VAR")  直接读取
         → factory.py, embed_service/app.py, logger
```

### 6.2 配置文件占位符解析

`src/config.py:422-434` 的 `_resolve_env()` 函数用正则匹配 YAML 中的 `${VAR}` / `${VAR:-default}` 占位符:

```
config/llm.yaml:    api_key: ${DEEPSEEK_API_KEY}           → os.environ["DEEPSEEK_API_KEY"]
config/db.yaml:     host: ${MYSQL_HOST:-127.0.0.1}        → os.environ["MYSQL_HOST"]
config/session.yaml: url: ${REDIS_URL:-redis://localhost}  → os.environ["REDIS_URL"]
config/embed.yaml:  api_key: ${EMBED_API_KEY:-}            → os.environ["EMBED_API_KEY"]
config/metrics.yaml: engine: ${KF_METRICS_ENGINE:-sqlite}  → "mysql"
```

### 6.3 各 Secret Key 消费链路

| Secret Key | 注入方式 | 消费位置 |
|---|---|---|
| `DEEPSEEK_API_KEY` | envFrom → `_resolve_env()` | `config/llm.yaml` (LLM 调用), `config/session.yaml` (会话摘要) |
| `KF_API_KEY` | envFrom → `_resolve_env()` | `config/auth.yaml` (API 鉴权, 当前被注释) |
| `EMBED_API_KEY` | envFrom + valueFrom | `config/embed.yaml` (chat/admin 调用 embed), `src/embed_service/app.py:40` (embed 服务自身鉴权) |
| `REDIS_URL` | envFrom → `_resolve_env()` | `config/session.yaml` → `src/session/redis_store.py:27` |
| `MYSQL_HOST/PORT/USER/PASSWORD/DB` | envFrom → `_resolve_env()` | `config/db.yaml` → `src/db.py` 连接池 |
| `KF_METRICS_DB_*` | envFrom → `_resolve_env()` / `os.environ.get()` | `config/db.yaml`, `config/metrics.yaml`, `src/metrics/factory.py:35-44` |
| `PG_HOST/PORT/USER/PASSWORD/DB` | envFrom → `_resolve_env()` | `config/db.yaml` → `src/db.py` 连接池 |
| `OSS_ACCESS_KEY_ID/SECRET/ENDPOINT` | envFrom (Jenkins) | **不在 Python 应用中使用**，仅 CI/CD 流水线用于 ossutil 上传 UI 静态文件 |
| `OSS_WORKFLOW_BUCKET/UI_BUCKET` | envFrom (Jenkins) | 同上 |

---

## 7. 占位符替换

部署前替换以下占位符（`kubectl apply` 前执行 `sed` 或编辑文件）：

| 占位符 | 出现位置 | 说明 | 示例 |
|---|---|---|---|
| `<NAMESPACE>` | 所有 k8s 资源 | K8s 命名空间 | `mb-test` |
| `<ACR_REGISTRY>` | Deployment image | ACR 镜像仓库地址 | `registry.cn-hangzhou.aliyuncs.com/team` |
| `<API_IMAGE_TAG>` | chat-api/admin-api Deployment | kf-api 镜像标签 | `v1.0.0` |
| `<EMBED_IMAGE_TAG>` | embed Deployment | kf-embed 镜像标签 | `v1.0.0` |
| `<DOMAIN>` | Ingress | ALB 对外域名 | `kf-test.example.com` |

---

## 8. 资源需求参考

| 组件 | requests | limits | 备注 |
|---|---|---|---|
| chat-api | 0.5 CPU / 512Mi | 2 CPU / 2Gi | 1 副本 |
| admin-api | 0.5 CPU / 512Mi | 2 CPU / 2Gi | 1 副本 |
| kf-embed | 0.2 CPU / 256Mi | 0.5 CPU / 512Mi | 模型已烘焙，不需 PVC |
| Qdrant | 1 CPU / 2Gi | 2 CPU / 4Gi | 1 副本 + ESSD |

---

## 9. 配置说明

| 资源 | 文件 | 说明 |
|---|---|---|
| 命名空间 | `k8s/namespace.yaml` | 应用隔离（mb-test / mb-pr） |
| 保密字典 | `k8s/secret.yaml` | **模板文件**，仅作结构参考 |
| chat-api | `k8s/chat-api/` | 用户流量（KF_MODE=chat） |
| admin-api | `k8s/admin-api/` | 内部管理（KF_MODE=admin） |
| kf-embed | `k8s/embed/` | FastEmbed 向量化微服务 |
| Qdrant | `k8s/qdrant/` | 1 副本 StatefulSet + ESSD |
| OSS PVC | `k8s/oss-pvc.yaml` | 工作流 YAML 配置挂载 |
| Ingress | `k8s/ingress.yaml` | 双后端 ALB Ingress |
