# kf-embed 嵌入服务配置与使用

## 概述

kf-embed 是基于 [FastEmbed](https://github.com/qdrant/fastembed)（Qdrant 官方 ONNX 推理库）
的轻量向量化微服务，替代独立 Ollama 容器承担 Embedding 职责。

- **推理引擎**：FastEmbed（ONNX Runtime，CPU 即可运行）
- **API 格式**：OpenAI 兼容 `/v1/embeddings`（端口 8100）
- **模型**：`nomic-ai/nomic-embed-text-v1.5`（768d，137M 参数）

## 架构位置

```
kf-api (FastAPI + Vue SPA)
    │
    ├── POST https://api.deepseek.com/v1/chat/completions   (LLM, 外部)
    ├── POST http://embed:8100/v1/embeddings                 (Embedding, kf-embed)
    ├── gRPC qdrant:6334 + Qdrant Search                     (向量库)
    ├── MySQL RDS / PostgreSQL RDS / Redis                    (外部托管)
    └── GET  /                                                (Vue SPA, 同进程)
```

## 快速开始

### 本地开发（进程直接启动）

```bash
# 1. 安装依赖（仅首次）
pip install -e .[embed]

# 2. 可选：预下载模型到本地缓存（启动首次自动下载，约 60 秒）
#    直接启动服务时会自动下载，以下为可选手动预热
python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='nomic-ai/nomic-embed-text-v1.5')"

# 3. 启动服务
FASTEMBED_CACHE_PATH=./.fastembed_cache \
EMBED_MODEL=nomic-ai/nomic-embed-text-v1.5 \
uvicorn src.embed_service.app:app --port 8100
```

### Docker 启动

```bash
# 构建镜像（模型在构建期预下载至 /opt/fastembed_cache，启动零下载）
docker build -t kf-embed -f Dockerfile.embed .
docker run -d --name kf-embed -p 8100:8100 kf-embed
```

### docker-compose（推荐）

```yaml
# docker-compose.yaml
embed:
  build:
    context: .
    dockerfile: Dockerfile.embed
  ports:
    - "8100:8100"
  environment:
    EMBED_MODEL: nomic-ai/nomic-embed-text-v1.5
    EMBED_WARMUP: "1"
```

## 环境变量

| 变量 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `EMBED_MODEL` | 否 | `nomic-ai/nomic-embed-text-v1.5` | FastEmbed 模型仓库名 |
| `EMBED_WARMUP` | 否 | `1` | 启动时预加载模型（`0` 懒加载） |
| `EMBED_API_KEY` | 否 | 空＝不鉴权 | 内部服务鉴权 Key |
| `FASTEMBED_CACHE_PATH` | 否 | 系统临时目录 | 模型缓存路径（构建期设 `/opt/fastembed_cache`） |

## API 端点

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| `GET` | `/health` | 跳过 | 存活探针，进程可用即 200 |
| `GET` | `/ready` | 跳过 | 就绪探针，模型加载完成返回 200 + `{"status":"ready","startup_seconds":1.27}` |
| `POST` | `/v1/embeddings` | Key 可选 | OpenAI 兼容向量化，见下方 |

### POST /v1/embeddings

**请求**：
```json
{
  "model": "nomic-embed-text",
  "input": "文本内容"           // 或 ["文本1", "文本2"]
}
```

模型名别名映射：`nomic-embed-text` → `nomic-ai/nomic-embed-text-v1.5`。

**响应**：
```json
{
  "object": "list",
  "data": [
    {"object": "embedding", "index": 0, "embedding": [0.01, -0.02, ...]}
  ],
  "model": "nomic-embed-text",
  "usage": {"prompt_tokens": 2, "total_tokens": 2}
}
```

**认证**：设置 `EMBED_API_KEY` 后，需附带以下请求头之一：
- `X-API-Key: <key>`
- `Authorization: Bearer <key>`

## 鉴权设计

```
EMBED_API_KEY 为空 → 放行全部请求（开发模式）
EMBED_API_KEY 设置 → /health、/ready 跳过（探针可无 Key 访问）
                     → /v1/embeddings 需 X-API-Key 或 Authorization: Bearer
```

生产环境建议为 kf-api 与 kf-embed 共享同一个 `EMBED_API_KEY`，
kf-api 侧通过 `config/embed.yaml` 的 `api_key: ${EMBED_API_KEY:-}` 自动附带。

## kf-api 对接

`config/embed.yaml` 默认配置：

```yaml
default: ollama
providers:
  ollama:
    type: openai
    base_url: ${EMBED_BASE_URL:-http://localhost:8100/v1}
    api_key: ${EMBED_API_KEY:-}
    model: ${EMBED_MODEL:-nomic-embed-text}
    dims: 768
```

kf-api 的 `LLMClient.embed()` 调用 `/v1/embeddings`，自动附带 `Authorization: Bearer <key>`，
无需代码改动。

## K8s 部署

镜像已烘焙模型于 `/opt/fastembed_cache`，无需 PVC。Deployment 1 副本 + ClusterIP Service（端口 8100）。

```yaml
env:
  - name: EMBED_MODEL
    value: "nomic-ai/nomic-embed-text-v1.5"
  - name: FASTEMBED_CACHE_PATH
    value: "/opt/fastembed_cache"
  - name: EMBED_API_KEY
    valueFrom:
      secretKeyRef:
        name: kf-secrets
        key: EMBED_API_KEY
```

资源需求参考：

| | requests | limits |
|---|---------|--------|
| CPU | 200m | 500m |
| 内存 | 256Mi | 512Mi |

## 模型烘焙机制

`Dockerfile.embed` 在 **RUN 阶段**预下载模型：

```dockerfile
ENV FASTEMBED_CACHE_PATH=/opt/fastembed_cache
ENV EMBED_MODEL=nomic-ai/nomic-embed-text-v1.5

RUN python -c "import os; from fastembed import TextEmbedding; \
    TextEmbedding(model_name=os.environ['EMBED_MODEL'])"
```

构建后镜像层包含完整模型文件，容器启动仅需将模型加载至内存（约 1 秒），
**无需联网、无需 PVC**。

## 启动耗时参考

| 环境 | 就绪时间 |
|------|---------|
| 本地进程（模型已缓存） | **~1.3s** |
| Docker（模型已烘焙） | **~1.5s** |
| K8s（模型已烘焙） | **~2s** |
| 冷启动（无缓存需联网） | **~60s**（不推荐，禁此路径） |

## 故障排查

| 现象 | 原因 | 解决 |
|------|------|------|
| `/ready` 返回 503 | 模型未加载 | 检查 `EMBED_WARMUP=1` 且无报错 |
| 返回空向量 | 输入为空或非字符串 | 检查请求 `input` 字段 |
| 401 Unauthorized | Key 不匹配或缺失 | 检查 `EMBED_API_KEY` 环境变量 |
| 启动极慢 | 首次下载模型 | 确保模型已烘焙进镜像或本地缓存 |
