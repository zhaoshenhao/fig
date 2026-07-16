[中文](architecture_CN.md)

# KF Intelligent Customer Service System — Architecture Document

## System Architecture

The system follows a six-layer architecture, decoupling concerns from user interface to infrastructure.

### Layer 1 — Presentation

| Component | Tech Stack | Deployment | Status |
|-----------|-----------|------------|--------|
| Vue 3 SPA | Vue 3 + Vite + dagre.js | Alibaba Cloud OSS + CDN | Primary |
| Streamlit Debug GUI | Streamlit (`src/gui/app.py`) | Local dev only | Legacy (replaced) |

The Vue SPA uses Vite dev proxy to forward `/api/v1` → local FastAPI (port 9000). In production, traffic is routed via ALB Ingress.

### Layer 2 — API Gateway

Application entry point: `src/api/main.py`, FastAPI app factory pattern.

**Dual-mode deployment via `KF_MODE`**:
- `KF_MODE=chat`: loads user-facing routes (`routes_chat.py`)
- `KF_MODE=admin`: loads admin management routes (`routes_admin.py`)
- `KF_MODE=full` (default): loads both route groups

**Middleware stack** (in registration order):
```
CharsetMiddleware → CORS → RequestID → Metrics → Auth (X-API-Key)
```

**Endpoint inventory**:

| Endpoint | Method | Route Group | Description |
|----------|--------|-------------|-------------|
| `/health` | GET | Always available | Liveness probe, returns startup duration |
| `/ready` | GET | Always available | Readiness probe, checks Qdrant / Embedding / DB connectivity |
| `/status` | GET | Always available | Component status overview (LLM / Embedding / DB / Qdrant / Metrics) |
| `/metrics` | GET | Always available | Prometheus metrics export (text/plain) |
| `/reload` | POST | Always available | Hot-reload config without process restart |
| `/api/v1/workflows/{name}/run` | POST | chat | Workflow execution (primary entry point) |
| `/api/v1/sessions/*` | GET/DELETE/PATCH | chat | Session management CRUD |
| `/api/v1/sessions` | GET | admin | Admin session search (multi-condition filtering) |
| `/collections/*` | GET/POST/PUT/DELETE | admin | Qdrant collection management |
| `/documents/*` | POST/PUT/DELETE | admin | Document upload and management |
| `/export/*` | GET | chat | Conversation export |

**Exception handling**: global `Exception` catch → unified JSON 500 response with `request_id` for distributed tracing.

**Config reload gate**: returns 503 + `Retry-After: 1` for all other requests while `/reload` is in progress.

### Layer 3 — Workflow Engine

Location: `src/engine/`

**DAGEngine** (`dag.py`):
- BFS topology traversal via `deque`
- Conditional branching: `next_type=if-then`, selects successor path based on node output
- Parallel branches: `next_type=switch`, `ThreadPoolExecutor` executes branches concurrently, `merge` tool aggregates results
- Session state tracking: `session.nodes` records input/output of all executed nodes for downstream reference
- Metrics collection: auto-invokes `_collect_metrics` after each execution for full execution trace

**ToolRegistry** (`tool.py`):
- Pluggable tool system, key-value store (name → function)
- Unified tool signature: `fn(config: dict, session: SessionData) -> dict`

**10 built-in tools**:

| Tool | File | Function |
|------|------|----------|
| `llm` | `llm_tool.py` | LLM chat generation (supports system / user / assistant message templates) |
| `rag_search` | `rag_search.py` | Knowledge base retrieval (hybrid dense + BM25, RRF fusion) |
| `router` | `router.py` | Conditional routing (exact / regex / contains matching, intent mapping) |
| `merge` | `merge.py` | Parallel branch result merging |
| `db_query` | `db_query.py` | SQL query (LLM generates SQL → execute → LLM summarizes) |
| `extract_llm` | `extract_llm.py` | LLM-powered structured information extraction |
| `extract_regex` | `extract_regex.py` | Regex-based information extraction |
| `api_call` | `api_call.py` | External API proxy invocation |
| `web_search` | `web_search.py` | Web search engine integration |
| `code` | `code_exec.py` | Sandboxed Python code execution |

### Layer 4 — Domain Services

**Session Management** (`src/session/`):

| Module | Responsibility |
|--------|---------------|
| `data.py` | `SessionData` (dataclass, dict-like protocol) + `TurnRecord` + `trim_or_compress` two-phase strategy |
| `base.py` | `SessionStore` abstract base class |
| `memory.py` | `MemorySessionStore` (dict storage, dev/single-node, TTL cleanup thread) |
| `redis_store.py` | `RedisSessionStore` (Redis shared storage, multi-worker, production) |

Trim/compress strategy: TTL-based expiry trimming + LLM summary compression, keeping session context within token window limits.

**LLM Client** (`src/llm/client.py`):
- `LLMClient` class, built on `httpx2.Client`, OpenAI-compatible API
- Supports `chat` (synchronous) and `stream_chat` (SSE streaming) modes
- Supports OpenAI and Anthropic provider types behind a unified interface

**RAG Retrieval** (`src/rag/qdrant.py`):
- `QdrantSearch` facade class, wrapping Qdrant gRPC client (`prefer_grpc=True`, port 6334)
- Hybrid search: Dense Vector (768d Cosine) + Sparse BM25 + RRF score fusion
- Automatic fallback: degrades to pure vector search on hybrid failure
- Collection management: `ensure_collection`, `upsert`, `scroll`, `count`

### Layer 5 — Data & Storage

**DB Connection Pools** (`src/db/`):
- `base.py`: `DBConfig` / `DBPoolConfig` models, `DBPool` abstract base class
- `mysql_pool.py`: MySQL connection pool (pymysql)
- `pg_pool.py`: PostgreSQL connection pool (psycopg2)
- Config-driven: `config/db.yaml` defines pools, referenced by name

**Metrics Storage** (`src/metrics/`):

Three-layer execution trace hierarchy:
```
runs (conversation turns) → node_logs (node executions) → tool_logs (tool invocations)
```

| Module | Responsibility |
|--------|---------------|
| `schema.py` | Table DDL specification (canonical source of truth) |
| `migration.py` | Versioned migrations (`Migration` dataclass + `MIGRATIONS` list, auto-run on startup) |
| `dialect.py` | Multi-database SQL dialect adaptation (SQLite / MySQL / PostgreSQL) |
| `store.py` | `MetricsStore` (SQLite implementation, dev) |
| `sql_store.py` | `SQLMetricsStore` (MySQL/PostgreSQL production implementation) |
| `factory.py` | `create_metrics_store()` factory function |
| `prometheus.py` | Prometheus metrics export (Counter / Histogram / Gauge) |

**External Storage**:
- **Qdrant**: external Docker container, gRPC port 6334, Dense 768d + Sparse BM25 dual index
- **kf-embed**: standalone FastEmbed/ONNX microservice (`src/embed_service/app.py`), port 8100, OpenAI-compatible `/v1/embeddings`

### Layer 6 — Infrastructure

**Local Development** (`docker-compose.yaml`):
```
embed (8100) + qdrant (6333/6334) + api (8000)
```

**Kubernetes Production Deployment**:

| Resource | Type | Description |
|----------|------|-------------|
| chat-api | Deployment | User traffic, `KF_MODE=chat` |
| admin-api | Deployment | Internal management, `KF_MODE=admin` |
| kf-embed | Deployment | FastEmbed ONNX embeddings (1 replica, model baked into image) |
| Qdrant | StatefulSet | Vector database (EBS/ESSD persistent storage) |

Same Docker image (`Dockerfile`) builds both chat-api and admin-api, differentiated by `KF_MODE` environment variable.

**External Managed Services**:
- DeepSeek API: LLM inference
- Redis: shared session storage (multi-worker consistency)
- MySQL RDS: primary metrics database
- PostgreSQL RDS: analytics database
- Alibaba Cloud OSS: configuration files (CSI PVC mount) + SPA static files (CDN delivery)

---

## Directory Structure

```
kf/
├── config/                          # YAML configuration files
│   ├── auth.yaml                    # API keys + auth skip paths
│   ├── db.yaml                      # DB connection pool configuration
│   ├── embed.yaml                   # Embedding provider configuration
│   ├── gui.yaml                     # Streamlit GUI configuration
│   ├── llm.yaml                     # LLM provider configuration
│   ├── logging.yaml                 # Log level configuration
│   ├── metrics.yaml                 # Metrics storage configuration
│   ├── pricing.yaml                 # Pricing configuration
│   ├── qdrant.yaml                  # Qdrant connection configuration
│   ├── session.yaml                 # Session management configuration
│   └── workflows/                   # Workflow definitions
│       ├── auto_film/               # Auto film product workflow
│       │   ├── workflow.yaml        # DAG topology definition
│       │   └── nodes/               # Node YAML configurations
│       ├── customer_service/        # Customer service product workflow
│       └── default/                 # Default workflow
├── src/                             # Source code
│   ├── api/                         # FastAPI application layer
│   │   ├── main.py                  # App factory, lifecycle, route registration
│   │   ├── state.py                 # Singleton getters/setters (global state management)
│   │   ├── auth.py                  # X-API-Key authentication middleware
│   │   ├── routes_chat.py           # User-facing routes (workflows / sessions)
│   │   └── routes_admin.py          # Admin routes (metrics / collections / documents)
│   ├── cli/                         # CLI command-line tools
│   │   ├── build.py                 # Document ingestion CLI
│   │   ├── manage.py                # Knowledge base management CLI
│   │   └── validate_workflow.py     # Workflow validator
│   ├── config.py                    # Config loader (AppConfig singleton, YAML + ${ENV_VAR} interpolation)
│   ├── db/                          # Database connection pools
│   │   ├── base.py                  # DBConfig / DBPoolConfig / DBPool abstract base
│   │   ├── mysql_pool.py            # MySQLPool (pymysql)
│   │   └── pg_pool.py               # PgPool (psycopg2)
│   ├── embed_service/               # kf-embed vectorization microservice
│   │   ├── app.py                   # FastAPI application (port 8100)
│   │   └── service.py               # Embedding service logic (FastEmbed wrapper)
│   ├── engine/                      # DAG workflow engine
│   │   ├── dag.py                   # DAGEngine (topology traversal, parallel branches, metrics collection)
│   │   ├── tool.py                  # ToolRegistry (pluggable tool registry)
│   │   └── tools/                   # Built-in tools
│   │       ├── _template.py         # Tool development template
│   │       ├── llm_tool.py          # LLM chat generation
│   │       ├── rag_search.py        # Knowledge base retrieval (RAG)
│   │       ├── router.py            # Conditional routing (exact / regex / contains)
│   │       ├── merge.py             # Parallel branch result merging
│   │       ├── db_query.py          # Database query (LLM SQL generation + execution)
│   │       ├── extract_llm.py       # LLM structured extraction
│   │       ├── extract_regex.py     # Regex extraction
│   │       ├── api_call.py          # External API proxy invocation
│   │       ├── web_search.py        # Web search engine integration
│   │       └── code_exec.py         # Sandboxed code execution
│   ├── gui/                         # Streamlit debug GUI (legacy)
│   │   ├── app.py                   # Streamlit main entry
│   │   ├── ui/                      # Vue 3 + Vite SPA source
│   │   └── utils.py                 # GUI utility functions
│   ├── ingestion/                   # Document ingestion pipeline
│   │   ├── chunker.py               # Text chunker
│   │   └── builder.py               # Document builder (chunk → embed → upsert to Qdrant)
│   ├── llm/                         # LLM client
│   │   └── client.py                # Unified REST API client (chat + embed, httpx2)
│   ├── logger/                      # Structured logging
│   │   ├── __init__.py              # JSONFormatter + init_logging (per-module level config)
│   │   └── middleware.py            # RequestID injection middleware
│   ├── metrics/                     # Observability
│   │   ├── schema.py                # Table schema specification (canonical DDL source)
│   │   ├── migration.py             # Versioned database migrations (auto-run on startup)
│   │   ├── dialect.py               # Multi-database SQL dialect adaptation
│   │   ├── store.py                 # MetricsStore (SQLite implementation, dev)
│   │   ├── sql_store.py             # SQLMetricsStore (MySQL/PG production implementation)
│   │   ├── factory.py               # create_metrics_store() factory function
│   │   └── prometheus.py            # Prometheus metrics export (Counter / Histogram / Gauge)
│   ├── rag/                         # Vector retrieval engine
│   │   └── qdrant.py                # QdrantSearch (hybrid search, pagination, collection management)
│   └── session/                     # Session management
│       ├── base.py                  # SessionStore abstract base class
│       ├── data.py                  # SessionData + TurnRecord + trim_or_compress
│       ├── memory.py                # MemorySessionStore (dict storage, TTL cleanup thread)
│       └── redis_store.py           # RedisSessionStore (production shared storage)
├── tests/                           # Test suite
│   ├── conftest.py                  # Shared fixtures (tmp_path, mock httpx2, etc.)
│   ├── test_api.py                  # API endpoint tests
│   ├── test_auth.py                 # Auth middleware tests
│   ├── test_builder.py              # Document builder tests
│   ├── test_chunker.py              # Text chunker tests
│   ├── test_cli.py                  # CLI tool tests
│   ├── test_config.py               # Config loading tests
│   ├── test_coverage_edge.py        # Edge case and coverage tests
│   ├── test_dag_engine.py           # DAG engine tests
│   ├── test_db_integration.py       # Database integration tests
│   ├── test_db.py                   # DB connection pool tests
│   ├── test_embed_service.py        # Embedding service tests
│   ├── test_gui.py                  # GUI component tests
│   ├── test_llm_client.py           # LLM client tests
│   ├── test_metrics.py              # Metrics storage tests
│   ├── test_qdrant.py               # Qdrant retrieval tests
│   ├── test_session_store.py        # Session store tests
│   ├── test_tool_impl.py            # Tool implementation tests
│   ├── test_tool_impl_extra.py      # Tool implementation supplementary tests
│   └── test_tools.py                # Tool system tests
├── k8s/                             # Kubernetes deployment manifests
│   ├── namespace.yaml               # Namespace definition
│   ├── secret.yaml                  # Secret template (placeholder values)
│   ├── ingress.yaml                 # ALB Ingress configuration
│   ├── kustomization.yaml           # Kustomize orchestration
│   ├── oss-pvc.yaml                 # OSS CSI PersistentVolumeClaim
│   ├── job-build.yaml               # Document build Job
│   ├── grafana-dashboard.json       # Grafana monitoring dashboard
│   ├── prometheus-rules.yaml        # Prometheus alerting rules
│   ├── chat-api/                    # User traffic Deployment
│   ├── admin-api/                   # Admin management Deployment
│   ├── embed/                       # Embedding service Deployment
│   └── qdrant/                      # Qdrant StatefulSet
├── scripts/                         # Operations scripts
├── docker-compose.yaml              # Local dev orchestration (embed + qdrant + api)
├── Dockerfile                       # API image (shared by chat-api / admin-api)
├── Dockerfile.embed                 # kf-embed vectorization service image
├── pyproject.toml                   # Project metadata and tool configuration
└── Jenkinsfile                      # CI/CD pipeline
```

---

## Data Flow

Complete data flow path from user input to response:

```
User Input → POST /api/v1/workflows/{name}/run
  │
  ├─ 1. SessionStore.get_or_create(chat_id) → SessionData
  │      └─ MemorySessionStore (dev) / RedisSessionStore (production)
  │
  ├─ 2. DAGEngine.run(workflow_name, query, session)
  │      │
  │      ├─ 2a. Topology traversal (BFS + deque)
  │      │      ├─ Regular node: sequential tool_fn(node_config, session) → {text, ...}
  │      │      ├─ if-then branch: select successor path based on previous node output
  │      │      └─ switch parallel branch: ThreadPoolExecutor concurrent execution
  │      │
  │      ├─ 2b. Branch merging (merge tool): combine parallel branch results into unified output
  │      │
  │      ├─ 2c. _finish: reach output node, generate final reply
  │      │
  │      └─ 2d. _collect_metrics: collect complete execution trace
  │             ├─ runs (session × turn) record
  │             ├─ node_logs (node input/output/latency/error) records
  │             ├─ tool_logs (tool invocation details) records
  │             └─ Prometheus Counter / Histogram updates
  │
  ├─ 3. session.add_turn(query, reply) → trim_or_compress
  │      ├─ TTL trim: remove turn records exceeding max_age
  │      └─ Capacity compress: LLM summarize old conversations when exceeding max_turns
  │
  ├─ 4. SessionStore.save(session) → persist
  │
  └─ 5. JSONResponse { chat_id, turn_id, reply }
```

**Inter-node data passing in DAG**:
- Each node stores its output in `session.nodes[node_name].data` after execution
- Downstream nodes access upstream output via `session["node_name"]`
- Template engine supports `{{session.node_name.field}}` variable interpolation

---

## Key Design Decisions

### 1. YAML-Driven Config with Environment Variable Interpolation

All configuration is unified as YAML files (`config/*.yaml`), supporting `${ENV_VAR}` and `${ENV_VAR:-default}` interpolation syntax. Shared across process via `AppConfig` singleton, with runtime `/reload` hot-reload support.

### 2. Workflow Isolation

Each product line has an independent config directory (`config/workflows/{name}/`) containing:
- `workflow.yaml`: DAG topology definition
- `nodes/`: per-node tool type, parameters, and prompt configurations
- Independent KB lists, API key lists, and routing rules

Workflows are completely isolated, naturally supporting multi-tenancy.

### 3. Unified Tool Signature

All tool functions follow the `fn(config: dict, session: SessionData) -> dict` signature. `config` is the YAML node configuration dict, `session` is the current session object (dict-like interface, upstream output accessible via `session["node_name"]`). Return `dict` is uniformly `{"text": "...", ...}` format.

### 4. No Vendor SDK Lock-In

All LLM calls go through `httpx2` REST API — no dependency on openai / anthropic SDKs. `LLMClient` abstracts provider differences (OpenAI-compatible vs Anthropic) behind a unified `chat` / `stream_chat` interface. Switching LLM providers requires no business code changes.

### 5. Embedding as Independent Microservice

kf-embed is deployed as a standalone container (`Dockerfile.embed`), powered by FastEmbed/ONNX, using `nomic-embed-text` model (768d). Exposes `/v1/embeddings` OpenAI-compatible endpoint for kf-api consumption. Independently scalable, avoids competing with LLM inference resources.

### 6. Dual-Mode Session Storage

Development uses `MemorySessionStore` (dict storage + TTL cleanup thread), production uses `RedisSessionStore` (Redis shared storage, multi-worker consistency). `trim_or_compress` automatically maintains session context within token window limits.

### 7. Three-Level Metrics Tracing

```
runs (conversation turns)
  └─ node_logs (node execution details)
       └─ tool_logs (tool invocation details)
```

Supports SQLite (dev) / MySQL (production) / PostgreSQL (analytics) storage backends, with `dialect.py` adapting multi-database SQL dialects. Simultaneously exports Prometheus metrics for Grafana visualization.

### 8. Single Image, Dual Deployment

chat-api and admin-api use the same image built from a single `Dockerfile`, differentiated by the `KF_MODE` environment variable for route group selection. Reduces image build and maintenance overhead while ensuring version consistency.
