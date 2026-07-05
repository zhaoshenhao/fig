# K8s 部署指南（阿里云 ACK 托管版）

## 前提条件

- 已有 ACK 托管版集群
- kubectl 已配置连接集群
- ALB Ingress Controller 已安装
- 镜像已推送至 ACR（阿里云容器镜像服务）

## 架构

```
Internet → ALB Ingress → [FastAPI Service] → Qdrant (StatefulSet + ESSD)
                        → [Streamlit GUI]   → Ollama (Deployment, embedding)
                        → [Build Job]       → Qdrant + Ollama
```

## 部署步骤

### 1. 创建命名空间

```bash
kubectl apply -f k8s/namespace.yaml
```

### 2. 配置 ConfigMap 和 Secret

编辑 `k8s/configmap.yaml` 中的 `<WORKFLOW_CONFIG>` 和 `k8s/secret.yaml` 中的 `<AUTH_CONFIG>`，然后：

```bash
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml
```

### 3. 部署 Ollama

```bash
kubectl apply -f k8s/ollama/
```

部署后拉取模型：

```bash
kubectl exec -n <NAMESPACE> deploy/ollama -- ollama pull nomic-embed-text
```

### 4. 部署 Qdrant

```bash
kubectl apply -k k8s/qdrant/
```

### 5. 部署 FastAPI

```bash
kubectl apply -k k8s/api/
```

### 6. 部署 Streamlit

```bash
kubectl apply -k k8s/streamlit/
```

### 7. 配置 Ingress

编辑 `k8s/ingress.yaml` 中的域名和证书，然后：

```bash
kubectl apply -f k8s/ingress.yaml
```

### 8. 文档构建 Job（按需手动触发）

```bash
kubectl apply -f k8s/job-build.yaml
```

## 一键部署

```bash
kubectl apply -k k8s/
```

## 配置说明

| 组件 | 文件 | 说明 |
|------|------|------|
| 命名空间 | k8s/namespace.yaml | 应用隔离 |
| 工作流配置 | k8s/configmap.yaml | workflow.yaml + 节点定义 |
| API Keys | k8s/secret.yaml | 各 workflow 的固定 key |
| Ollama | k8s/ollama/ | Deployment + PVC（模型持久化） |
| Qdrant | k8s/qdrant/ | StatefulSet 3副本 + ESSD |
| API | k8s/api/ | Deployment + HPA |
| GUI | k8s/streamlit/ | Streamlit Deployment |
| 入口 | k8s/ingress.yaml | ALB Ingress |

## 占位符替换

部署前替换以下占位符：

| 占位符 | 说明 | 示例 |
|--------|------|------|
| `<NAMESPACE>` | 命名空间 | `kf` |
| `<ACR_REGISTRY>` | 镜像仓库 | `registry.cn-hangzhou.aliyuncs.com/team` |
| `<API_IMAGE_TAG>` | API 镜像标签 | `v1.0.0` |
| `<STREAMLIT_IMAGE_TAG>` | GUI 镜像标签 | `v1.0.0` |
| `<DOMAIN>` | 对外域名 | `kf.example.com` |
| `<QDRANT_STORAGE_SIZE>` | Qdrant 磁盘 | `50Gi` |
