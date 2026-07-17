# Metrics Execution Tracing Storage

[中文](metrics_CN.md)

## 1. Overview

Three-layer execution tracing storage for training data collection and performance analysis:

```
runs (per conversation turn)
  └── node_logs (per node execution)
        └── tool_logs (per tool call)
```

- **runs**: One record per conversation turn (`session × turn`)
- **node_logs**: One record per node execution within a turn
- **tool_logs**: One record per tool invocation within a node

Supporting tables: `feedback` (user feedback), `session_meta` (session metadata), `rag_retrievals` (RAG retrieval records), `_schema_version` (migration tracker).

## 2. Storage Engines

Three database engine options, switchable via configuration. **SQLite is the default** and currently used in production.

| Engine | Config Key | Driver | Use Case |
|--------|-----------|--------|----------|
| SQLite | `sqlite` | built-in (`sqlite3`) | Development, single instance |
| MySQL | `mysql` | PyMySQL | Production (ACK RDS) |
| PostgreSQL | `postgresql` | psycopg2 | Production (ACK RDS) |

**Configuration**: `config/metrics.yaml` or environment variables.

```yaml
# config/metrics.yaml
engine: ${KF_METRICS_ENGINE:-sqlite}   # sqlite | mysql | postgresql
path: data/metrics.db                  # SQLite only
pool: metrics                          # Connection pool name for MySQL/PG (maps to config/db.yaml)
retention_days: 0                      # 0 = unlimited
```

Environment variable overrides (highest priority):

| Variable | Description | Default |
|------|------|------|
| `KF_METRICS_ENGINE` | `sqlite` / `mysql` / `postgresql` | `sqlite` |
| `KF_METRICS_DB_PATH` | SQLite file path | `data/metrics.db` |
| `KF_METRICS_POOL` | MySQL/PG connection pool name | `metrics` |

> Switching engines does not auto-migrate historical data. Use the migration script if preservation is needed (see sample at end of this doc).

**SQL Dialect Differences** (handled automatically by `src/metrics/dialect.py`):

| Dimension | SQLite | MySQL | PostgreSQL |
|------|--------|-------|------------|
| Auto-increment PK | `INTEGER PRIMARY KEY AUTOINCREMENT` | `BIGINT AUTO_INCREMENT` | `BIGSERIAL` |
| Placeholder | `?` | `%s` | `%s` |
| Timestamp default | `datetime('now')` | `CURRENT_TIMESTAMP` | `now() at time zone 'utc'` |
| Insert returning ID | `lastrowid` | `lastrowid` | `RETURNING id` |
| Dedup aggregation | `GROUP_CONCAT` | `GROUP_CONCAT` | `string_agg` |

**Local Verification** (WSL Docker):

```bash
docker run -d --name kf-mysql -e MYSQL_ROOT_PASSWORD=kfpass \
    -e MYSQL_DATABASE=kf_metrics -p 3307:3306 mysql:8
docker run -d --name kf-pg -e POSTGRES_PASSWORD=kfpass \
    -e POSTGRES_DB=kf_metrics -p 5433:5432 postgres:16

# Switch to MySQL
export KF_METRICS_ENGINE=mysql
uvicorn src.api.main:app --port 9000
```

## 3. Table Schemas

### runs — Run Records

One record per conversation turn.

| Column | Type | Description |
|------|------|------|
| `id` | INTEGER PK | Auto-increment primary key |
| `chat_id` | TEXT NOT NULL | Session ID |
| `turn_id` | INTEGER NOT NULL | Turn number |
| `workflow_name` | TEXT NOT NULL | Workflow name |
| `query` | TEXT | User input |
| `reply` | TEXT | System reply |
| `node_count` | INTEGER DEFAULT 0 | Number of nodes executed |
| `duration_ms` | REAL | Total duration (milliseconds) |
| `status` | TEXT DEFAULT 'ok' | `ok` / `error` |
| `error_message` | TEXT | Error details |
| `prompt_tokens` | INTEGER DEFAULT 0 | LLM prompt tokens |
| `completion_tokens` | INTEGER DEFAULT 0 | LLM completion tokens |
| `created_at` | TEXT | Creation timestamp |

Indexes:
- `idx_runs_chat` (`chat_id`, `turn_id`)
- `idx_runs_workflow` (`workflow_name`, `created_at`)

### node_logs — Node Logs

One record per node execution.

| Column | Type | Description |
|------|------|------|
| `id` | INTEGER PK | Auto-increment primary key |
| `run_id` | INTEGER FK → runs.id | References the run |
| `chat_id` | TEXT NOT NULL | Session ID |
| `turn_id` | INTEGER NOT NULL | Turn number |
| `node_name` | TEXT NOT NULL | Node name (e.g. `retrieve`, `generate`, `input`, `output`) |
| `tool_name` | TEXT DEFAULT '' | Tool type (e.g. `llm`, `rag_search`, `router`) |
| `input_data` | TEXT | Node input (YAML config as JSON) |
| `output_text` | TEXT | Node output text |
| `duration_ms` | REAL | Execution duration (milliseconds) |
| `status` | TEXT DEFAULT 'ok' | `ok` / `error` |
| `error_message` | TEXT | Error details |
| `created_at` | TEXT | Creation timestamp |

Indexes:
- `idx_node_logs_run` (`run_id`)
- `idx_node_logs_chat` (`chat_id`, `turn_id`)

### tool_logs — Tool Call Logs

One record per tool invocation.

| Column | Type | Description |
|------|------|------|
| `id` | INTEGER PK | Auto-increment primary key |
| `node_log_id` | INTEGER FK → node_logs.id | References the node log |
| `run_id` | INTEGER FK → runs.id | References the run |
| `chat_id` | TEXT NOT NULL | Session ID |
| `turn_id` | INTEGER NOT NULL | Turn number |
| `node_name` | TEXT NOT NULL | Parent node name |
| `tool_name` | TEXT NOT NULL | Tool name |
| `input_params` | TEXT | Tool input (JSON) |
| `output_result` | TEXT | Tool output (JSON) |
| `duration_ms` | REAL | Tool execution duration (milliseconds) |
| `status` | TEXT DEFAULT 'ok' | `ok` / `error` |
| `error_message` | TEXT | Error details |
| `created_at` | TEXT | Creation timestamp |

Indexes:
- `idx_tool_logs_node` (`node_log_id`)
- `idx_tool_logs_run` (`run_id`)

### Supporting Tables

| Table | Purpose | Key Columns |
|------|------|------|
| `feedback` | User feedback | `chat_id`, `turn_id`, `rating`, `comment`, `correction` |
| `session_meta` | Session metadata | `chat_id` (PK), `title`, `tags`, `updated_at` |
| `rag_retrievals` | RAG retrieval records | `run_id`, `collection`, `score`, `source`, `chunk_preview` (truncated to 500 chars) |
| `_schema_version` | Migration version tracker | `version` (PK), `applied_at`, `description` |

Tables are auto-created on application startup (`CREATE TABLE IF NOT EXISTS`); no manual DDL is required.

## 4. Schema Management

### Canonical Sources

- **Schema definition**: `src/metrics/schema.py` — `TABLE_COLUMNS` dictionary + `all_table_ddl()` function
- **Versioned migrations**: `src/metrics/migration.py` — `Migration` dataclass + `MIGRATIONS` list
- **Auto-executed on startup**: `migrate(conn, dialect)` applies pending migrations in version order

### Migration Process

1. Read current version from `_schema_version` table
2. For each pending migration:
   - Compare actual table columns against expected column set (`table_columns`)
   - If mismatch: **rename old table to `<table>_backup_<YYYYMMDD_HHMMSS>`** (non-destructive backup, no data loss)
   - Drop old indexes, execute new DDL statements
   - Execute migration-specific DDL (`ALTER TABLE`, etc.)
   - Create indexes
3. Record the applied migration version in `_schema_version`

### How to Add a Migration

1. Add columns to `TABLE_COLUMNS` in `src/metrics/schema.py`
2. Add columns to the corresponding `CREATE TABLE` statement in `all_table_ddl()`
3. Append a `Migration` dataclass to the `MIGRATIONS` list in `src/metrics/migration.py` with an incremented version
4. Include `ALTER TABLE` DDL in the migration's `ddl_sql`
5. For new indexes, add corresponding statements in `index_sql`
6. Run the test suite to verify migration correctness on both fresh and version-upgraded databases

**Principle**: Never commit a migration that drops data without an explicit backup step.

## 5. API Endpoints

### Endpoint Summary

| Method | Path | Description |
|------|------|------|
| GET | `/api/v1/sessions` | List/search sessions with filtering, sorting, pagination |
| GET | `/api/v1/sessions/{chat_id}` | All turns for a session |
| GET | `/api/v1/sessions/{chat_id}/turns/{turn_id}` | All nodes for a turn |
| GET | `/api/v1/sessions/{chat_id}/turns/{turn_id}/nodes/{node_name}` | All tool calls for a node |
| GET | `/api/v1/metrics/summary` | Dashboard aggregate data |
| GET | `/api/v1/metrics/timeseries?workflow=X` | Per-minute time series |
| POST | `/api/v1/metrics/retention?days=N` | Data retention cleanup |
| GET | `/api/v1/export/training.jsonl` | Export training samples (JSONL) |
| POST | `/api/v1/export/chat.xlsx` | Export chat records (Excel) |
| POST | `/api/v1/export/chat.csv` | Export chat records (CSV) |

### GET /api/v1/sessions Query Parameters

All parameters are optional and can be combined arbitrarily. Text-type filters use substring matching (`LIKE %value%`).

| Parameter | Type | Description |
|------|------|------|
| `limit` | int | Per page (default 50) |
| `offset` | int | Offset (default 0) |
| `time_from` | str | Start time `YYYY-MM-DD HH:MM:SS` (`runs.created_at >=`) |
| `time_to` | str | End time (`runs.created_at <=`) |
| `workflow` | str | Filter by workflow name (`runs.workflow_name`) |
| `node` | str | Filter by node name (matches `node_logs.node_name`, via subquery) |
| `tool` | str | Filter by tool name (matches `node_logs.tool_name`, via subquery) |
| `input_text` | str | Filter node input text (matches `node_logs.input_data`) |
| `output_text` | str | Filter node output text (matches `node_logs.output_text`) |
| `duration_min` | float | Min total duration (ms) |
| `duration_max` | float | Max total duration (ms) |
| `sort_by` | str | Sort field: `last_at`(default) / `first_at` / `duration_ms` / `turn_count` / `chat_id` |
| `sort_dir` | str | `desc`(default) / `asc` |

`node` / `tool` / `input_text` / `output_text` are implemented via `runs.id IN (SELECT run_id FROM node_logs WHERE ...)` subqueries and can be used alone or combined with other conditions.

Response format: `{"sessions": [...], "total": <int>}`, where `total` is the deduplicated session count (for pagination).

### Request Examples

```bash
# List sessions
curl http://localhost:9000/api/v1/sessions

# Filter by workflow + tool
curl "http://localhost:9000/api/v1/sessions?workflow=auto_film&tool=rag_search"

# Search by node output text, sort by ascending duration
curl "http://localhost:9000/api/v1/sessions?output_text=window+tint&sort_by=duration_ms&sort_dir=asc"

# View all turns for a session
curl http://localhost:9000/api/v1/sessions/chat_abc123

# View node details for a turn
curl http://localhost:9000/api/v1/sessions/chat_abc123/turns/0

# View tool calls for a node
curl http://localhost:9000/api/v1/sessions/chat_abc123/turns/0/nodes/retrieve
```

### GET /api/v1/metrics/summary Response Structure

Global overview + per-workflow breakdown + node/tool granularity.

**Global overview**:
- `total_requests`: Total number of requests
- `total_sessions`: Total number of sessions
- `error_rate`: Global error rate
- `avg_ms` / `p50_ms` / `p95_ms` / `p99_ms`: Average / P50 / P95 / P99 latency
- `total_prompt_tokens` / `total_completion_tokens`: Token totals

**Per-workflow** (`workflows` array, sorted by request count descending):
- Each workflow contains: `requests`, `sessions`, `error_rate`, `avg_ms`, `p95_ms`, `total_tokens`
- `wf_nodes`: Per-workflow per-node: `calls`, `avg_ms`, `p95_ms`, `error_rate`
- `wf_tools`: Per-workflow per-tool: `calls`, `avg_ms`, `p95_ms`, `error_rate`

### GET /api/v1/metrics/timeseries Response Structure

Per-minute bucketed time series data; requires the `workflow` parameter.

- Each bucket: `active_sessions`, `requests`, `avg_ms`, `p95_ms`
- Per-node breakdown (`nodes` array): requests / avg latency / P95 per node
- Per-tool breakdown (`tools` array): calls / avg latency / P95 per tool

### POST /api/v1/metrics/retention

Delete records older than N days (`days` query parameter). Also callable programmatically via `metrics_store.delete_older_than("YYYY-MM-DD HH:MM:SS")`. Recommended: K8s CronJob for periodic execution (e.g., daily, retain 90 days).

## 6. Prometheus Metrics

Prometheus metrics exposed on the `/metrics` endpoint:

| Metric | Type | Labels | Description |
|------|------|------|------|
| `http_requests_total` | Counter | `method`, `path`, `status` | HTTP request count |
| `http_request_duration_seconds` | Histogram | `method`, `path` | HTTP latency distribution |
| `llm_calls_total` | Counter | `model` | LLM call count |
| `rag_search_duration_ms` | Histogram | — | RAG retrieval latency distribution |
| `node_executions_total` | Counter | `node`, `tool`, `status` | Node execution count |
| `node_duration_ms` | Histogram | `node`, `tool` | Node latency distribution |
| `tool_calls_total` | Counter | `tool`, `status` | Tool call count |
| `workflow_runs_total` | Counter | `workflow`, `status` | Workflow run count |

- Grafana dashboard: `deployment/k8s-aliyun/grafana-dashboard.json`
- Alert rules: `deployment/k8s-aliyun/prometheus-rules.yaml` (includes node/tool error rate and P95 latency alerts)
- OpenTelemetry: Ingestible via OTel Collector's Prometheus receiver scraping the `/metrics` endpoint

## 7. RAG Retrieval Tracking

`rag_search` results are stored via `insert_rag_retrieval()` into the `rag_retrievals` table:

- Parameters: `run_id`, `chat_id`, `turn_id`, `collection`, `score`, `source`, `chunk_preview`
- `chunk_preview` is truncated to 500 characters
- Automatically invoked during RAG search node execution in `src/engine/dag.py`

Query: `query_rag_for_turn(run_id)` returns all retrieval results for a turn, ordered by score descending.

## 8. Data Export

| Endpoint | Description |
|------|------|
| `GET /api/v1/export/training.jsonl` | Export query → reply pairs as JSONL for fine-tuning |
| `POST /api/v1/export/chat.xlsx` | Export chat records as Excel |
| `POST /api/v1/export/chat.csv` | Export chat records as CSV |

Export buttons are located on the Vue SPA "Chat History" page.

## 9. Vue SPA Dashboard

Two independent sidebar menu pages:

### Chat History (`MetricsPage.vue`)

- **Search/Filter Panel**: Supports all query parameters (time range, workflow, node, tool, input/output text, duration range), collapsible
- **Session List**: One row per session with turn count, total duration, time range; column-header click sorting and prev/next pagination
- **DAG Execution Trace Modal**: Opens on session row click; organizes nodes by workflow DAG topology:
  - ✅ Executed nodes (green) — click to show input/output/tool call details
  - ⚪ Unexecuted nodes (gray) — shows node name and router type label (if-then / switch)
  - Arrows connect layers to show node dependencies
  - Fallback: When workflow config is unavailable, degrades to an expanded node list

### Dashboard (`DashboardPage.vue`)

Two tabs:

- **Overview** — Data source: `/api/v1/metrics/summary`:
  - Global overview cards row: total requests / sessions / error rate / avg / P50 / P95 / P99 / tokens
  - Per-workflow blocks (sorted by request count descending), each containing:
    - Workflow metrics: total requests, total sessions, error rate, avg latency, P95 latency, total tokens
    - Node detail table (per node: requests / avg / P95 / error rate)
    - Tool detail table (per tool: requests / avg / P95 / error rate)

- **Charts** — Data source: `/api/v1/metrics/timeseries`:
  - Select workflow + time range (presets/custom)
  - SVG line charts (zero-dependency `LineChart.vue`): active sessions, requests per minute, avg/P95 latency
  - Per-node and per-tool multi-line charts for request volume / avg latency / P95

## 10. Configuration Reference

### config/metrics.yaml

```yaml
# Metrics storage engine configuration
# engine: sqlite | mysql | postgresql (default sqlite, currently sqlite in production)
# Environment variables override: KF_METRICS_ENGINE / KF_METRICS_DB_PATH / KF_METRICS_POOL
#
# Before switching to mysql / postgresql, configure the connection pool in config/db.yaml
# and create the database per the setup guide.

engine: ${KF_METRICS_ENGINE:-sqlite}

# SQLite only
path: data/metrics.db

# Connection pool name for MySQL / PostgreSQL (maps to pools key in config/db.yaml)
pool: metrics

# Data retention: records older than this many days can be cleaned by maintenance jobs; 0 = unlimited
retention_days: 0
```

### config/db.yaml (MySQL pool example)

```yaml
pools:
  metrics:
    driver: mysql
    host: ${MYSQL_HOST:-127.0.0.1}
    port: 3306
    user: kf
    password: ${MYSQL_PASSWORD}
    database: kf_metrics
    pool_size: 5
```

### config/db.yaml (PostgreSQL pool example)

```yaml
pools:
  metrics:
    driver: postgresql
    host: ${PG_HOST:-127.0.0.1}
    port: 5432
    user: kf
    password: ${PG_PASSWORD}
    database: kf_metrics
    pool_size: 5
```

### Environment Variables

| Variable | Description | Default |
|------|------|------|
| `KF_METRICS_ENGINE` | Storage engine type | `sqlite` |
| `KF_METRICS_DB_PATH` | SQLite file path | `data/metrics.db` |
| `KF_METRICS_POOL` | Connection pool name | `metrics` |

### Production Database Initialization

**MySQL** (charset must be `utf8mb4`):

```sql
CREATE DATABASE kf_metrics CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'kf'@'%' IDENTIFIED BY 'your-strong-password';
GRANT ALL PRIVILEGES ON kf_metrics.* TO 'kf'@'%';
FLUSH PRIVILEGES;
SET GLOBAL time_zone = '+00:00';
```

**PostgreSQL**:

```sql
CREATE DATABASE kf_metrics ENCODING 'UTF8';
CREATE USER kf WITH PASSWORD 'your-strong-password';
GRANT ALL PRIVILEGES ON DATABASE kf_metrics TO kf;
```

Table schemas are auto-created on application startup; no manual DDL execution is needed.

### Migrating Historical Data from SQLite

One-time migration script example:

```python
import sqlite3
from src.metrics.factory import create_metrics_store

src = sqlite3.connect("data/metrics.db")
src.row_factory = sqlite3.Row
dst = create_metrics_store({"engine": "mysql", "pool": "metrics"})

for run in src.execute("SELECT * FROM runs ORDER BY id"):
    dst.insert_run(
        run["chat_id"], run["turn_id"], run["workflow_name"],
        query=run["query"] or "", reply=run["reply"] or "",
        node_count=run["node_count"], duration_ms=run["duration_ms"],
        status=run["status"], error_message=run["error_message"],
    )
    # node_logs / tool_logs need run_id mapping before migration
```

> Validate in staging before production migration; execute during off-peak hours and back up first.
