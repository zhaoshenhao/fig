# AGENTS.md — 项目决策记录

## 项目概述
多产品线智能客服（智能客服）系统。Python 3.14.5，FastAPI + Streamlit + Qdrant。

## 技术栈决策

### 运行时
- Python 3.14.5
- 所有 PyPI 依赖取最新稳定版

### 核心依赖（6项）
| 包 | 用途 |
|-----|------|
| fastapi | API 框架（自带 pydantic, uvicorn） |
| qdrant-client | 向量库客户端，prefer_grpc=True |
| httpx2 | HTTP 客户端，LLM + Embeddings 调用（含 Ollama） |
| pyyaml | 配置文件解析 |
| python-multipart | 文件上传 |
| streamlit | GUI |

### 禁止项
- 禁止使用 openai/anthropic 等 LLM 供应商 SDK → 统一 httpx2 REST API
- 禁止使用 sentence-transformers → Embeddings + Rerank 走本地 Ollama（httpx2）
- 禁止使用 watchfiles → 文件监控用轮询或手动触发
- 新增依赖必须手动确认

### Ollama
- 部署：独立 Docker（开发）或 K8s Deployment（生产），CPU 即可运行
- 嵌入模型：`nomic-embed-text`（768d，~500MB）
- Embedding API：`{OLLAMA_URL}/v1/embeddings`，OpenAI 兼容格式
- 零费用、零外网依赖、低延迟（30-80ms CPU）
- Rerank：不用 Ollama（无 `/api/rerank` 端点），改用 Qdrant RRF

### Qdrant
- 独立 Docker 服务，不嵌入应用
- 始终 gRPC（prefer_grpc=True）
- 开发：localhost:6334
- 生产：ACK StatefulSet 3副本 + ESSD 云盘
- 允许读写（非只读部署）
- 多 Worker 共享同一 Qdrant DB（SQLite WAL 支持并发读）
- 混合检索：Dense Vector (768d) + Sparse BM25，RRF 分数融合，不设独立 reranker

### 工作流引擎
- DAG 驱动（depends_on 字段）
- 每个产品线一个独立 workflow，独立 context_path 和 API key 列表
- 配置：workflow.yaml + 节点 yaml 目录
- 工具系统：llm, rag_search, db_query, api_call, web_search, code, router, merge

### 文档构建
- API 上传 + 目录扫描（均手动触发）
- 独立构建脚本，与应用分离

### Streamlit GUI
- 5-tab layout: 聊天 / 知识库浏览 / 工作流状态 / 文档管理 / 运行指标
- Global CSS: sticky title+tab bar, reduced font sizes, dark-mode compatible, mobile responsive
- Chat: scrollable messages area with sticky header and bottom input; JSON/CSV export
- Knowledge Browser: paginated browsing + semantic search + term highlighting
- Workflow Status: DAG topology visualization (clickable nodes with YAML config popover)
- Document Management: upload .txt/.md/.pdf/.docx/.csv/.xlsx (chunk_size 800 chars)
- Metrics Explorer: DAG-aware execution trace (non-traversed nodes grayed, click for details)
- Pure utilities in `src/gui/utils.py`: `_dag_levels`, `_highlight_term`, `_pretty_display_json`

### LLM 多供应商
- 通过 httpx2 REST API 直连各供应商
- API key 配置在 workflow 级 auth.yaml（固定 key 列表）

### 测试
- mock httpx2.Client（unittest.mock）
- tmp_path fixture 模拟 Qdrant 环境
- mock 工具函数测 workflow engine
- 不用 pytest-httpx（不兼容 httpx2）

### 生产部署
- ACK 托管版 K8s（阿里云容器服务）
- 已有现有 ACK 集群
- ALB Ingress
- Ollama: Deployment 1副本 + PVC（模型持久化）
- Qdrant: StatefulSet 3副本 + ESSD 云盘
- FastAPI: Deployment 2副本 + HPA
- Streamlit: Deployment 1副本
