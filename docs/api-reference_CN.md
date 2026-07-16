[English](api-reference_EN.md)

# KF 智能客服引擎 · HTTP API 参考

> 版本：`0.2.0` ｜ 协议：HTTP/1.1 + JSON（UTF-8）｜ 流式：SSE (`text/event-stream`)

---

## 概述

| 项 | 说明 |
|----|------|
| Base URL | `http://<HOST>:9000`（生产经 ALB Ingress，路径不变） |
| 编码 | 请求与响应均为 UTF-8。POST JSON 建议显式 `Content-Type: application/json; charset=utf-8` |
| 流式 | SSE (`text/event-stream`)，逐 token 推送 |
| 时间格式 | 所有时间为 **UTC**，字符串格式 `YYYY-MM-DD HH:MM:SS` |
| 请求追踪 | 每个响应含 `X-Request-ID` 头，服务端日志据此关联；500 错误响应体中也含 `request_id` |
| 幂等性 | `GET`/`DELETE` 幂等；`POST /api/v1/workflows/{name}/run` 每次调用产生一轮新对话 |
| 分页 | 统一 `limit` + `offset` 查询参数 |

---

## 认证

基于静态 API Key 白名单，通过请求头传递：

```
X-API-Key: <YOUR_KEY>
```

- Key 列表配置在 `config/auth.yaml` 的 `api_keys`（支持 `${ENV_VAR}`）
- **`api_keys` 为空数组 = 关闭鉴权**（开发模式，所有请求放行）
- 放行路径（`skip_paths`，无需 Key）：`/health`、`/ready`、`/docs`、`/openapi.json`、`/redoc`
- 鉴权失败返回 `401`：

```json
{ "error": "invalid or missing X-API-Key" }
```

> 交互式文档：服务内置 Swagger UI `GET /docs` 与 OpenAPI `GET /openapi.json`（FastAPI 自动生成），可在浏览器直接调试。

---

## 错误处理

| 状态码 | 含义 | 场景 |
|--------|------|------|
| `200` | 成功 | 正常返回 |
| `204` | 成功，无内容 | 删除会话成功 |
| `400` | 请求错误 | 会话与工作流不匹配、参数错误、检索/入库失败 |
| `401` | 未认证 | 缺失或非法 `X-API-Key` |
| `404` | 不存在 | 工作流/会话/集合/节点不存在，或会话已过期 |
| `422` | 参数校验失败 | 缺必填字段、`query` 为空、类型错误 |
| `500` | 服务器内部错误 | 未捕获异常（详情仅入日志，不对外暴露；响应含 `request_id`） |
| `503` | 配置重载中 | 热重载窗口期，`Retry-After: 1` 秒后重试 |

**业务错误**（HTTPException）格式：

```json
{ "detail": "workflow 'foo' not found" }
```

**未捕获异常**（500）格式：

```json
{
  "error": "internal server error",
  "detail": "服务器内部错误，请稍后重试或联系管理员",
  "request_id": "3f8c1a2b..."
}
```

**参数校验**（422，FastAPI 标准）：

```json
{
  "detail": [
    {
      "type": "string_too_short",
      "loc": ["body", "query"],
      "msg": "String should have at least 1 character",
      "input": ""
    }
  ]
}
```

---

## API 端点

### 健康检查 & 运维

#### `GET /health`

存活探针（无需认证）。Kubernetes liveness probe。

- **认证**：否

**响应 200**

```json
{ "status": "ok", "timestamp": 1785000000.123, "startup_seconds": 3.45 }
```

---

#### `GET /ready`

就绪探针（无需认证）。探测 Qdrant、Embedding 服务、DB 连接池状态，并返回已加载的工作流列表。Kubernetes readiness probe。

- **认证**：否

**响应 200**

```json
{
  "status": "ready",
  "probes": {
    "qdrant": "ok",
    "embedding": "ok",
    "db_pools": "mysql_main: OperationalError, pg_analytics: OperationalError"
  },
  "workflows": ["auto_film", "customer_service", "default"],
  "llm_default": "deepseek",
  "embed_default": "nomic-embed-text"
}
```

- `probes.qdrant`：检查 Qdrant 集合列表是否可获取
- `probes.embedding`：检查 kf-embed 微服务 `/health` 端点
- `probes.db_pools`：列出各 DB 连接池的连接测试结果，或 `"not configured"`

---

#### `GET /status`

系统整体健康状态 + 各下游组件逐一探测（结构化，供状态页/监控使用）。

- **认证**：需要

**响应 200**

```json
{
  "status": "ok",
  "timestamp": 1785000000.5,
  "components": {
    "qdrant":        { "status": "ok", "latency_ms": 12.3, "detail": "7 collections" },
    "llm":           { "status": "ok", "latency_ms": 210.0, "detail": "provider=openai model=deepseek-v4-flash host=api.deepseek.com (HTTP 200)" },
    "embedding":     { "status": "ok", "latency_ms": 35.0, "detail": "model=nomic-embed-text host=localhost:8100 (HTTP 200)" },
    "metrics_store": { "status": "ok", "latency_ms": 1.1, "detail": "data\\metrics.db" },
    "db_pools":      { "status": "ok", "latency_ms": 5.0, "detail": "mysql_main:OperationalError,pg_analytics:ok" }
  },
  "process": {
    "version": "0.2.0",
    "python": "3.14.5",
    "uptime_seconds": 3600.0,
    "workflow_count": 3,
    "workflows": ["auto_film", "customer_service", "default"]
  }
}
```

- `status`：全局状态 — `ok`（全部组件正常）或 `degraded`（任一组件异常）
- 各组件含 `status`（`ok`/`error`）、`latency_ms`（探测耗时）、`detail`（补充信息）

---

#### `GET /metrics`

Prometheus 文本格式指标（`text/plain`）。

- **认证**：需要

**核心指标**

| 指标 | 类型 | 标签 |
|------|------|------|
| `http_requests_total` | Counter | method, path, status |
| `http_request_duration_seconds` | Histogram | method, path, status |
| `llm_calls_total` | Counter | model |
| `rag_search_duration_ms` | Histogram | — |
| `node_executions_total` | Counter | node, tool, status |
| `node_duration_ms` | Histogram | node, tool |
| `tool_calls_total` | Counter | tool, status |
| `workflow_runs_total` | Counter | workflow, status |

---

#### `POST /reload`

**热重载配置**：重新读取全部 YAML 配置文件并原子替换运行中配置，无需重启进程。

- **认证**：需要
- **请求体**：空 JSON `{}`（POST 必须带 body）

**响应 200**

```json
{ "status": "ok", "workflows": ["auto_film", "customer_service", "default"] }
```

**工作原理**：
1. 加写锁 → 在旧配置上标记 `need_reload=True`
2. 扫描 `config/` 重新构建 AppConfig（跳过 `enabled: false` 的工作流）
3. 原子替换全局配置 → 触发 DAG 引擎回调更新引用
4. 释放锁

**冲突保护**：标记 `need_reload` 到替换完成之间的窗口期（通常 <100ms），除 `/reload` 外的所有请求返回 `503 Service Unavailable` + `Retry-After: 1`。

**工作流启用/禁用**：在 `config/workflows/<name>/workflow.yaml` 中设置 `enabled: true|false`（默认 `true`），设为 `false` 后调用 `/reload`，该工作流从列表消失且不可运行。无需删除文件。

```powershell
Invoke-RestMethod -Uri "http://<HOST>:9000/reload" -Method Post -Headers @{"X-API-Key"="<KEY>"} -Body "{}"
```

---

### 工作流引擎（核心）

#### `GET /api/v1/workflows`

列出所有已注册的工作流（每个产品线一个工作流）。

- **认证**：需要
- **参数**：无

**响应 200**

```json
{
  "workflows": [
    { "name": "auto_film", "description": "汽车衣膜智能问答 — 太阳膜/隐形车衣/车窗膜/车衣膜产品咨询" },
    { "name": "customer_service", "description": "客服工作流 — 意图分发 + 多分支处理" },
    { "name": "default", "description": "默认智能客服" }
  ]
}
```

---

#### `GET /api/v1/workflows/{name}`

获取某工作流的 DAG 拓扑与节点配置。

- **认证**：需要
- **路径参数**：`name` — 工作流名
- **错误**：`404` 工作流不存在

**响应 200**

```json
{
  "name": "auto_film",
  "description": "汽车衣膜智能问答 — 太阳膜/隐形车衣/车窗膜/车衣膜产品咨询",
  "collections": ["car_films"],
  "return_mode": "full",
  "nodes": [
    {
      "name": "intent_classify",
      "tool": "llm",
      "next_type": "one",
      "next": "intent_route",
      "metrics": true,
      "parallel": false,
      "config": { "tool": "llm", "system_prompt": "..." }
    },
    {
      "name": "intent_route",
      "tool": "router",
      "next_type": "if-then",
      "next": ["search_kb", "non_product_reply"],
      "metrics": true,
      "parallel": false,
      "config": { "tool": "router", "router": { "...": "..." } }
    }
  ]
}
```

字段说明：
- `next_type` ∈ `one` / `if-then` / `switch`
- `next` 为字符串（单后继）或数组（分支）
- `enabled: false` 的工作流在 `/reload` 后从列表消失，不可被运行

---

#### `POST /api/v1/workflows/{name}/run` ⭐

**对话引擎主入口**。执行指定工作流的一轮对话（DAG：意图分类 → 路由 → RAG 检索 → LLM 生成）。

- **认证**：需要
- **路径参数**：`name` — 工作流名
- **查询参数**：`stream` (bool, 默认 `false`) — `true` 时返回 SSE 流

**请求体** (`application/json`)

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `query` | string | ✅ | 用户输入文本（≥1 字符） |
| `chat_id` | string | ✕ | 续接多轮对话的会话 ID；省略则新建会话 |
| `long_mem_data` | string | ✕ | 客户端管理的长期记忆，注入到本轮上下文 |

**响应 200**（阻塞模式，`stream=false`）

```json
{
  "chat_id": "chat_054d0450cd5a400dbb34",
  "turn_id": 1,
  "reply": "哈哈，隔热膜的价格范围挺广的，从几百到几千甚至上万都有……"
}
```

| 字段 | 说明 |
|------|------|
| `chat_id` | 会话 ID，多轮续接时回传 |
| `turn_id` | 当前累计轮次（从 1 开始递增） |
| `reply` | 最终回复文本 |

**响应（流式模式，`stream=true`）**

返回 `text/event-stream`，逐 token 推送。

事件序列：
1. `status`（开始）— `{"event":"status","node":"start","workflow":"auto_film"}`
2. 裸事件行 `event: node_start`
3. `token`（多次）— `{"event":"token","data":"隔"}`
4. 裸事件行 `event: node_end`
5. `done`（结束）— `{"event":"done","chat_id":"…","turn_id":1,"reply":"完整回复"}`
6. 出错时：`{"event":"error","data":"错误信息"}`

原始 SSE 帧示例：

```
data: {"event":"status","node":"start","workflow":"auto_film"}

event: node_start

data: {"event":"token","data":"隔"}

data: {"event":"token","data":"热"}

event: node_end

data: {"event":"done","chat_id":"chat_x","turn_id":1,"reply":"隔热膜……"}
```

**客户端解析建议**：读取 `data:` 行的 JSON，按 `event` 字段分派；`done` 事件里的 `reply` 是权威完整回复（与逐 token 拼接一致）。

**JavaScript 示例**

```js
const resp = await fetch(`/api/v1/workflows/auto_film/run?stream=true`, {
  method: "POST",
  headers: { "Content-Type": "application/json", "X-API-Key": KEY },
  body: JSON.stringify({ query: "太阳膜有什么作用", chat_id }),
});
const reader = resp.body.getReader();
const dec = new TextDecoder();
let buf = "";
while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  buf += dec.decode(value, { stream: true });
  const lines = buf.split("\n"); buf = lines.pop();
  for (const line of lines) {
    if (!line.startsWith("data: ")) continue;
    const evt = JSON.parse(line.slice(6));
    if (evt.event === "token") process.stdout.write(evt.data);
    if (evt.event === "done") console.log("\n[done]", evt.chat_id, evt.turn_id);
    if (evt.event === "error") console.error("[error]", evt.data);
  }
}
```

**错误**

| 码 | 场景 |
|----|------|
| `404` | 工作流不存在；或 `chat_id` 对应会话不存在/已过期 |
| `400` | `chat_id` 所属工作流与请求的 `name` 不一致 |
| `422` | `query` 为空 |

**多轮对话**：会话由服务端保存（内存或 Redis，含 TTL）。把上一次返回的 `chat_id` 放入请求体续接：

```bash
# 第 1 轮
curl ... -d '{"query":"太阳膜有什么作用"}'
# → {"chat_id":"chat_x","turn_id":1,"reply":"..."}

# 第 2 轮
curl ... -d '{"query":"那价格呢","chat_id":"chat_x"}'
# → {"chat_id":"chat_x","turn_id":2,"reply":"..."}
```

约束：一个 `chat_id` 绑定其创建时的工作流，跨工作流复用返回 `400`；会话过期后返回 `404`。

---

#### `POST /api/v1/workflows/{name}/regenerate`

对会话的**最后一次用户输入重新生成回答**（追加为新一轮）。

- **认证**：需要
- **路径参数**：`name` — 工作流名
- **查询参数**：`stream` (bool, 默认 `false`)

**请求体** (`application/json`)

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `chat_id` | string | ✅ | 要重新生成的会话 ID |

**响应 200**：与 `run` 相同 `{ chat_id, turn_id, reply }`

**错误**

| 码 | 场景 |
|----|------|
| `404` | 工作流或会话不存在 |
| `400` | 会话属于其他工作流 / 无历史轮次 / 最后轮次无输入 |

---

### 会话管理

#### `GET /api/v1/sessions`

搜索/列出会话（分页 + 多条件过滤 + 排序）。数据来自 metrics 存储。

- **认证**：需要

**查询参数**（全部可选）

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `limit` / `offset` | int | 50 / 0 | 分页 |
| `time_from` / `time_to` | string | — | UTC 时间范围 `YYYY-MM-DD HH:MM:SS` |
| `workflow` | string | — | 工作流名（精确匹配） |
| `node` | string | — | 节点名（精确匹配） |
| `tool` | string | — | 工具名（精确匹配） |
| `input_text` | string | — | 节点输入子串匹配 |
| `output_text` | string | — | 节点输出子串匹配 |
| `duration_min` / `duration_max` | float | — | 会话总耗时区间（毫秒） |
| `feedback` | string | — | 评价过滤：`none`(无)/`up`(好评)/`down`(差评)；空=全部 |
| `title` | string | — | 会话标题子串匹配（来自 `session_meta`） |
| `sort_by` | string | `last_at` | 排序字段：`last_at`/`first_at`/`duration_ms`/`turn_count`/`chat_id` |
| `sort_dir` | string | `desc` | 排序方向：`desc`/`asc` |

**响应 200**

```json
{
  "sessions": [
    {
      "chat_id": "chat_054d0450cd5a400dbb34",
      "turn_count": 2,
      "total_duration_ms": 15321.4,
      "first_at": "2026-07-10 03:18:55",
      "last_at": "2026-07-10 03:20:10",
      "workflow_names": "auto_film"
    }
  ],
  "total": 37
}
```

---

#### `GET /api/v1/sessions/filters`

返回会话搜索的下拉候选值（去重后的工作流/节点/工具名）。

- **认证**：需要

**响应 200**

```json
{
  "workflows": ["auto_film", "customer_service", "default"],
  "nodes": ["intent_classify", "search_kb", "generate_answer"],
  "tools": ["llm", "rag_search", "router", "api_call"]
}
```

---

#### `GET /api/v1/sessions/{chat_id}`

某会话的所有轮次。

- **认证**：需要
- **查询参数**：`limit` (默认 50)、`offset` (默认 0)
- **错误**：`404` 会话不存在

**响应 200**

```json
{
  "chat_id": "chat_054d0450cd5a400dbb34",
  "turns": [
    {
      "run_id": 169,
      "turn_id": 0,
      "workflow_name": "auto_film",
      "query": "隔热膜贵不贵",
      "reply": "哈哈，隔热膜的价格范围挺广的……",
      "node_count": 6,
      "duration_ms": 9609.43,
      "status": "ok",
      "error_message": null,
      "prompt_tokens": 2280,
      "completion_tokens": 301,
      "created_at": "2026-07-10 03:18:55"
    }
  ]
}
```

---

#### `GET /api/v1/sessions/{chat_id}/turns/{turn_id}`

某一轮次内所有节点的执行详情 + RAG 检索记录 + 反馈。

- **认证**：需要
- **错误**：`404` 轮次不存在

**响应 200**

```json
{
  "chat_id": "chat_x",
  "turn_id": 0,
  "run": {
    "run_id": 169,
    "turn_id": 0,
    "workflow_name": "auto_film",
    "query": "隔热膜贵不贵",
    "reply": "哈哈，隔热膜的价格范围……",
    "node_count": 6,
    "duration_ms": 9609.43,
    "status": "ok",
    "error_message": null,
    "prompt_tokens": 2280,
    "completion_tokens": 301,
    "created_at": "2026-07-10 03:18:55"
  },
  "nodes": [
    {
      "node_log_id": 501,
      "node_name": "search_kb",
      "tool_name": "rag_search",
      "input_data": "...",
      "output_text": "...",
      "duration_ms": 82.1,
      "status": "ok",
      "error_message": null,
      "created_at": "2026-07-10 03:18:55"
    }
  ],
  "feedback": [
    { "id": 1, "rating": "up", "comment": "好", "correction": null, "created_at": "2026-07-11 03:00:00" }
  ],
  "rag": [
    {
      "id": 1,
      "collection": "car_films",
      "score": 0.67,
      "source": "COMPREHENSIVE_KNOWLEDGE_BASE.md",
      "chunk_preview": "行业标准参数……"
    }
  ]
}
```

`rag` 字段仅在含 `rag_search` 节点的轮次中有数据；每行列出一条召回结果（score/collection/source/内容预览）。

---

#### `GET /api/v1/sessions/{chat_id}/turns/{turn_id}/nodes/{node_name}`

某节点下每个工具调用的入参/返回详情。

- **认证**：需要
- **错误**：`404` 轮次或节点不存在

**响应 200**

```json
{
  "chat_id": "chat_x",
  "turn_id": 0,
  "node_name": "search_kb",
  "node": {
    "node_log_id": 501,
    "node_name": "search_kb",
    "tool_name": "rag_search",
    "input_data": "...",
    "output_text": "...",
    "duration_ms": 82.1,
    "status": "ok",
    "error_message": null,
    "created_at": "2026-07-10 03:18:55"
  },
  "tools": [
    {
      "tool_log_id": 900,
      "tool_name": "rag_search",
      "input_params": "{…}",
      "output_result": "{…}",
      "duration_ms": 80.0,
      "status": "ok",
      "error_message": null,
      "created_at": "2026-07-10 03:18:55"
    }
  ]
}
```

---

#### `DELETE /api/v1/sessions/{chat_id}`

删除（结束）一个会话。

- **认证**：需要
- **响应**：`204 No Content`
- **错误**：`404` 会话不存在

```bash
curl -X DELETE "http://<HOST>:9000/api/v1/sessions/chat_x" -H "X-API-Key: <KEY>"
```

---

#### `GET /api/v1/sessions/{chat_id}/meta`

查询会话元信息（标题/标签）。数据优先读取实时会话，会话过期后从 metrics 持久化存储回退。

- **认证**：需要

**响应 200**

```json
{
  "chat_id": "chat_x",
  "title": "VIP 咨询",
  "tags": ["vip", "film"],
  "workflow": "auto_film",
  "turn_id": 5
}
```

会话过期时 `workflow`/`turn_id` 为 `null`，`title`/`tags` 从 metrics 读取。

---

#### `PATCH /api/v1/sessions/{chat_id}/meta`

更新会话元信息（标题/标签）。同时写入实时会话 + metrics 持久化。对不存在/过期的会话也可写入（仅持久化到 metrics），返回 200。

- **认证**：需要

**请求体** (`application/json`)

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `title` | string | ✕ | 会话标题（仅更新提供的字段） |
| `tags` | list[string] | ✕ | 标签列表 |

```bash
curl -X PATCH "http://<HOST>:9000/api/v1/sessions/chat_x/meta" \
  -H "Content-Type: application/json" -H "X-API-Key: <KEY>" \
  -d '{"title":"VIP 咨询","tags":["vip"]}'
```

**响应 200**

```json
{ "chat_id": "chat_x", "title": "VIP 咨询", "tags": ["vip"] }
```

---

### 用户反馈

#### `POST /api/v1/sessions/{chat_id}/turns/{turn_id}/feedback`

对某轮回答提交用户反馈（👍/👎 + 评论/纠错），写入 metrics 存储。

- **认证**：需要

**请求体** (`application/json`)

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `rating` | string | ✅ | `up` 或 `down` |
| `comment` | string | ✕ | 文字评论 |
| `correction` | string | ✕ | 纠正后的正确答案 |

**响应 200**

```json
{
  "status": "ok",
  "feedback_id": 1,
  "chat_id": "chat_x",
  "turn_id": 0,
  "rating": "down"
}
```

- **错误**：`422` rating 非 `up`/`down`

```bash
curl -X POST "http://<HOST>:9000/api/v1/sessions/chat_x/turns/0/feedback" \
  -H "Content-Type: application/json" -H "X-API-Key: <KEY>" \
  -d '{"rating":"down","comment":"答非所问","correction":"太阳膜能隔热防晒"}'
```

---

#### `GET /api/v1/sessions/{chat_id}/turns/{turn_id}/feedback`

查询某轮的反馈记录。

- **认证**：需要

**响应 200**

```json
{
  "chat_id": "chat_x",
  "turn_id": 0,
  "feedback": [
    {
      "id": 1,
      "rating": "up",
      "comment": "好",
      "correction": null,
      "created_at": "2026-07-11 03:00:00"
    }
  ]
}
```

---

### 用量统计

#### `GET /api/v1/usage`

API 用量/配额：调用次数、会话数、token 消耗（可按时间范围过滤）。

- **认证**：需要
- **查询参数**：`time_from` / `time_to`（可选，UTC 格式 `YYYY-MM-DD HH:MM:SS`）

**响应 200**

```json
{
  "total_runs": 269,
  "total_sessions": 45,
  "prompt_tokens": 40000,
  "completion_tokens": 9216,
  "total_tokens": 49216,
  "error_rate": 0.011,
  "time_from": null,
  "time_to": null
}
```

---

#### `GET /api/v1/health`

外部 API 健康探针（与内部 `/health` 等价，供外部 LB/监控使用，无需认证）。

- **认证**：否

```json
{ "status": "ok", "timestamp": 1785000000.123 }
```

---

### 指标 & 分析

#### `GET /metrics/summary`

仪表盘聚合：全局概览 + 按工作流明细 + 节点/工具明细 + 趋势。

- **认证**：需要
- **查询参数**：`time_from` / `time_to`（可选，UTC）

**响应 200**（节选）

```json
{
  "overview": {
    "total_runs": 120,
    "total_sessions": 45,
    "error_runs": 3,
    "error_rate": 0.025,
    "avg_ms": 3200.5,
    "p50_ms": 2800.0,
    "p95_ms": 7100.0,
    "p99_ms": 9800.0,
    "prompt_tokens": 254000,
    "completion_tokens": 41000,
    "feedback_up": 22,
    "feedback_down": 1,
    "feedback_total": 23,
    "rating_rate": 0.19,
    "satisfaction_rate": 0.9565,
    "feedback_rate": 0.12
  },
  "by_workflow": [
    {
      "workflow_name": "auto_film",
      "runs": 88,
      "avg_ms": 3300.1,
      "errors": 2,
      "sessions": 30,
      "error_rate": 0.0227,
      "p95_ms": 7200.0,
      "tokens": 240000,
      "feedback_up": 7,
      "feedback_down": 1,
      "feedback_total": 8,
      "rating_rate": 0.09,
      "satisfaction_rate": 0.875,
      "feedback_rate": 0.06
    }
  ],
  "by_tool": [
    { "tool_name": "llm", "calls": 240, "avg_ms": 1500.0, "errors": 1 }
  ],
  "trend": [
    { "hour": "2026-07-10 03", "runs": 12, "avg_ms": 3100.0, "errors": 0 }
  ],
  "wf_nodes": {
    "auto_film": [
      { "node_name": "search_kb", "calls": 40, "avg_ms": 80.0, "errors": 0, "error_rate": 0.0, "p95_ms": 120.0 }
    ]
  },
  "wf_tools": {
    "auto_film": [
      { "tool_name": "rag_search", "calls": 40, "avg_ms": 80.0, "errors": 0, "error_rate": 0.0, "p95_ms": 120.0 }
    ]
  }
}
```

反馈指标（overview 与每个 by_workflow 项均含）：
- `rating_rate`：评价率（评价数/请求数）
- `satisfaction_rate`：好评率（好评数/评价数）
- `feedback_rate`：反馈率（含文字评论或纠错的反馈数/请求数）

---

#### `GET /metrics/timeseries`

按**分钟**分桶的时间序列，供折线图使用。

- **认证**：需要
- **查询参数**：
  - `workflow`（string, 必填, ≥1 字符）
  - `time_from` / `time_to`（可选，UTC）

**响应 200**

```json
{
  "workflow": "auto_film",
  "buckets": ["2026-07-10 03:18", "2026-07-10 03:19"],
  "workflow_series": {
    "requests": [2, 1],
    "avg_ms": [3300.0, 2900.0],
    "p95_ms": [7100.0, 5200.0],
    "active_sessions": [2, 1],
    "feedback_up": [1, 0],
    "feedback_down": [0, 1],
    "satisfaction": [1.0, 0.0]
  },
  "nodes": {
    "search_kb": { "requests": [2, 1], "avg_ms": [80.0, 75.0], "p95_ms": [120.0, 90.0] }
  },
  "tools": {
    "rag_search": { "requests": [2, 1], "avg_ms": [80.0, 75.0], "p95_ms": [120.0, 90.0] }
  }
}
```

各序列数组与 `buckets` 对齐（缺失延迟为 `null`，缺失计数为 `0`）。

---

#### `GET /metrics/rag`

RAG 检索质量概览（平均分、按 collection/source 分布）。

- **认证**：需要
- **查询参数**：`workflow` / `time_from` / `time_to`（全部可选）

**响应 200**

```json
{
  "overview": { "total_chunks": 120, "avg_score": 0.65, "min_score": 0.30, "max_score": 0.92 },
  "by_collection": [
    { "collection": "car_films", "chunks": 80, "avg_score": 0.66, "max_score": 0.92 }
  ],
  "by_source": [
    { "source": "COMPREHENSIVE_KNOWLEDGE_BASE.md", "chunks": 50, "avg_score": 0.68 }
  ]
}
```

---

#### `GET /metrics/feedback`

列出用户反馈（JOIN query/reply 上下文），供运营/训练审阅。

- **认证**：需要
- **查询参数**：
  - `rating`（`up`/`down`，可选）
  - `workflow`（可选）
  - `limit`（默认 200）

**响应 200**

```json
{
  "feedback": [
    {
      "id": 1,
      "chat_id": "chat_x",
      "turn_id": 0,
      "rating": "down",
      "comment": "答非所问",
      "correction": "应介绍产品",
      "created_at": "2026-07-10 03:18:55",
      "workflow_name": "auto_film",
      "query": "隔热膜贵不贵",
      "reply": "..."
    }
  ],
  "count": 1
}
```

---

#### `POST /metrics/retention`

数据保留：删除 `created_at` 早于 `now - days` 的历史记录。

- **认证**：需要
- **查询参数**：`days`（int, 必填, ≥1）

**响应 200**

```json
{ "status": "ok", "cutoff": "2026-04-11 03:20:00", "deleted_runs": 128 }
```

---

### 知识库（Collections）

#### `GET /collections`

列出所有 Qdrant 集合。

- **认证**：需要

**响应 200**

```json
{ "collections": ["car_films", "l2_auto", "default"] }
```

---

#### `GET /collections/{name}`

集合详情（向量维度、点数、配置等）。

- **认证**：需要
- **错误**：`404` 不存在

---

#### `GET /collections/{name}/count`

集合内文档数量。

- **认证**：需要
- **错误**：`404` 不存在

**响应 200**

```json
{ "collection": "car_films", "count": 21 }
```

---

#### `GET /collections/{name}/browse`

分页浏览集合内文档点。

- **认证**：需要
- **查询参数**：`limit` (默认 20) / `offset` (默认 0)

**响应 200**

```json
{
  "collection": "car_films",
  "points": [
    {
      "id": 8012014300849,
      "payload": {
        "source": "COMPREHENSIVE_KNOWLEDGE_BASE.md",
        "text": "五大核心卖点\n1. 紫外线阻隔率 > 99% …",
        "total_chunks": 21,
        "chunk_index": 7
      }
    }
  ],
  "next_offset": 23273498938123
}
```

---

#### `GET /collections/{name}/search`

**语义检索**（Dense 向量 + BM25 混合，RRF 融合）。

- **认证**：需要
- **查询参数**：
  - `q`（string, 必填, ≥1 字符）
  - `limit`（int, 默认 10）
- **错误**：`400` 检索失败（集合不存在/嵌入服务不可用等）

**响应 200**

```json
{
  "collection": "car_films",
  "query": "隔热膜",
  "points": [
    {
      "id": 48224948645350,
      "score": 0.6217,
      "text": "行业标准参数（全员必背）……",
      "source": "COMPREHENSIVE_KNOWLEDGE_BASE.md"
    }
  ]
}
```

---

#### `DELETE /collections/{name}`

删除整个集合。

- **认证**：需要
- **错误**：`404` 不存在

**响应 200**

```json
{ "status": "deleted", "collection": "car_films" }
```

---

#### `DELETE /collections/{name}/points`

按 ID 批量删除点。

- **认证**：需要

**请求体** (`application/json`)

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `ids` | list[int] | ✅ | 要删除的点 ID 列表（至少 1 个） |

- **错误**：`400` 删除失败

```bash
curl -X DELETE "http://<HOST>:9000/collections/car_films/points" \
  -H "Content-Type: application/json" -H "X-API-Key: <KEY>" \
  -d '{"ids":[1,2,3]}'
```

---

### 文档入库

用于构建/更新知识库。所有请求均可通过 `rebuild=true` 先删除目标集合再重建。

#### `POST /documents/upload`

上传单个文档并入库（自动分块 + 向量化）。

- **认证**：需要
- **Content-Type**：`multipart/form-data`

**表单字段**

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `file` | file | — (必填) | 支持 `.txt/.md/.pdf/.docx/.csv/.xlsx/.html` |
| `collection` | string | `default` | 目标集合 |
| `chunk_size` | int | 800 | 分块字符数 |
| `chunk_overlap` | int | 64 | 块间重叠字符数 |
| `rebuild` | bool | false | `true` 时先删除该集合再重建 |

**响应 200**

```json
{
  "status": "ok",
  "file": "产品介绍.md",
  "collection": "car_films",
  "chunks": 12,
  "rebuilt": false
}
```

```bash
curl -X POST "http://<HOST>:9000/documents/upload" -H "X-API-Key: <KEY>" \
  -F "file=@产品介绍.md" -F "collection=car_films" -F "chunk_size=800"
```

---

#### `POST /documents/scan`

扫描服务器上的目录批量入库。

- **认证**：需要
- **Content-Type**：`multipart/form-data` 或 `application/x-www-form-urlencoded`

**表单字段**

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `directory` | string | `data/documents` | 服务器上的目录路径 |
| `collection` | string | `default` | 目标集合 |
| `chunk_size` | int | 800 | 分块字符数 |
| `chunk_overlap` | int | 64 | 块间重叠字符数 |
| `rebuild` | bool | false | `true` 时先删除该集合再重建 |

- **错误**：`400` 目录不存在

**响应 200**

```json
{
  "status": "ok",
  "directory": "data/documents",
  "collection": "car_films",
  "chunks": 48,
  "rebuilt": true
}
```

---

### 数据导出

#### `GET /export/training.jsonl`

导出训练样本（`query → reply` + 反馈）为 JSONL，供微调/纠错数据筛选使用。

- **认证**：需要
- **查询参数**

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `workflow` | string | — | 按工作流过滤（可选） |
| `status` | string | `ok` | 轮次状态：`ok`/`error` |
| `limit` | int | 1000 | 最大导出条数 |
| `only_feedback` | string | — | 仅导出特定反馈：`up`/`down`（可选） |

**响应**：`application/x-ndjson`，每行一个 JSON 对象：

```json
{"chat_id":"chat_x","turn_id":0,"workflow_name":"auto_film","query":"隔热膜贵不贵","reply":"…","created_at":"2026-07-10 03:18:55","feedback_rating":"down","feedback_comment":"答非所问","feedback_correction":"应介绍产品"}
```

---

#### `POST /export/chat.xlsx`

将客户端持有的聊天记录导出为 Excel（`.xlsx`）。服务端生成二进制文件流。

- **认证**：需要

**请求体** (`application/json`)

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `messages` | list[ChatMessage] | `[]` | 聊天记录列表 |
| `filename` | string | `chat_history` | 导出文件名（不含扩展名） |

每条 `ChatMessage`：

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `role` | string | ✕ | 角色（如 `user`/`assistant`） |
| `content` | string | ✕ | 消息内容 |
| `ts` | string | ✕ | 时间戳 |
| `feedback` | string | ✕ | 评价（`up`/`down`） |
| `comment` | string | ✕ | 评论 |
| `correction` | string | ✕ | 纠错答案 |

- **响应**：`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`，`Content-Disposition: attachment`
- **导出列**：`role, content, timestamp, feedback, comment, correction`

**请求示例**

```json
{
  "messages": [
    { "role": "user", "content": "你好", "ts": "10:00:00" },
    { "role": "assistant", "content": "您好，有什么可以帮您", "ts": "10:00:01",
      "feedback": "down", "comment": "答非所问", "correction": "应介绍产品" }
  ],
  "filename": "chat_history"
}
```

---

#### `POST /export/chat.csv`

将客户端持有的聊天记录导出为 CSV（UTF-8 BOM，Excel 友好）。请求体与 `chat.xlsx` 相同。

- **认证**：需要
- **响应**：`text/csv; charset=utf-8`，`Content-Disposition: attachment`
- **导出列**：`role, content, timestamp, feedback, comment, correction`

---

## 数据模型

### RunRequest（对话请求体）

```ts
{
  query: string;           // 必填，≥1 字符
  chat_id?: string;        // 续接会话
  long_mem_data?: string;  // 客户端长期记忆
}
```

### RunResponse（阻塞模式响应）

```ts
{ chat_id: string; turn_id: number; reply: string; }
```

### RegenerateRequest

```ts
{ chat_id: string; }  // 必填
```

### FeedbackRequest

```ts
{
  rating: string;       // 必填，"up" | "down"
  comment?: string;     // 可选评论
  correction?: string;  // 可选纠错答案
}
```

### SessionMetaRequest

```ts
{
  title?: string;
  tags?: string[];
}
```

### ChatExportRequest

```ts
{
  messages: Array<{
    role: string;
    content: string;
    ts?: string;
    feedback?: string;
    comment?: string;
    correction?: string;
  }>;
  filename: string;  // 默认 "chat_history"
}
```

### DeletePointsRequest

```ts
{ ids: number[]; }  // 至少 1 个元素
```

### SSE 事件类型

```ts
{ event: "status"; node: "start"; workflow: string }
{ event: "token";  data: string }
{ event: "done";   chat_id: string; turn_id: number; reply: string }
{ event: "error";  data: string }
```

### Turn（轮次记录）

```ts
{
  run_id: number;
  turn_id: number;
  workflow_name: string;
  query: string;
  reply: string;
  node_count: number;
  duration_ms: number;
  status: "ok" | "error";
  error_message: string | null;
  prompt_tokens: number;
  completion_tokens: number;
  created_at: string;  // UTC
}
```

### NodeLog（节点执行）

```ts
{
  node_log_id: number;
  node_name: string;
  tool_name: string;
  input_data: string | null;   // JSON 字符串
  output_text: string;          // JSON 字符串（工具返回）
  duration_ms: number;
  status: "ok" | "error";
  error_message: string | null;
  created_at: string;  // UTC
}
```

---

## 端点速查

### 外部 API（/api/v1/*）

| 方法 | 路径 | 认证 | 用途 |
|------|------|:---:|------|
| GET | `/api/v1/health` | ✕ | 外部健康探针 |
| GET | `/api/v1/workflows` | ✓ | 工作流列表 |
| GET | `/api/v1/workflows/{name}` | ✓ | 工作流详情（DAG 拓扑 + 节点配置） |
| POST | `/api/v1/workflows/{name}/run` | ✓ | **执行工作流（阻塞/SSE）** |
| POST | `/api/v1/workflows/{name}/regenerate` | ✓ | 重新生成最后一轮回答 |
| GET | `/api/v1/sessions` | ✓ | 会话搜索（多条件过滤 + 分页） |
| GET | `/api/v1/sessions/filters` | ✓ | 搜索下拉候选 |
| GET | `/api/v1/sessions/{chat_id}` | ✓ | 会话轮次列表 |
| GET | `/api/v1/sessions/{chat_id}/meta` | ✓ | 会话元信息（标题/标签） |
| PATCH | `/api/v1/sessions/{chat_id}/meta` | ✓ | 更新会话标题/标签 |
| GET | `/api/v1/sessions/{chat_id}/turns/{turn_id}` | ✓ | 轮次节点详情 + RAG 记录 |
| GET | `/api/v1/sessions/{chat_id}/turns/{turn_id}/nodes/{node_name}` | ✓ | 节点工具调用详情 |
| POST | `/api/v1/sessions/{chat_id}/turns/{turn_id}/feedback` | ✓ | 提交反馈 👍/👎 |
| GET | `/api/v1/sessions/{chat_id}/turns/{turn_id}/feedback` | ✓ | 查询反馈 |
| DELETE | `/api/v1/sessions/{chat_id}` | ✓ | 删除会话 |
| GET | `/api/v1/usage` | ✓ | 用量/配额统计 |

### 内部 API（仅运维/管理）

| 方法 | 路径 | 认证 | 用途 |
|------|------|:---:|------|
| GET | `/health` | ✕ | 存活探针 |
| GET | `/ready` | ✕ | 就绪探针 |
| GET | `/status` | ✓ | 结构化系统健康 |
| GET | `/metrics` | ✓ | Prometheus 指标 |
| POST | `/reload` | ✓ | 热重载配置 |
| GET | `/metrics/summary` | ✓ | 仪表盘聚合 |
| GET | `/metrics/timeseries` | ✓ | 时间序列图表 |
| GET | `/metrics/rag` | ✓ | RAG 检索质量概览 |
| GET | `/metrics/feedback` | ✓ | 反馈审阅列表 |
| POST | `/metrics/retention` | ✓ | 数据保留清理 |
| GET | `/collections` | ✓ | 集合列表 |
| GET | `/collections/{name}` | ✓ | 集合详情 |
| GET | `/collections/{name}/count` | ✓ | 文档计数 |
| GET | `/collections/{name}/browse` | ✓ | 分页浏览 |
| GET | `/collections/{name}/search` | ✓ | 语义检索 |
| DELETE | `/collections/{name}` | ✓ | 删除集合 |
| DELETE | `/collections/{name}/points` | ✓ | 批量删点 |
| POST | `/documents/upload` | ✓ | 上传入库（multipart） |
| POST | `/documents/scan` | ✓ | 目录扫描入库 |
| GET | `/export/training.jsonl` | ✓ | 导出训练数据 |
| POST | `/export/chat.xlsx` | ✓ | 导出聊天记录 Excel |
| POST | `/export/chat.csv` | ✓ | 导出聊天记录 CSV |
