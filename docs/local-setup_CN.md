# 本地开发环境搭建

[English](local-setup_EN.md)

## 1. 前置依赖

| 工具 | 版本 | 用途 |
|------|------|------|
| Python | >=3.12 | 项目运行时 |
| Node.js | >=20 | 构建 Vue SPA |
| Docker | latest | 运行 Qdrant + kf-embed |

## 2. 快速启动（docker-compose）

```bash
docker compose up --build
```

一键启动以下服务：

| 服务 | 端口 | 协议 |
|------|------|------|
| Qdrant | 6334 | gRPC |
| kf-embed | 8100 | HTTP |
| kf-api | 8000 | HTTP |

## 3. 手动搭建

### 3.1 克隆项目 & 环境配置

```bash
git clone <repo-url>
cd kf
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY
```

### 3.2 启动 Qdrant

```bash
docker run -d --name kf-qdrant \
  -p 6333:6333 -p 6334:6334 \
  -v qdrant_data:/qdrant/storage \
  qdrant/qdrant
```

> 6333 = HTTP REST API，6334 = gRPC（SDK 使用 gRPC）。

### 3.3 启动 kf-embed（向量化微服务）

kf-embed 是基于 [FastEmbed](https://github.com/qdrant/fastembed)（Qdrant 官方 ONNX 推理库）的轻量向量化微服务。推理引擎为 ONNX Runtime，CPU 即可运行。API 格式兼容 OpenAI `/v1/embeddings`。

**Docker 启动（推荐，模型已烘焙进镜像，零下载）：**

```bash
docker build -t kf-embed -f Dockerfile.embed .
docker run -d --name kf-embed -p 8100:8100 kf-embed
```

**或本地进程启动：**

```bash
pip install -e .[embed]
uvicorn src.embed_service.app:app --port 8100
```

> 模型 `nomic-ai/nomic-embed-text-v1.5`（768d，137M 参数）已在 Docker 构建期预下载至 `/opt/fastembed_cache`。`GET /ready` 返回 200 即模型加载完成。

### 3.4 Python 环境

```bash
python -m venv .venv
.venv\Scripts\activate     # Windows
# source .venv/bin/activate  # Linux/macOS
pip install -e .[dev]
```

### 3.5 配置环境变量（.env）

```
DEEPSEEK_API_KEY=sk-xxx
EMBED_BASE_URL=http://localhost:8100/v1
EMBED_MODEL=nomic-embed-text
QDRANT_HOST=localhost
QDRANT_PORT=6334
```

### 3.6 构建 Vue SPA

```bash
cd src/gui/ui
npm install
npm run build
```

### 3.7 启动 API

```bash
uvicorn src.api.main:app --reload --port 9000
```

API 同时提供 REST API（`/api/v1/*`）和 Vue SPA 静态文件（`/`）。

## 4. 本地架构

```
localhost:8100          ← kf-embed（Docker，FastEmbed ONNX 推理）
localhost:6334 (gRPC)   ← Qdrant（Docker）
localhost:6333 (HTTP)   ← Qdrant（REST API）
localhost:9000          ← FastAPI（REST API + Vue SPA 静态文件）
外部                     ← DeepSeek API（LLM）
```

## 5. 开发工作流

**API 热重载：**`uvicorn --reload` 在代码变更时自动重启。

**前端开发热更新：**

```bash
cd src/gui/ui && npm run dev
# Vite dev server 自动代理 /api/v1 → localhost:9000
```

**运行测试：**

```bash
pytest
pytest -k "dag" -v
```

**代码检查：**

```bash
ruff check .
```

**文档构建（入库）：**

```bash
python -m src.cli.build --dir data/documents --collection default
```

**验证工作流配置：**

```bash
python -m src.cli.validate_workflow config/workflows/auto_film/
```

## 6. kf-embed 服务详情

### 6.1 环境变量

| 变量 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `EMBED_MODEL` | 否 | `nomic-ai/nomic-embed-text-v1.5` | FastEmbed 模型名 |
| `EMBED_WARMUP` | 否 | `1` | 启动时预加载模型（`0` 为懒加载） |
| `EMBED_API_KEY` | 否 | 空=不鉴权 | 内部服务鉴权 Key |
| `FASTEMBED_CACHE_PATH` | 否 | 系统临时目录 | 模型缓存路径 |

### 6.2 API 端点

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| `GET` | `/health` | 跳过 | 存活探针 |
| `GET` | `/ready` | 跳过 | 就绪探针（模型加载完成后返回 200） |
| `POST` | `/v1/embeddings` | Key 可选 | OpenAI 兼容向量化接口 |

**鉴权逻辑：**

- `EMBED_API_KEY` 为空 → 放行全部请求（开发模式）
- `EMBED_API_KEY` 已设置 → `/health`、`/ready` 跳过鉴权；`/v1/embeddings` 需附带 `X-API-Key: <key>` 或 `Authorization: Bearer <key>`

### 6.3 Embedding 请求/响应

**请求：**

```json
{"model": "nomic-embed-text", "input": "要向量化的文本"}
```

> 模型别名映射：`nomic-embed-text` → `nomic-ai/nomic-embed-text-v1.5`。<br>
> `input` 支持单个字符串或字符串数组。

**响应：**

```json
{
  "object": "list",
  "data": [{"object": "embedding", "index": 0, "embedding": [0.01, -0.02, ...]}],
  "model": "nomic-embed-text",
  "usage": {"prompt_tokens": 2, "total_tokens": 2}
}
```

### 6.4 启动耗时

| 环境 | 就绪时间 |
|------|---------|
| 本地进程（模型已缓存） | ~1.3s |
| Docker（模型已烘焙） | ~1.5s |
| 冷启动（需下载模型） | ~60s（不推荐，请烘焙进镜像） |

### 6.5 故障排查

| 现象 | 原因 | 解决 |
|------|------|------|
| `/ready` 返回 503 | 模型未加载 | 检查 `EMBED_WARMUP=1` 且无启动报错 |
| 返回空向量 | 输入为空 | 检查请求 `input` 字段 |
| 401 Unauthorized | Key 不匹配或缺失 | 检查 `EMBED_API_KEY` 环境变量 |
| 启动极慢 | 首次下载模型 | 确保模型已烘焙进镜像或本地缓存 |

## 7. 停止服务

```bash
docker stop kf-embed kf-qdrant && docker rm kf-embed kf-qdrant
# 或：docker compose down
# Ctrl+C 关闭 uvicorn
```

## 8. 可选：Vue SPA 独立开发

Vue 3 + Vite SPA 位于 `src/gui/ui/`。仅前端开发时：

```bash
cd src/gui/ui
npm run dev      # 开发服务器（HMR），API 请求代理到 localhost:9000
npm run build    # 生产构建 → dist/
```
