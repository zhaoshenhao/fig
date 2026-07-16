[English](database_EN.md)

# 数据库配置与 Schema 管理

## 1. 概述

智能客服系统涉及两类独立的数据库：

1. **业务数据库**（`config/db.yaml`）：工作流工具（`db_query` 工具）使用的连接池
2. **Metrics 数据库**（`config/metrics.yaml`）：执行追踪与运行日志存储

---

## 2. 业务数据库（连接池）

### 配置（config/db.yaml）

```yaml
default: mysql_main

pools:
  mysql_main:
    type: mysql
    host: localhost
    port: 3306
    user: root
    password: ${MYSQL_PASSWORD:}
    database: kf
    pool_size: 5

  pg_analytics:
    type: postgresql
    host: localhost
    port: 5432
    user: postgres
    password: ${PG_PASSWORD:}
    database: analytics
    pool_size: 3
```

### 字段参考

| 字段 | 必填 | 说明 |
|------|------|------|
| `default` | 否 | 默认连接池名称 |
| `pools.{name}.type` | 是 | `mysql` 或 `postgresql` |
| `pools.{name}.host` | 否 | 主机地址，默认 `localhost` |
| `pools.{name}.port` | 否 | 端口（MySQL 默认 3306，PG 默认 5432） |
| `pools.{name}.user` | 否 | 用户名 |
| `pools.{name}.password` | 否 | 密码，支持 `${ENV_VAR}` 占位符 |
| `pools.{name}.database` | 否 | 数据库名 |
| `pools.{name}.pool_size` | 否 | 连接池大小，默认 5 |

### 代码架构

| 模块 | 说明 |
|------|------|
| `src/db/base.py` | `DBConfig`、`DBPoolConfig` 数据类，`DBPool` 抽象基类 |
| `src/db/mysql_pool.py` | `MySQLPool`（pymysql 实现） |
| `src/db/pg_pool.py` | `PgPool`（psycopg2 实现） |
| `src/db/__init__.py` | `create_pool(name, config)`、`get_db_pool(name)`、`close_all_pools()` |

连接池在应用启动时通过 `src/api/main.py` 创建。

### 在 db_query 工具中使用

```yaml
tool: db_query
db: mysql_main
query: SELECT * FROM faq WHERE question LIKE %s
params:
  - "%{{query}}%"
limit: 20
```

**模板变量**：

| 变量 | 来源 |
|------|------|
| `{{query}}` | 当前轮用户输入 |
| `{{chat_id}}` | 会话 ID |
| `{{_workflow}}` | 工作流名称 |
| `{{<field>}}` | 前序节点的 `data.<field>` 或 `data_map` 中的字段 |
| `{{data_map}}` | 整个 data_map 的 JSON 字符串 |

**返回格式**：

```json
{
  "text": "mysql_main\nid, question, answer\n----------------\n1, ...",
  "rows": [
    {"id": 1, "question": "...", "answer": "..."}
  ],
  "db": "mysql_main"
}
```

---

## 3. Metrics 数据库 Schema 管理

### 架构

```
src/metrics/
├── schema.py       # 规范 DDL + 列定义（唯一真相源）
├── migration.py    # Migration 数据类 + MIGRATIONS 列表 + migrate() 引擎
├── dialect.py      # SQL 方言（SQLite / MySQL / PostgreSQL）
├── store.py        # MetricsStore（SQLite）→ _init_db() 调用 migrate()
├── sql_store.py    # SQLMetricsStore（MySQL / PG）→ _init_db() 调用 migrate()
└── factory.py      # create_metrics_store() 工厂
```

### 核心原则

1. **唯一真相源**：所有表结构定义在 `src/metrics/schema.py`
2. **版本化迁移**：通过 `Migration` 数据类定义变更，`version` 递增
3. **自动执行**：启动时 `_init_db()` → `migrate(conn, dialect)` 自动应用
4. **非破坏性**：表结构变更前自动备份旧表（`<table>_backup_<YYYYMMDD_HHMMSS>`）
5. **幂等**：`_schema_version` 表记录已应用版本，重复执行无副作用

### 如何新增一次迁移

**示例**：为 `runs` 表添加 `cost_estimated` 列。

**第 1 步：更新 schema.py**

在 `TABLE_COLUMNS["runs"]` 列表末尾添加 `"cost_estimated"`：

```python
TABLE_COLUMNS: dict[str, list[str]] = {
    "runs": [
        ...
        "created_at",
        "cost_estimated",  # 新增
    ],
```

在 `all_table_ddl()` 的 runs DDL 中添加新列：

```python
f"""CREATE TABLE IF NOT EXISTS runs (
    ...
    created_at       {vc} DEFAULT {ts},
    cost_estimated   REAL DEFAULT 0
)"""
```

**第 2 步：追加 Migration**

在 `src/metrics/migration.py` 的 `MIGRATIONS` 列表末尾追加：

```python
Migration(
    version=2,
    description="Add cost_estimated column to runs",
    table_columns={"runs": TABLE_COLUMNS["runs"]},
    ddl_sql=["ALTER TABLE runs ADD COLUMN cost_estimated REAL DEFAULT 0"],
    index_sql=[],
)
```

**第 3 步：验证**

```bash
python -m pytest tests/test_metrics.py -k "metrics or migration"
```

**第 4 步：部署** — API 启动时自动执行迁移，失败则启动终止。

### 迁移规则

| 操作 | 迁移动作 | 示例 |
|------|---------|------|
| 新建表 | `ddl_sql` 含 `CREATE TABLE` | version 1 |
| 新增列 | `ddl_sql` 含 `ALTER TABLE ADD COLUMN` | `cost_estimated` |
| 列类型变更 | `table_columns` 触发 drift → 备份 → 重建 | 极少发生 |
| 新增索引 | `index_sql` 含 `CREATE INDEX` | `idx_runs_cost` |
| 删除列 | 标记弃用，下个大版本清理 | — |

**禁止**：迁移中不得直接 `DROP TABLE` 或 `DELETE`。数据清理应通过 `_backup_table` 安全进行。

---

## 4. 依赖安装

```bash
pip install pymysql              # MySQL
pip install psycopg2-binary      # PostgreSQL
# 或一次性安装所有生产依赖：
pip install -e .[prod]
```

---

## 5. 连接池生命周期

- 应用启动时根据 `config/db.yaml` 创建所有连接池
- 连接在 `pool_size` 范围内复用
- `db_query` 工具自动从对应池获取连接，查询后归还
- 所有连接池在应用关闭（shutdown）时统一释放

---

## 6. 环境变量配置

```bash
# 业务数据库（匹配 config/db.yaml 中的 ${ENV_VAR} 占位符）
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3307
MYSQL_USER=root
MYSQL_PASSWORD=kfpass
MYSQL_DB=kf_metrics

PG_HOST=127.0.0.1
PG_PORT=5433
PG_USER=postgres
PG_PASSWORD=kfpass
PG_DB=kf_analytics

# Metrics 数据库（独立配置，通过 factory 创建）
KF_METRICS_DB_HOST=127.0.0.1
KF_METRICS_DB_PORT=3307
KF_METRICS_DB_USER=root
KF_METRICS_DB_PASSWORD=kfpass
KF_METRICS_DB_NAME=kf_metrics
KF_METRICS_DB_TYPE=mysql
```
