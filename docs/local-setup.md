# 本地开发环境搭建

## 前置依赖

| 工具 | 版本 | 说明 |
|------|------|------|
| Python | >=3.12 | 项目运行时 |
| Docker | latest | 运行 Qdrant + Ollama 独立服务 |

## 项目结构

```
kf/
├── src/             # Python 源码
│   ├── api/         # FastAPI 应用
│   ├── engine/      # DAG 引擎 + Tool 系统
│   ├── rag/         # Qdrant 混合检索
│   ├── llm/         # LLM 客户端
│   ├── gui/         # Streamlit GUI
│   └── ingestion/   # 文档构建
├── config/          # 配置文件
│   ├── workflow.yaml
│   ├── auth.yaml
│   └── workflows/   # 节点配置目录
├── data/            # 本地数据
├── tests/           # 测试
├── k8s/             # K8s 部署清单
└── docs/            # 文档
```

## 快速启动

### 1. 启动 Qdrant

```bash
docker run -d --name kf-qdrant \
  -p 6333:6333 -p 6334:6334 \
  -v qdrant_data:/qdrant/storage \
  qdrant/qdrant
```

### 2. 启动 Ollama + 拉取模型

```bash
docker run -d --name kf-ollama \
  -p 11434:11434 \
  -v ollama_models:/root/.ollama \
  ollama/ollama

ollama pull nomic-embed-text
```

### 3. 配置

编辑 `config/workflow.yaml` 和 `config/auth.yaml`，按需创建 `config/workflows/` 下的节点配置。
确保 `auth.yaml` 中配置了 Ollama 的 `base_url: http://localhost:11434/v1`。

### 4. 创建虚拟环境

```bash
python -m venv .venv
.venv\Scripts\activate     # Windows
# source .venv/bin/activate   # Linux/macOS
```

### 5. 安装依赖

```bash
pip install -e .
```

### 6. 启动 API

```bash
uvicorn src.api.main:app --reload --port 8000
```

### 7. 启动 Streamlit

```bash
streamlit run src/gui/app.py --server.port 8501
```

## 架构

```
localhost:11434         ←  Ollama (Docker, embedding + LLM)
localhost:6334 (gRPC)   ←  Qdrant (Docker)
localhost:6333 (HTTP)   ←  Qdrant (Docker, REST API)
localhost:8000           ←  FastAPI (uvicorn)
localhost:8501           ←  Streamlit (GUI)
```

## 停止

```bash
docker stop kf-ollama kf-qdrant && docker rm kf-ollama kf-qdrant
# Ctrl+C 关闭 uvicorn 和 streamlit
```
