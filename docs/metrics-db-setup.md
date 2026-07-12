# Metrics 存储引擎安装配置指南

Metrics 执行追踪存储支持三种引擎，通过配置切换。**默认 SQLite**，生产当前也使用 SQLite。

- 三层结构：`runs` → `node_logs` → `tool_logs`
- 引擎选择：`config/metrics.yaml` 或环境变量
- 抽象实现：`src/metrics/store.py`(SQLite) + `src/metrics/sql_store.py`(MySQL/PG) + `src/metrics/factory.py`

---

## 本地快速验证（WSL Docker，已验证）

```bash
# WSL 内启动 MySQL + PostgreSQL
docker run -d --name kf-mysql -e MYSQL_ROOT_PASSWORD=kfpass \
    -e MYSQL_DATABASE=kf_metrics -p 3307:3306 mysql:8
docker run -d --name kf-pg -e POSTGRES_PASSWORD=kfpass \
    -e POSTGRES_DB=kf_metrics -p 5433:5432 postgres:16
```

`config/db.yaml` 已内置 `mysql_main`(3307) / `pg_analytics`(5433) / `metrics` 三个连接池，
默认指向上述 WSL 容器（密码 `kfpass`，可用环境变量覆盖）。切换 metrics 引擎：

```bash
# 用 MySQL 存储 metrics
$env:KF_METRICS_ENGINE="mysql"    # PowerShell；或 export KF_METRICS_ENGINE=mysql
python -m uvicorn src.api.main:app --port 9000
```

集成测试（DB 不可达时自动 skip）：

```bash
python -m pytest tests/test_db_integration.py -v
```

> 表结构在应用/Store 初始化时自动创建（`CREATE TABLE IF NOT EXISTS`），
> 无需手动建表；下面的手动 SQL 仅供生产参考。

## 引擎选择
`config/metrics.yaml`：

```yaml
engine: ${KF_METRICS_ENGINE:-sqlite}   # sqlite | mysql | postgresql
path: data/metrics.db                  # sqlite 专用
pool: metrics                          # mysql/pg 使用的 db 连接池名
retention_days: 0                      # 0=不限制
```

环境变量覆盖（优先级最高）：

| 变量 | 说明 | 默认 |
|------|------|------|
| `KF_METRICS_ENGINE` | `sqlite` / `mysql` / `postgresql` | `sqlite` |
| `KF_METRICS_DB_PATH` | SQLite 文件路径 | `data/metrics.db` |
| `KF_METRICS_POOL` | MySQL/PG 连接池名 | `metrics` |

> ⚠️ 切换引擎不会自动迁移历史数据；如需保留，请用下方迁移脚本。

---

## SQLite（默认）

无需额外配置。首次启动自动建表 + 建索引；旧 schema 会被**非破坏性重命名备份**（`*_backup_<时间戳>`），不会丢数据。

```yaml
engine: sqlite
path: data/metrics.db
```

---

## MySQL

### 1. 建库建用户

```sql
CREATE DATABASE kf_metrics CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'kf'@'%' IDENTIFIED BY 'your-strong-password';
GRANT ALL PRIVILEGES ON kf_metrics.* TO 'kf'@'%';
FLUSH PRIVILEGES;
```

- 字符集必须 `utf8mb4`（支持中文与 emoji）
- 时区建议统一 UTC：`SET GLOBAL time_zone = '+00:00';`

### 2. 配置连接池 `config/db.yaml`

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

### 3. 启用

```yaml
# config/metrics.yaml
engine: mysql
pool: metrics
```

表结构由应用启动时自动创建（`CREATE TABLE IF NOT EXISTS`）。依赖：`PyMySQL`。

---

## PostgreSQL

### 1. 建库建用户

```sql
CREATE DATABASE kf_metrics ENCODING 'UTF8';
CREATE USER kf WITH PASSWORD 'your-strong-password';
GRANT ALL PRIVILEGES ON DATABASE kf_metrics TO kf;
```

- `created_at` 使用文本 UTC 时间（`now() at time zone 'utc'`），与 SQLite 一致，保证跨引擎时间过滤行为一致
- 自增主键使用 `BIGSERIAL`

### 2. 配置连接池 `config/db.yaml`

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

### 3. 启用

```yaml
# config/metrics.yaml
engine: postgresql
pool: metrics
```

依赖：`psycopg2-binary`。

---

## SQL 方言差异（自动处理）

`src/metrics/dialect.py` 封装了各引擎差异，业务代码无需关心：

| 维度 | SQLite | MySQL | PostgreSQL |
|------|--------|-------|------------|
| 自增主键 | `INTEGER PRIMARY KEY AUTOINCREMENT` | `BIGINT AUTO_INCREMENT` | `BIGSERIAL` |
| 占位符 | `?` | `%s` | `%s` |
| 时间默认 | `datetime('now')` | `CURRENT_TIMESTAMP` | `now() at time zone 'utc'` |
| 插入返回 ID | `lastrowid` | `lastrowid` | `RETURNING id` |
| 去重聚合 | `GROUP_CONCAT` | `GROUP_CONCAT` | `string_agg` |

---

## 从 SQLite 迁移历史数据（可选）

一次性迁移脚本示例（Python）：

```python
import sqlite3
from src.metrics.factory import create_metrics_store

src = sqlite3.connect("data/metrics.db")
src.row_factory = sqlite3.Row
dst = create_metrics_store({"engine": "mysql", "pool": "metrics"})

for run in src.execute("SELECT * FROM runs ORDER BY id"):
    rid = dst.insert_run(
        run["chat_id"], run["turn_id"], run["workflow_name"],
        query=run["query"] or "", reply=run["reply"] or "",
        node_count=run["node_count"], duration_ms=run["duration_ms"],
        status=run["status"], error_message=run["error_message"],
    )
    # node_logs / tool_logs 需按 run_id 映射后迁移（略）
```

> 生产迁移前请在预发环境验证；建议低峰期执行并先备份。

---

## 数据保留

- 接口：`POST /metrics/retention?days=N` 删除 N 天前的记录
- 或程序内调用 `metrics_store.delete_older_than("YYYY-MM-DD HH:MM:SS")`
- 建议用 K8s CronJob 定期调用（如每日保留 90 天）
