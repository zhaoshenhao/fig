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
| GET | `/sessions` | 列出所有会话 |
| GET | `/sessions/{chat_id}` | 会话的所有轮次 |
| GET | `/sessions/{chat_id}/turns/{turn_id}` | 轮次的所有节点 |
| GET | `/sessions/{chat_id}/turns/{turn_id}/nodes/{node_name}` | 节点的所有工具调用 |

## 查询示例

```bash
# 列出会话
curl http://$WIN_IP:9000/sessions

# 查看某会话的所有轮次
curl http://$WIN_IP:9000/sessions/chat_abc123

# 查看某轮次的节点详情
curl http://$WIN_IP:9000/sessions/chat_abc123/turns/0

# 查看某节点的工具调用
curl http://$WIN_IP:9000/sessions/chat_abc123/turns/0/nodes/retrieve
```

## GUI 查看

Streamlit GUI → "会话追踪" Tab：
- 会话列表 → 展开 → 轮次列表 (含 query/reply/耗时)
- 轮次展开 → 节点列表 (含 输入/输出/耗时)
- 节点展开 → 工具调用列表 (含 入参/返回/耗时)

## Prometheus 指标

`/metrics` 端点暴露 4 个进程内存指标：

| 指标 | 类型 | 说明 |
|------|------|------|
| `http_requests_total` | Counter | HTTP 请求计数 |
| `http_request_duration_seconds` | Histogram | HTTP 延迟分布 |
| `llm_calls_total` | Counter | LLM 调用次数 |
| `rag_search_duration_ms` | Histogram | RAG 检索延迟 |
