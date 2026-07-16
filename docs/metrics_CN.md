# Metrics 执行追踪存储

[English](metrics_EN.md)

## 1. 概述

三层执行追踪存储，用于训练数据采集和性能分析：

```
runs (每轮对话)
  └── node_logs (每次节点执行)
        └── tool_logs (每次工具调用)
```

- **runs**：每轮对话一条记录（`session × turn`）
- **node_logs**：该轮中每个节点的执行记录
- **tool_logs**：节点内每个工具的调用记录

另有辅助表：`feedback`（用户反馈）、`session_meta`（会话元数据）、`rag_retrievals`（RAG 检索记录）、`_schema_version`（迁移版本）。

## 2. 存储引擎

支持三种数据库引擎，通过配置切换。**默认 SQLite**，生产当前使用 SQLite。

| 引擎 | 配置键 | 驱动 | 适用场景 |
|--------|-----------|--------|----------|
| SQLite | `sqlite` | 内置 (`sqlite3`) | 开发，单实例 |
| MySQL | `mysql` | PyMySQL | 生产（ACK RDS） |
| PostgreSQL | `postgresql` | psycopg2 | 生产（ACK RDS） |

**配置方式**：`config/metrics.yaml` 或环境变量。

```yaml
# config/metrics.yaml
engine: ${KF_METRICS_ENGINE:-sqlite}   # sqlite | mysql | postgresql
path: data/metrics.db                  # SQLite 专用
pool: metrics                          # MySQL/PG 使用的连接池名（对应 config/db.yaml）
retention_days: 0                      # 0 = 不限制
```

环境变量覆盖（优先级最高）：

| 变量 | 说明 | 默认值 |
|------|------|------|
| `KF_METRICS_ENGINE` | `sqlite` / `mysql` / `postgresql` | `sqlite` |
| `KF_METRICS_DB_PATH` | SQLite 文件路径 | `data/metrics.db` |
| `KF_METRICS_POOL` | MySQL/PG 连接池名 | `metrics` |

> 切换引擎不会自动迁移历史数据；如需保留，请使用迁移脚本（见 `docs/metrics-db-setup.md` 末尾示例）。

**SQL 方言差异**（由 `src/metrics/dialect.py` 自动处理）：

| 维度 | SQLite | MySQL | PostgreSQL |
|------|--------|-------|------------|
| 自增主键 | `INTEGER PRIMARY KEY AUTOINCREMENT` | `BIGINT AUTO_INCREMENT` | `BIGSERIAL` |
| 占位符 | `?` | `%s` | `%s` |
| 时间默认值 | `datetime('now')` | `CURRENT_TIMESTAMP` | `now() at time zone 'utc'` |
| 插入返回 ID | `lastrowid` | `lastrowid` | `RETURNING id` |
| 去重聚合 | `GROUP_CONCAT` | `GROUP_CONCAT` | `string_agg` |

**本地验证**（WSL Docker）：

```bash
docker run -d --name kf-mysql -e MYSQL_ROOT_PASSWORD=kfpass \
    -e MYSQL_DATABASE=kf_metrics -p 3307:3306 mysql:8
docker run -d --name kf-pg -e POSTGRES_PASSWORD=kfpass \
    -e POSTGRES_DB=kf_metrics -p 5433:5432 postgres:16

# 切换到 MySQL
$env:KF_METRICS_ENGINE="mysql"
uvicorn src.api.main:app --port 9000
```

## 3. 表结构

### runs — 运行记录

每轮对话一条记录。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 自增主键 |
| `chat_id` | TEXT NOT NULL | 会话 ID |
| `turn_id` | INTEGER NOT NULL | 轮次序号 |
| `workflow_name` | TEXT NOT NULL | 工作流名称 |
| `query` | TEXT | 用户输入 |
| `reply` | TEXT | 系统回复 |
| `node_count` | INTEGER DEFAULT 0 | 执行节点数 |
| `duration_ms` | REAL | 总耗时（毫秒） |
| `status` | TEXT DEFAULT 'ok' | `ok` / `error` |
| `error_message` | TEXT | 错误信息 |
| `prompt_tokens` | INTEGER DEFAULT 0 | LLM 提示 token 数 |
| `completion_tokens` | INTEGER DEFAULT 0 | LLM 生成 token 数 |
| `created_at` | TEXT | 创建时间 |

索引：
- `idx_runs_chat` (`chat_id`, `turn_id`)
- `idx_runs_workflow` (`workflow_name`, `created_at`)

### node_logs — 节点日志

每个节点执行一条记录。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 自增主键 |
| `run_id` | INTEGER FK → runs.id | 关联运行记录 |
| `chat_id` | TEXT NOT NULL | 会话 ID |
| `turn_id` | INTEGER NOT NULL | 轮次序号 |
| `node_name` | TEXT NOT NULL | 节点名（如 `retrieve`, `generate`, `input`, `output`） |
| `tool_name` | TEXT DEFAULT '' | 工具类型（如 `llm`, `rag_search`, `router`） |
| `input_data` | TEXT | 节点输入（YAML 配置 JSON） |
| `output_text` | TEXT | 节点输出文本 |
| `duration_ms` | REAL | 执行耗时（毫秒） |
| `status` | TEXT DEFAULT 'ok' | `ok` / `error` |
| `error_message` | TEXT | 错误信息 |
| `created_at` | TEXT | 创建时间 |

索引：
- `idx_node_logs_run` (`run_id`)
- `idx_node_logs_chat` (`chat_id`, `turn_id`)

### tool_logs — 工具调用日志

每个工具调用一条记录。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 自增主键 |
| `node_log_id` | INTEGER FK → node_logs.id | 关联节点日志 |
| `run_id` | INTEGER FK → runs.id | 关联运行记录 |
| `chat_id` | TEXT NOT NULL | 会话 ID |
| `turn_id` | INTEGER NOT NULL | 轮次序号 |
| `node_name` | TEXT NOT NULL | 所属节点名 |
| `tool_name` | TEXT NOT NULL | 工具名 |
| `input_params` | TEXT | 工具入参（JSON） |
| `output_result` | TEXT | 工具返回（JSON） |
| `duration_ms` | REAL | 工具执行耗时（毫秒） |
| `status` | TEXT DEFAULT 'ok' | `ok` / `error` |
| `error_message` | TEXT | 错误信息 |
| `created_at` | TEXT | 创建时间 |

索引：
- `idx_tool_logs_node` (`node_log_id`)
- `idx_tool_logs_run` (`run_id`)

### 辅助表

| 表名 | 说明 | 关键字段 |
|------|------|------|
| `feedback` | 用户反馈 | `chat_id`, `turn_id`, `rating`, `comment`, `correction` |
| `session_meta` | 会话元数据 | `chat_id` (PK), `title`, `tags`, `updated_at` |
| `rag_retrievals` | RAG 检索记录 | `run_id`, `collection`, `score`, `source`, `chunk_preview`（截断500字符） |
| `_schema_version` | 迁移版本追踪 | `version` (PK), `applied_at`, `description` |

表结构由应用启动时自动创建（`CREATE TABLE IF NOT EXISTS`），无需手动建表。

## 4. Schema 管理

### 规范来源

- **Schema 唯一定义**：`src/metrics/schema.py` — `TABLE_COLUMNS` 字典 + `all_table_ddl()` 函数
- **版本化迁移**：`src/metrics/migration.py` — `Migration` 数据类 + `MIGRATIONS` 列表
- **启动时自动执行**：`migrate(conn, dialect)` 按版本顺序应用未执行的迁移

### 迁移流程

1. 读取 `_schema_version` 表获取当前版本
2. 对每个待执行的迁移：
   - 对比实际表的列名与期望列名集合（`table_columns`）
   - 若不一致：**将旧表重命名为 `<table>_backup_<YYYYMMDD_HHMMSS>`**（非破坏性备份，不丢历史数据）
   - 删除旧索引，执行新的 DDL 建表语句
   - 执行迁移专属 DDL（`ALTER TABLE` 等）
   - 创建索引
3. 在 `_schema_version` 中记录已执行的版本

### 如何新增迁移

1. 在 `src/metrics/schema.py` 的 `TABLE_COLUMNS` 中添加新列
2. 在 `all_table_ddl()` 函数的对应 `CREATE TABLE` 语句中添加新列
3. 在 `src/metrics/migration.py` 的 `MIGRATIONS` 列表末尾追加 `Migration` 数据类，版本号递增
4. 在迁移的 `ddl_sql` 中包含 `ALTER TABLE` 语句
5. 如需新索引，在 `index_sql` 中添加对应语句
6. 运行测试套件验证迁移在新数据库和旧版本数据库上均可正确执行

**原则**：永远不要提交删除数据的迁移，除非包含显式的备份步骤。

## 5. API 端点

### 端点总览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/sessions` | 列出/搜索会话（支持过滤、排序、分页） |
| GET | `/api/v1/sessions/{chat_id}` | 会话的所有轮次 |
| GET | `/api/v1/sessions/{chat_id}/turns/{turn_id}` | 轮次的所有节点 |
| GET | `/api/v1/sessions/{chat_id}/turns/{turn_id}/nodes/{node_name}` | 节点的所有工具调用 |
| GET | `/api/v1/metrics/summary` | 仪表盘聚合数据 |
| GET | `/api/v1/metrics/timeseries?workflow=X` | 时间序列数据（按分钟分桶） |
| POST | `/api/v1/metrics/retention?days=N` | 数据保留清理 |
| GET | `/api/v1/export/training.jsonl` | 导出训练样本（JSONL） |
| POST | `/api/v1/export/chat.xlsx` | 导出聊天记录（Excel） |
| POST | `/api/v1/export/chat.csv` | 导出聊天记录（CSV） |

### GET /api/v1/sessions 查询参数

所有参数均可选，可任意组合。文本类过滤为子串匹配（`LIKE %value%`）。

| 参数 | 类型 | 说明 |
|------|------|------|
| `limit` | int | 每页条数（默认 50） |
| `offset` | int | 偏移量（默认 0） |
| `time_from` | str | 起始时间 `YYYY-MM-DD HH:MM:SS`（`runs.created_at >=`） |
| `time_to` | str | 结束时间（`runs.created_at <=`） |
| `workflow` | str | 工作流名过滤（`runs.workflow_name`） |
| `node` | str | 节点名过滤（匹配 `node_logs.node_name`，子查询） |
| `tool` | str | 工具名过滤（匹配 `node_logs.tool_name`，子查询） |
| `input_text` | str | 节点输入文本过滤（匹配 `node_logs.input_data`） |
| `output_text` | str | 节点输出文本过滤（匹配 `node_logs.output_text`） |
| `duration_min` | float | 最小总耗时（毫秒） |
| `duration_max` | float | 最大总耗时（毫秒） |
| `sort_by` | str | 排序字段：`last_at`(默认) / `first_at` / `duration_ms` / `turn_count` / `chat_id` |
| `sort_dir` | str | `desc`(默认) / `asc` |

`node` / `tool` / `input_text` / `output_text` 通过 `runs.id IN (SELECT run_id FROM node_logs WHERE ...)` 子查询实现，可单独或与其他条件组合。

响应格式：`{"sessions": [...], "total": <int>}`，其中 `total` 为去重后的会话总数（用于分页）。

### 请求示例

```bash
# 列出会话
curl http://localhost:9000/api/v1/sessions

# 按工作流 + 工具过滤
curl "http://localhost:9000/api/v1/sessions?workflow=auto_film&tool=rag_search"

# 按节点输出文本搜索，按耗时升序
curl "http://localhost:9000/api/v1/sessions?output_text=隔热膜&sort_by=duration_ms&sort_dir=asc"

# 查看某会话的所有轮次
curl http://localhost:9000/api/v1/sessions/chat_abc123

# 查看某轮次的节点详情
curl http://localhost:9000/api/v1/sessions/chat_abc123/turns/0

# 查看某节点的工具调用
curl http://localhost:9000/api/v1/sessions/chat_abc123/turns/0/nodes/retrieve
```

### GET /api/v1/metrics/summary 响应结构

全局概览 + 按工作流明细 + 节点/工具粒度详情。

**全局概览**：
- `total_requests`：总请求数
- `total_sessions`：总会话数
- `error_rate`：全局错误率
- `avg_ms` / `p50_ms` / `p95_ms` / `p99_ms`：平均 / P50 / P95 / P99 延迟
- `total_prompt_tokens` / `total_completion_tokens`：Token 总量

**按工作流**（`workflows` 数组，按请求量降序）：
- 每工作流包含：`requests`、`sessions`、`error_rate`、`avg_ms`、`p95_ms`、`total_tokens`
- `wf_nodes`：每工作流每节点：`calls`、`avg_ms`、`p95_ms`、`error_rate`
- `wf_tools`：每工作流每工具：`calls`、`avg_ms`、`p95_ms`、`error_rate`

### GET /api/v1/metrics/timeseries 响应结构

按分钟分桶的时间序列数据，需指定 `workflow` 参数。

- 每桶包含：`active_sessions`（活跃会话数）、`requests`（请求数）、`avg_ms`（平均延迟）、`p95_ms`（P95 延迟）
- 按节点拆分（`nodes` 数组）：各节点请求量 / 平均延迟 / P95
- 按工具拆分（`tools` 数组）：各工具调用量 / 平均延迟 / P95

### POST /api/v1/metrics/retention

删除 N 天前的记录（`days` 查询参数）。也可通过 `metrics_store.delete_older_than("YYYY-MM-DD HH:MM:SS")` 程序调用。建议用 K8s CronJob 定期执行（如每日保留 90 天）。

## 6. Prometheus 指标

`/metrics` 端点暴露的 Prometheus 指标：

| 指标 | 类型 | 标签 | 说明 |
|------|------|------|------|
| `http_requests_total` | Counter | `method`, `path`, `status` | HTTP 请求计数 |
| `http_request_duration_seconds` | Histogram | `method`, `path` | HTTP 延迟分布 |
| `llm_calls_total` | Counter | `model` | LLM 调用次数 |
| `rag_search_duration_ms` | Histogram | — | RAG 检索延迟分布 |
| `node_executions_total` | Counter | `node`, `tool`, `status` | 节点执行次数 |
| `node_duration_ms` | Histogram | `node`, `tool` | 节点延迟分布 |
| `tool_calls_total` | Counter | `tool`, `status` | 工具调用次数 |
| `workflow_runs_total` | Counter | `workflow`, `status` | 工作流运行次数 |

- Grafana 仪表盘：`k8s/grafana-dashboard.json`
- 告警规则：`k8s/prometheus-rules.yaml`（含节点/工具错误率与 P95 延迟告警）
- OpenTelemetry：可通过 OTel Collector 的 Prometheus receiver 抓取 `/metrics` 端点接入

## 7. RAG 检索追踪

`rag_search` 结果通过 `insert_rag_retrieval()` 存入 `rag_retrievals` 表：

- 参数：`run_id`, `chat_id`, `turn_id`, `collection`, `score`, `source`, `chunk_preview`
- `chunk_preview` 截断为 500 字符
- 存储在 `src/engine/dag.py` 中 RAG 搜索节点执行时自动调用

查询接口：`query_rag_for_turn(run_id)` 按 score 降序返回某轮的所有检索结果。

## 8. 数据导出

| 端点 | 说明 |
|------|------|
| `GET /api/v1/export/training.jsonl` | 导出 query → reply 训练样本对（JSONL 格式，供模型微调） |
| `POST /api/v1/export/chat.xlsx` | 导出聊天记录为 Excel |
| `POST /api/v1/export/chat.csv` | 导出聊天记录为 CSV |

导出按钮位于 Vue SPA「聊天记录」页面。

## 9. Vue SPA 仪表盘

侧边栏含两个独立菜单页：

### 聊天记录（`MetricsPage.vue`）

- **搜索过滤面板**：支持全部查询参数（时间范围、工作流、节点、工具、输入/输出文本、时长区间），可折叠
- **会话列表**：每行含轮次数、总耗时、时间范围，支持列头点击排序与上一页/下一页分页
- **DAG 执行追踪弹窗**：点击会话行打开，按工作流 DAG 拓扑层级组织节点：
  - ✅ 已执行节点（绿色）— 点击显示输入/输出/工具调用详情
  - ⚪ 未执行节点（灰色）— 仅显示节点名和路由类型标签（if-then / switch）
  - 层级间用箭头连接，展示节点依赖关系
  - Fallback：当工作流配置不可用时，退化为展开式节点列表

### 仪表盘（`DashboardPage.vue`）

两个 Tab：

- **总览** — 数据源 `/api/v1/metrics/summary`：
  - 全局概览卡片行：总请求 / 会话 / 错误率 / 平均 / P50 / P95 / P99 / Tokens
  - 按工作流逐个区块（请求量降序），每块含：
    - 工作流指标：总请求、总会话、错误率、平均耗时、P95 延迟、总 Token
    - 节点明细表（每节点：请求 / 平均 / P95 / 错误率）
    - 工具明细表（每工具：请求 / 平均 / P95 / 错误率）

- **图表** — 数据源 `/api/v1/metrics/timeseries`：
  - 选择工作流 + 时间范围（预设/自定义）
  - SVG 折线图（零依赖 `LineChart.vue`）：活跃 Session 数、每分钟请求量、平均/P95 延迟
  - 按节点、按工具分别绘制请求量 / 平均延迟 / P95 多线图

## 10. 配置参考

### config/metrics.yaml

```yaml
# Metrics 存储引擎配置
# engine: sqlite | mysql | postgresql（默认 sqlite，当前生产使用 sqlite）
# 环境变量可覆盖：KF_METRICS_ENGINE / KF_METRICS_DB_PATH / KF_METRICS_POOL
#
# 切换到 mysql / postgresql 前，请先在 config/db.yaml 中配置对应的连接池，
# 并参考 docs/metrics-db-setup.md 建库建表。

engine: ${KF_METRICS_ENGINE:-sqlite}

# SQLite 专用
path: data/metrics.db

# MySQL / PostgreSQL 时使用的连接池名（对应 config/db.yaml 中的 pools 键）
pool: metrics

# 数据保留：超过该天数的记录可由维护任务清理，0 表示不限制
retention_days: 0
```

### config/db.yaml（MySQL 连接池示例）

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

### config/db.yaml（PostgreSQL 连接池示例）

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

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|------|
| `KF_METRICS_ENGINE` | 存储引擎类型 | `sqlite` |
| `KF_METRICS_DB_PATH` | SQLite 文件路径 | `data/metrics.db` |
| `KF_METRICS_POOL` | 连接池名 | `metrics` |

### 生产数据库初始化

**MySQL**（字符集必须 `utf8mb4`）：

```sql
CREATE DATABASE kf_metrics CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'kf'@'%' IDENTIFIED BY 'your-strong-password';
GRANT ALL PRIVILEGES ON kf_metrics.* TO 'kf'@'%';
FLUSH PRIVILEGES;
SET GLOBAL time_zone = '+00:00';
```

**PostgreSQL**：

```sql
CREATE DATABASE kf_metrics ENCODING 'UTF8';
CREATE USER kf WITH PASSWORD 'your-strong-password';
GRANT ALL PRIVILEGES ON DATABASE kf_metrics TO kf;
```

应用启动时表结构自动创建，无需手动执行 DDL。

### 从 SQLite 迁移历史数据

一次性迁移脚本示例：

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
    # node_logs / tool_logs 需按 run_id 映射后迁移
```

> 生产迁移前在预发环境验证，低峰期执行并先备份。
