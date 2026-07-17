[中文](metrics-db-setup.md)

# Metrics Database Setup Guide

## Prerequisites

- MySQL 8.0+ or PostgreSQL 14+
- Character set `utf8mb4` (MySQL) / `UTF8` (PostgreSQL)
- Time zone set to UTC

---

## 1. Local Development (Docker)

### MySQL

```bash
docker run -d --name kf-mysql \
  -e MYSQL_ROOT_PASSWORD=kfpass \
  -e MYSQL_DATABASE=kf_metrics \
  -p 3307:3306 \
  mysql:8.0 --character-set-server=utf8mb4 --collation-server=utf8mb4_unicode_ci
```

### PostgreSQL

```bash
docker run -d --name kf-pg \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=kfpass \
  -e POSTGRES_DB=kf_metrics \
  -p 5433:5432 \
  postgres:16
```

---

## 2. Create Database and User

### Using the Init Script (Recommended)

```bash
# MySQL
DB_TYPE=mysql DB_ROOT_PASSWORD=your-root-password ./deployment/scripts/init-metrics-db.sh

# PostgreSQL
DB_TYPE=postgresql DB_ROOT_PASSWORD=your-root-password ./deployment/scripts/init-metrics-db.sh
```

The script handles: connection test → create DB → create app user → grant privileges → print credentials.

### Manual (Alternative)

**MySQL**:

```sql
CREATE DATABASE kf_metrics CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'kf'@'%' IDENTIFIED BY 'your-strong-password';
GRANT ALL PRIVILEGES ON kf_metrics.* TO 'kf'@'%';
FLUSH PRIVILEGES;
SET GLOBAL time_zone = '+00:00';
```

### PostgreSQL

```sql
CREATE DATABASE kf_metrics ENCODING 'UTF8';
CREATE USER kf WITH PASSWORD 'your-strong-password';
GRANT ALL PRIVILEGES ON DATABASE kf_metrics TO kf;
```

---

## 3. Configure Environment Variables

Copy and edit the `.env` file:

```bash
cp .env.example .env
```

Metrics-related variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `KF_METRICS_ENGINE` | Storage engine: `sqlite` / `mysql` / `postgresql` | `sqlite` |
| `KF_METRICS_DB_PATH` | SQLite file path | `data/metrics.db` |
| `KF_METRICS_DB_HOST` | DB host | `127.0.0.1` |
| `KF_METRICS_DB_PORT` | DB port | `3307` (MySQL) / `5433` (PG) |
| `KF_METRICS_DB_USER` | DB user | `root` |
| `KF_METRICS_DB_PASSWORD` | DB password | `kfpass` |
| `KF_METRICS_DB_NAME` | Database name | `kf_metrics` |

---

## 4. Automatic Table Creation

On startup, `src/metrics/migration.py` runs automatically to:

1. Check the current version in `_schema_version`
2. For each pending migration:
   - Compare actual vs. expected columns; backup old table if drift detected
   - Execute DDL (CREATE TABLE, ALTER TABLE, etc.)
   - Create indexes
3. Record the migration version

**No manual DDL execution is required.**

---

## 5. Migrating from SQLite to MySQL/PostgreSQL

One-time script to move local SQLite data to production:

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
```

> Full script: see `../design/metrics_EN.md`.

---

## 6. K8s Deployment (No Root Password)

A dedicated K8s Job `deployment/k8s-aliyun/init-db-job.yaml` handles DB initialization:

```
kubectl create secret generic kf-db-root-secret \
  --from-literal=DB_ROOT_USER=root \
  --from-literal=DB_ROOT_PASSWORD=<root-password>

kubectl apply -f deployment/k8s-aliyun/init-db-job.yaml      # Run once
kubectl delete secret kf-db-root-secret    # Can delete after
```

The Job uses root credentials to create the DB and app user. App Deployments only use app credentials from `kf-secrets`.

---

## 7. Schema Tables

| Table | Purpose |
|-------|---------|
| `runs` | Execution record per chat turn |
| `node_logs` | Execution record per DAG node |
| `tool_logs` | Tool invocation within a node |
| `feedback` | User 👍/👎 feedback |
| `session_meta` | Session metadata (title, tags) |
| `rag_retrievals` | RAG retrieval records |
| `_schema_version` | Migration version tracker (auto-managed) |

Full column definitions: `src/metrics/schema.py`.
