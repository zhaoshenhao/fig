# Metrics 数据库结构

## 概述

基于 SQLite 的三层执行追踪存储，用于训练数据采集和性能分析。

```
runs ─── 每轮对话 (session × turn)
  └── node_logs ─── 该轮中每个节点的执行
        └── tool_logs ─── 节点内每个工具的调用
```

## 表结构

### runs — 运行记录

每轮对话一条记录。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| chat_id | TEXT NOT NULL | 会话 ID |
| turn_id | INTEGER NOT NULL | 轮次序号 |
| workflow_name | TEXT NOT NULL | 工作流名称 |
| query | TEXT | 用户输入 |
| reply | TEXT | 系统回复 |
| node_count | INTEGER | 执行节点数 |
| duration_ms | REAL | 总耗时（毫秒） |
| status | TEXT | ok / error |
| error_message | TEXT | 错误信息 |
| created_at | TEXT | 创建时间 |

索引: `idx_runs_chat` (chat_id, turn_id), `idx_runs_workflow` (workflow_name, created_at)

### node_logs — 节点日志

每个节点执行一条记录。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增 |
| run_id | INTEGER FK | 关联 runs.id |
| chat_id | TEXT NOT NULL | 会话 ID |
| turn_id | INTEGER NOT NULL | 轮次序号 |
| node_name | TEXT NOT NULL | 节点名 (retrieve, generate, input, output 等) |
| tool_name | TEXT | 工具类型 (llm, rag_search, router 等) |
| input_data | TEXT | 节点输入 (YAML 配置 JSON) |
| output_text | TEXT | 节点输出文本 |
| duration_ms | REAL | 执行耗时（毫秒） |
| status | TEXT | ok / error |
| error_message | TEXT | 错误信息 |
| created_at | TEXT | 创建时间 |

索引: `idx_node_logs_run` (run_id), `idx_node_logs_chat` (chat_id, turn_id)

### tool_logs — 工具调用日志

每个工具调用一条记录。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增 |
| node_log_id | INTEGER FK | 关联 node_logs.id |
| run_id | INTEGER FK | 关联 runs.id |
| chat_id | TEXT NOT NULL | 会话 ID |
| turn_id | INTEGER NOT NULL | 轮次序号 |
| node_name | TEXT NOT NULL | 所属节点名 |
| tool_name | TEXT NOT NULL | 工具名 |
| input_params | TEXT | 工具入参 (JSON) |
| output_result | TEXT | 工具返回 (JSON) |
| duration_ms | REAL | 工具执行耗时（毫秒） |
| status | TEXT | ok / error |
| error_message | TEXT | 错误信息 |
| created_at | TEXT | 创建时间 |

索引: `idx_tool_logs_node` (node_log_id), `idx_tool_logs_run` (run_id)

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/sessions` | 列出/搜索会话（支持过滤、排序、分页） |
| GET | `/sessions/{chat_id}` | 会话的所有轮次 |
| GET | `/sessions/{chat_id}/turns/{turn_id}` | 轮次的所有节点 |
| GET | `/sessions/{chat_id}/turns/{turn_id}/nodes/{node_name}` | 节点的所有工具调用 |
| GET | `/metrics/summary` | 仪表盘聚合：全局概览 + 按工作流明细（含 sessions/error_rate/p95/tokens）+ `wf_nodes`/`wf_tools`（每工作流的节点/工具 calls/avg/p95/error_rate） |
| GET | `/metrics/timeseries?workflow=X` | 按分钟分桶时间序列（工作流/节点/工具的请求量、平均延迟、P95、活跃会话），供图表页折线图 |
| POST | `/metrics/retention?days=N` | 数据保留：删除 N 天前的记录 |
| GET | `/export/training.jsonl` | 导出训练样本（query→reply）为 JSONL |
| POST | `/export/chat.xlsx` · `/export/chat.csv` | 导出聊天记录为 Excel/CSV |

### 存储引擎（多数据库）

Metrics 存储支持 **SQLite（默认）/ MySQL / PostgreSQL**，通过 `config/metrics.yaml`
或环境变量 `KF_METRICS_ENGINE` 选择。安装与建表见 [`metrics-db-setup.md`](./metrics-db-setup.md)。

- `runs` 表新增 `prompt_tokens` / `completion_tokens`（token 用量，来自 LLM 响应 usage）
- schema 迁移为**非破坏性**（旧表重命名为 `*_backup_<时间戳>`，不丢历史）

### Prometheus 指标（节点/工具级）

除 4 个 HTTP/LLM/RAG 指标外，新增：

| 指标 | 类型 | 标签 |
|------|------|------|
| `node_executions_total` | Counter | node, tool, status |
| `node_duration_ms` | Histogram | node, tool |
| `tool_calls_total` | Counter | tool, status |
| `workflow_runs_total` | Counter | workflow, status |

Grafana 面板见 `k8s/grafana-dashboard.json`；告警规则见 `k8s/prometheus-rules.yaml`
（含节点/工具错误率与 P95 延迟告警）。OpenTelemetry 可通过 OTel Collector 的
Prometheus receiver 抓取 `/metrics` 端点接入。

### `/sessions` 查询参数

所有参数均可选，可任意组合。文本类过滤为子串匹配（`LIKE %value%`）。

| 参数 | 类型 | 说明 |
|------|------|------|
| `limit` | int | 每页条数（默认 50） |
| `offset` | int | 偏移量（默认 0） |
| `time_from` | str | 起始时间 `YYYY-MM-DD HH:MM:SS`（`runs.created_at >=`） |
| `time_to` | str | 结束时间（`runs.created_at <=`） |
| `workflow` | str | 工作流名过滤（`runs.workflow_name`） |
| `node` | str | 节点名过滤（匹配 `node_logs.node_name`） |
| `tool` | str | 工具名过滤（匹配 `node_logs.tool_name`） |
| `input_text` | str | 节点输入文本过滤（匹配 `node_logs.input_data`） |
| `output_text` | str | 节点输出文本过滤（匹配 `node_logs.output_text`） |
| `duration_min` | float | 最小总耗时（毫秒） |
| `duration_max` | float | 最大总耗时（毫秒） |
| `sort_by` | str | 排序字段：`last_at`(默认) / `first_at` / `duration_ms` / `turn_count` / `chat_id` |
| `sort_dir` | str | `desc`(默认) / `asc` |

`node` / `tool` / `input_text` / `output_text` 通过 `runs.id IN (SELECT run_id FROM node_logs WHERE ...)` 子查询实现，可单独使用或与其他条件组合。

响应：`{"sessions": [...], "total": <int>}`，其中 `total` 为去重后的会话总数（用于分页）。

## 查询示例

```bash
# 列出会话
curl http://$WIN_IP:9000/sessions

# 按工作流 + 工具过滤
curl "http://$WIN_IP:9000/sessions?workflow=auto_film&tool=rag_search"

# 按节点输出文本搜索，按耗时升序
curl "http://$WIN_IP:9000/sessions?output_text=隔热膜&sort_by=duration_ms&sort_dir=asc"

# 查看某会话的所有轮次
curl http://$WIN_IP:9000/sessions/chat_abc123

# 查看某轮次的节点详情
curl http://$WIN_IP:9000/sessions/chat_abc123/turns/0

# 查看某节点的工具调用
curl http://$WIN_IP:9000/sessions/chat_abc123/turns/0/nodes/retrieve
```

## GUI 查看

Vue SPA 侧边栏含独立的 **聊天记录**（`MetricsPage.vue`）与 **仪表盘**（`DashboardPage.vue`）两个菜单。

**聊天记录** — 会话搜索/过滤 + 会话详情 DAG 执行追踪：

**搜索过滤** — 折叠面板提供上述全部过滤条件（时间范围/工作流/节点/工具/输入/输出/时长区间），支持列头点击排序与上一页/下一页分页。**会话列表** — 每个会话一行，含轮次/总耗时/时间范围。

**DAG 执行状态** — 点击会话行打开详情弹窗，按工作流 DAG 拓扑层级组织节点：
- ✅ 已执行节点（绿色）— 点击显示输入/输出/工具调用详情
- ⚪ 未执行节点（灰色）— 仅显示节点名和路由类型标签（if-then / switch）
- 层级间用箭头连接，展示节点依赖关系
- Fallback：当工作流配置不可用时，退化为展开式节点列表

**仪表盘**（独立页，含两个 Tab）：
- **总览** — 数据源 `/metrics/summary`：
  - 第一行为全局概览卡片（总请求/会话/错误率/平均/P50/P95/P99/Tokens）
  - 下方**按使用频率（请求量降序）逐个工作流列出区块**，每块含：
    - 工作流指标：总请求、总会话、错误率、平均耗时、P95 延迟、总 Token
    - 节点明细表（每节点：请求/平均/P95/错误率）
    - 工具明细表（每工具：请求/平均/P95/错误率）
- **图表** — 数据源 `/metrics/timeseries`：选择工作流 + 时间范围（预设/自定义），折线图展示活跃 Session 数、请求轮次（每分钟）、平均/ P95 延迟；并按节点、按工具分别绘制请求量/平均延迟/P95 多线图。图表为**零依赖内联 SVG**（`LineChart.vue`）。

> 训练数据导出按钮已移至「聊天记录」页。

## Prometheus 指标

`/metrics` 端点暴露 4 个进程内存指标：

| 指标 | 类型 | 说明 |
|------|------|------|
| `http_requests_total` | Counter | HTTP 请求计数 |
| `http_request_duration_seconds` | Histogram | HTTP 延迟分布 |
| `llm_calls_total` | Counter | LLM 调用次数 |
| `rag_search_duration_ms` | Histogram | RAG 检索延迟 |
