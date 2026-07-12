# 本地开发环境搭建

## 前置依赖

| 工具 | 版本 | 说明 |
|------|------|------|
| Python | >=3.12 | 项目运行时 |
| Node.js | >=20 | 构建 Vue SPA |
| Docker | latest | 运行 Qdrant + kf-embed |

## 项目结构

```
kf/
├── src/                  # Python 源码
│   ├── api/              # FastAPI 应用（含 Vue SPA 静态挂载）
│   ├── embed_service/    # kf-embed 向量化微服务（FastEmbed）
│   ├── engine/           # DAG 引擎 + Tool 系统
│   ├── rag/              # Qdrant 混合检索
│   ├── llm/              # LLM 客户端
│   ├── gui/ui/           # Vue 3 + Vite SPA
│   └── ingestion/        # 文档构建
├── config/               # 配置文件
├── data/                 # 本地数据
├── tests/                # 测试
├── k8s/                  # K8s 部署清单
└── docs/                 # 文档
```

## 快速启动

### 方式 A：docker-compose（推荐）

一键起 Qdrant + kf-embed + kf-api：

```bash
docker compose up --build
```

### 方式 B：本地逐个启动

#### 1. 启动 Qdrant

```bash
docker run -d --name kf-qdrant \
  -p 6333:6333 -p 6334:6334 \
  -v qdrant_data:/qdrant/storage \
  qdrant/qdrant
```

#### 2. 启动 kf-embed（向量化微服务）

```bash
docker build -t kf-embed -f Dockerfile.embed .
docker run -d --name kf-embed \
  -p 8100:8100 \
  kf-embed
```

模型（`nomic-ai/nomic-embed-text-v1.5`）已在构建期烘焙进镜像，启动无需下载，`GET /ready` 返回 200 即就绪。

或本地进程直接运行（需先 `pip install -e .[embed]`）：

```bash
uvicorn src.embed_service.app:app --port 8100
```

#### 3. 配置环境变量

复制 `.env.example` 为 `.env`，填入 `DEEPSEEK_API_KEY`；确认 embed / Qdrant 地址：

```
EMBED_BASE_URL=http://localhost:8100/v1
EMBED_MODEL=nomic-embed-text
QDRANT_HOST=localhost
QDRANT_PORT=6334
```

#### 4. 创建虚拟环境并安装依赖

```bash
python -m venv .venv
.venv\Scripts\activate     # Windows
pip install -e .[dev]
```

#### 5. 构建 Vue SPA

```bash
cd src/gui/ui && npm install && npm run build
```

#### 6. 启动 API（同时提供 REST API + SPA）

```bash
uvicorn src.api.main:app --reload --port 8000
```

前端开发热更新（可选）：`cd src/gui/ui && npm run dev`（Vite 代理 API 到 8000）。

## 架构

```
localhost:8100          ←  kf-embed (Docker, FastEmbed 向量化)
localhost:6334 (gRPC)   ←  Qdrant (Docker)
localhost:6333 (HTTP)   ←  Qdrant (Docker, REST API)
localhost:8000          ←  FastAPI (uvicorn, REST API + Vue SPA)
外部                     ←  DeepSeek API (LLM)
```

## 停止

```bash
docker stop kf-embed kf-qdrant && docker rm kf-embed kf-qdrant
# 或 docker compose down
# Ctrl+C 关闭 uvicorn
```
