# KF - Multi-Product Intelligent Customer Service

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-teal.svg)](https://fastapi.tiangolo.com)
[![Vue 3](https://img.shields.io/badge/Vue-3.x-green.svg)](https://vuejs.org)
[![Qdrant](https://img.shields.io/badge/Qdrant-gRPC-orange.svg)](https://qdrant.tech)

KF is a multi-product intelligent customer service system powered by a DAG-driven workflow engine. It supports hybrid vector search, multi-turn conversation management with session compression, and multi-vendor LLM integration — all delivered through a Vue 3 SPA with real-time SSE streaming.

[中文](README.md)

## Core Features

- **Multi-product DAG-driven workflow engine** — each product line has an independent workflow with isolated context and API keys
- **10 built-in tools** — LLM, RAG search, conditional routing, DB query, API calls, web search, code execution, router, merge, and more
- **Hybrid vector search** — Dense (768d) + Sparse BM25 with RRF fusion, no standalone reranker needed
- **Multi-turn conversation management** — memory-backed sessions with Redis, automatic context compression
- **Real-time streaming output** — Server-Sent Events (SSE) for token-by-token streaming
- **Full observability** — Prometheus metrics + 3-layer execution tracing (SQLite/MySQL/PostgreSQL)
- **Multi-vendor LLM support** — DeepSeek, OpenAI, Anthropic, Ollama, LMStudio via unified httpx2 REST API
- **Standalone embedding microservice** — FastEmbed + ONNX runtime, CPU-only, zero external API cost

## Architecture Overview

```
                    Vue 3 SPA
                       │
                  SSE Streaming
                       │
                  FastAPI Server
                       │
               DAG Workflow Engine
                       │
         ┌─────────────┼─────────────┐
         │             │             │
      Tools         Session       Qdrant
   ┌───┴───┐       Manager       (gRPC)
   │       │         │              │
  LLM    RAG       Redis       kf-embed
   │       │       (multi-     (FastEmbed/
   │       │        worker)     ONNX)
   │       │
 Router   DB/API
```

## Quick Start

```bash
# 1. Clone and configure
cp .env.example .env
# Edit .env and fill in DEEPSEEK_API_KEY

# 2. Start services (docker-compose)
docker compose up --build

# 3. Or local development
pip install -e .[dev]
uvicorn src.api.main:app --port 9000
```

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture](docs/architecture_EN.md) | System architecture, modules, directory structure |
| [API Reference](docs/reference/api-reference_EN.md) | Complete HTTP API documentation |
| [Workflow Guide](docs/design/workflow_EN.md) | Workflow design, node config, routing rules |
| [Session Management](docs/design/session_EN.md) | Multi-turn dialog, storage backends, history compression |
| [Metrics](docs/design/metrics_EN.md) | Execution tracing, Prometheus, dashboards |
| [Tools Reference](docs/reference/tools-reference_EN.md) | 10 built-in tools + CLI tools |
| [Database](docs/database/database_EN.md) | Connection pools, schema norms, migrations |
| [Testing](docs/test/testing_EN.md) | Test structure, running tests, coverage requirements |
| [Local Setup](docs/deployments/local-setup_EN.md) | Environment setup, Docker, configuration |
| [Deployment](docs/deployments/deployment_EN.md) | K8s deployment (ACK + AWS EKS) |
| [Manual Test](docs/test/manual-test_EN.md) | Feature verification test plan |

## Tech Stack

- **Python >=3.12**, **FastAPI**, **Vue 3 + Vite**
- **Qdrant** (gRPC), **FastEmbed** (ONNX)
- **MySQL / PostgreSQL / Redis** (externally hosted)
- **Docker**, **Kubernetes**, **Jenkins CI/CD**

## Configuration

- YAML-driven config with `${ENV_VAR}` interpolation
- Workflow config: `config/workflows/<product>/workflow.yaml` + `nodes/*.yaml`
