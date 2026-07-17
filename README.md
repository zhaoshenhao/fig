# KF - 多产品线智能客服系统

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-teal.svg)](https://fastapi.tiangolo.com/)
[![Vue](https://img.shields.io/badge/Vue-3-4fc08d.svg)](https://vuejs.org/)
[![Qdrant](https://img.shields.io/badge/Qdrant-gRPC-orange.svg)](https://qdrant.tech/)

基于 FastAPI + Vue 3 + Qdrant 的多产品线智能客服系统。DAG 驱动的工作流引擎支持灵活编排，混合向量检索实现精准知识问答，多供应商 LLM 无缝切换。适用于企业级多业务线场景，支持独立工作流配置与完整观测体系。

[English](README_EN.md)

---

## 核心功能

- **多产品线工作流引擎** — DAG 驱动，每个产品线独立 workflow.yaml + nodes/\*.yaml 配置，支持节点依赖编排
- **10 种内置工具** — LLM 对话、RAG 检索、条件路由、数据库查询、API 调用、网页搜索、代码执行、参数合并等
- **混合向量检索** — Dense Vector (768d) + Sparse BM25，RRF 分数融合，无需独立 Reranker
- **多轮对话管理** — 内存 / Redis 双后端，会话自动压缩，长上下文窗口管理
- **实时流式输出** — SSE (Server-Sent Events) 逐 token 推送，低延迟交互体验
- **完整观测体系** — Prometheus 指标采集 + SQL / MySQL / PostgreSQL 三层执行追踪
- **多供应商 LLM 支持** — DeepSeek / OpenAI / Anthropic / Ollama / LMStudio，统一 httpx2 REST API 直连
- **独立向量化微服务** — kf-embed (FastEmbed / ONNX)，CPU 运行，零外网依赖

## 架构概览

```
  ┌──────────┐       ┌──────────┐        ┌──────────────────────────────┐
  │ Vue SPA  │─────▶│  FastAPI  │──────▶│       DAG Engine             │
  │(OSS/CDN) │       │ (chat /   │       │                              │
  └──────────┘       │  admin)   │       │  LLM ── RAG ── Router ── DB  │
                     └─────┬─────┘       │  API ── Code ── Merge ── ... │
                           │             └──────────────┬───────────────┘
                           │                            │
                     ┌─────┴────────────────────────────┴─────┐
                     │                                        │
                     ▼                                        ▼
               ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
               │ Session  │  │  Qdrant  │  │ kf-embed │  │ DB Pools │
               │ (Redis)  │  │ (gRPC)   │  │ (ONNX)   │  │(MySQL/PG)│
               └──────────┘  └──────────┘  └──────────┘  └──────────┘
```

## 快速开始

```bash
# 1. 克隆并配置环境
cp .env.example .env
# 编辑 .env 填入 DEEPSEEK_API_KEY

# 2. 启动服务 (docker-compose)
docker compose up --build

# 3. 或本地开发
pip install -e .[dev]
uvicorn src.api.main:app --port 9000
```

## 文档导航

| 文档 | 说明 |
|------|------|
| [架构设计](docs/architecture_CN.md) | 系统架构、模块关系、目录结构 |
| [API 参考](docs/reference/api-reference_CN.md) | 完整 HTTP API 文档 |
| [工作流指南](docs/design/workflow_CN.md) | 工作流设计、节点配置、路由规则 |
| [会话管理](docs/design/session_CN.md) | 多轮对话、存储后端、历史压缩 |
| [指标系统](docs/design/metrics_CN.md) | 执行追踪、Prometheus、仪表盘 |
| [工具参考](docs/reference/tools-reference_CN.md) | 10 种内置工具详解 + CLI 工具 |
| [数据库](docs/database/database_CN.md) | 连接池配置、Schema 规范、迁移 |
| [测试](docs/test/testing_CN.md) | 测试结构、运行方法、覆盖要求 |
| [本地开发](docs/deployments/local-setup_CN.md) | 环境搭建、Docker、配置说明 |
| [部署指南](docs/deployments/deployment_CN.md) | K8s 部署 (ACK + AWS EKS) |
| [手动测试](docs/test/manual-test_CN.md) | 功能验证测试计划 |

## 技术栈

- **运行时**: Python >=3.12, FastAPI, Vue 3 + Vite
- **向量检索**: Qdrant (gRPC), FastEmbed (ONNX)
- **外部存储**: MySQL / PostgreSQL / Redis (外部托管)
- **基础设施**: Docker, Kubernetes, Jenkins CI/CD

## 配置

YAML 配置驱动，支持 `${ENV_VAR}` 环境变量插值。

```
config/
└── workflows/
    └── <产品线>/
        ├── workflow.yaml
        └── nodes/
            └── *.yaml
```

每个产品线独立目录，包含 `workflow.yaml`（DAG 拓扑定义）和 `nodes/`（各节点配置），通过 `depends_on` 字段声明执行依赖。
