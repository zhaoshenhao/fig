[English](metrics-db-setup_EN.md)

# Metrics 数据库初始化指南

## 环境要求

- MySQL 8.0+ 或 PostgreSQL 14+
- 字符集 `utf8mb4`（MySQL）/ `UTF8`（PostgreSQL）
- 时区统一为 UTC

---

## 1. 本地开发（Docker）

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

## 2. 创建数据库和用户

### 使用初始化脚本（推荐）

```bash
# MySQL
DB_TYPE=mysql DB_ROOT_PASSWORD=your-root-password ./scripts/init-metrics-db.sh

# PostgreSQL
DB_TYPE=postgresql DB_ROOT_PASSWORD=your-root-password ./scripts/init-metrics-db.sh
```

脚本自动完成：连接测试 → 建库 → 建应用用户 → 授权 → 打印凭据。

### 手动执行（备选）

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

## 3. 配置环境变量

复制并编辑 `.env` 文件：

```bash
cp .env.example .env
```

Metrics 相关变量：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `KF_METRICS_ENGINE` | `sqlite` / `mysql` / `postgresql` | `sqlite` |
| `KF_METRICS_DB_PATH` | SQLite 文件路径 | `data/metrics.db` |
| `KF_METRICS_DB_HOST` | DB 主机 | `127.0.0.1` |
| `KF_METRICS_DB_PORT` | DB 端口 | `3307` (MySQL) / `5433` (PG) |
| `KF_METRICS_DB_USER` | DB 用户 | `root` |
| `KF_METRICS_DB_PASSWORD` | DB 密码 | `kfpass` |
| `KF_METRICS_DB_NAME` | 数据库名 | `kf_metrics` |

---

## 4. 表结构自动创建

应用启动时，`src/metrics/migration.py` 会自动执行：

1. 检查 `_schema_version` 表当前版本
2. 对每个未执行的迁移：
   - 对比实际列与期望列，如有漂移则备份旧表
   - 执行 DDL（CREATE TABLE、ALTER TABLE 等）
   - 创建索引
3. 记录迁移版本

**无需手动执行任何 SQL DDL 语句。**

---

## 5. 从 SQLite 迁移到 MySQL/PostgreSQL

**一次性操作**，用于将本地 SQLite 数据迁移到生产数据库：

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
    # 按 run_id 映射迁移 node_logs / tool_logs / feedback
```

> 完整脚本参见 `docs/metrics_CN.md` 第 430-449 行。

---

## 6. K8s 部署（不需要 root 密码）

K8s 环境下有专门的 `k8s/init-db-job.yaml`（一次性 Job）：

```
kubectl create secret generic kf-db-root-secret \
  --from-literal=DB_ROOT_USER=root \
  --from-literal=DB_ROOT_PASSWORD=<root密码>

kubectl apply -f k8s/init-db-job.yaml      # 只执行一次
kubectl delete secret kf-db-root-secret    # 之后可以删除
```

Job 用 root 密码建库 + 建应用用户，app Deployment 只用应用用户凭据（来自 `kf-secrets`）。

---

## 7. Schema 表结构

| 表 | 用途 |
|---|------|
| `runs` | 每次对话回合的执行记录 |
| `node_logs` | DAG 中每个节点的执行记录 |
| `tool_logs` | 节点内每个工具的调用记录 |
| `feedback` | 用户 👍/👎 反馈 |
| `session_meta` | 会话元数据（标题、标签） |
| `rag_retrievals` | RAG 检索记录 |
| `_schema_version` | 迁移版本追踪（自动管理） |

完整列定义见 `src/metrics/schema.py`。
