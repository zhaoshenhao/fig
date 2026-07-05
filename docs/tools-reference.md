# 工具参考

系统内置 10 个工具 (Tool)，在工作流节点 YAML 中通过 `tool` 字段指定。

---

## 1. llm — LLM 调用

**功能**: 调用 LLM 生成回复。注入对话历史、上下文和 session 变量。支持流式输出（SSE）。

**调用格式**: `tool: llm`

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `llm_provider` | str | 否 | LLM 供应商名 (config/llm.yaml 中的 key)，省略则用 default |
| `system_prompt` | str | 是 | 系统提示词，支持 `{{query}}`, `{{context}}`, `{{data_map}}`, `{{long_mem}}`, `{{history}}` 占位符 |

**返回值**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `text` | str | LLM 生成的文本 |
| `model` | str | 使用的模型名 |

**流式输出**: 当 session 对象设置 `stream_callback` 属性时，llm_tool 会调用 `LLMClient.stream_chat()` 逐 token 推送文本。回调签名为 `fn(token: str) -> None`。非流式模式仍使用 `LLMClient.chat()` 阻塞调用。

**node 配置示例**:
```yaml
# generate.yaml
tool: llm
llm_provider: ollama
system_prompt: |
  你是一个 {{query}} 领域的智能客服。
  参考上下文回答用户问题。

  上下文: {{context}}
  历史对话: {{history}}
```

**占位符说明**:
- `{{query}}` — 当前用户输入
- `{{context}}` — 上游节点的输出文本 (next_type=one 的前驱节点 data.text)
- `{{data_map}}` — session.data_map (JSON 序列化)
- `{{long_mem}}` — 客户端传入的长期记忆
- `{{history}}` — 对话历史文本 (用户: ...\n客服: ...)

---

## 2. rag_search — 向量库检索

**功能**: 将用户输入向量化后检索 Qdrant 向量库，返回相关文档片段。支持混合检索 (Dense + Sparse BM25 + RRF 融合)。

**调用格式**: `tool: rag_search`

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `embed_provider` | str | 否 | Embedding 供应商名 |
| `collection` | str\|list | 否 | 检索集合，省略则取 workflow 的 collections |
| `limit` | int | 否 | 返回结果数，默认 10 |
| `score_threshold` | float | 否 | 分数阈值过滤 |
| `prefetch_limit` | int | 否 | 混合检索预取数，默认 20 |

**返回值**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `text` | str | 拼接后的文档片段文本 |
| `chunks` | list[str] | 文档片段列表 |
| `results` | list[dict] | 原始结果 (含 id/score/payload) |

**node 配置示例**:
```yaml
# retrieve.yaml
tool: rag_search
collection: faq_knowledge_base
limit: 5
score_threshold: 0.5
```

---

## 3. router — 条件路由

**功能**: 根据规则匹配，返回分支名。配合 `next_type: if-then` 实现条件分支。

**调用格式**: `tool: router`

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `router.rules` | list | 是 | 规则列表 |
| `router.match_field` | str | 否 | 匹配字段，默认 "text" (上游节点输出) |
| `router.default` | str | 否 | 默认分支名 (无规则匹配时) |

**规则结构** (`router.rules[]`):

| 字段 | 类型 | 说明 |
|------|------|------|
| `branch` | str | 匹配后的目标分支节点名 |
| `value` | str | 匹配目标值 |
| `match` | str | 匹配模式: `exact` (精确字符串) \| `contains` (包含) \| `startswith` (前缀) |

**返回值**: `str` — 匹配的分支名 (或 default)

**node 配置示例**:
```yaml
# intent_classify.yaml
tool: router
router:
  match_field: text
  default: inquiry
  rules:
    - value: "投诉"
      match: contains
      branch: complaint
    - value: "订单"
      match: contains
      branch: order
    - value: "你好"
      match: startswith
      branch: greeting
```

**配合 workflow.yaml 使用**:
```yaml
# workflow.yaml
nodes:
  - name: intent_classify
    next_type: if-then
    next: [greeting, inquiry, complaint, order]
  - name: greeting
    next_type: one
    next: ""
  - name: inquiry
    next_type: one
    next: ""
  - name: complaint
    next_type: one
    next: ""
  - name: order
    next_type: one
    next: ""
```

---

## 4. merge — 并行分支合并

**功能**: 合并 `switch` + `parallel: true` 的多条并行分支结果。此工具由 DAG 引擎内部调用，**不在 node YAML 中配置**。

**触发条件**: workflow.yaml 中 `next_type: switch` 且 `parallel: true`

**排序策略**: 按 `timestamp` 升序合并

**返回值**: 每个分支的 `start/end` 索引写入 switch 节点的 `branches` 字段

```yaml
# workflow.yaml 中的 switch 并行节点
nodes:
  - name: dispatcher
    next_type: switch
    next: [branch_a, branch_b, branch_c]
    parallel: true
  - name: branch_a
    next_type: one
    next: ""
  - name: branch_b
    next_type: one
    next: ""
  - name: branch_c
    next_type: one
    next: ""
```

---

## 5. db_query — 数据库查询

**功能**: 执行 SQL 查询，返回格式化结果。

**前置条件**: `config/db.yaml` 中需要配置连接池。

**调用格式**: `tool: db_query`

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `db` | str | 是 | 数据库池名 (config/db.yaml 中的 key) |
| `query` | str | 是 | SQL 模板，支持 `{{query}}`, `{{data_map.key}}` 占位符 |
| `params` | list | 否 | 参数化查询参数列表 |
| `limit` | int | 否 | 返回行数上限，默认 50 |

**返回值**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `text` | str | 格式化表格文本 |
| `rows` | list[dict] | 查询结果行 |
| `db` | str | 数据库池名 |

**node 配置示例**:
```yaml
# order_query.yaml
tool: db_query
db: order_db
query: |
  SELECT order_id, status, amount
  FROM orders
  WHERE customer_id = {{data_map:customer_id}}
  ORDER BY created_at DESC
  LIMIT 10
limit: 20
```

---

## 6. extract_llm — LLM 信息提取

**功能**: 调用 LLM 从用户输入中提取结构化字段，结果存入 `session.data_map`。

**调用格式**: `tool: extract_llm`

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `extract` | list | 是 | 提取字段定义 |
| `llm_provider` | str | 否 | LLM 供应商名 |

**字段定义** (`extract[]`):

| 字段 | 类型 | 说明 |
|------|------|------|
| `key` | str | 字段名 (存入 data_map 的 key) |
| `description` | str | 字段描述 (用于 prompt) |

**返回值**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `text` | str | "extracted N fields" 消息 |
| `extracted` | list[str] | 提取到的字段 key 列表 |

**node 配置示例**:
```yaml
# extract_info.yaml
tool: extract_llm
llm_provider: ollama
extract:
  - key: customer_name
    description: 客户姓名
  - key: order_number
    description: 订单号
  - key: issue_type
    description: 问题类型 (退货/换货/退款/咨询)
```

**后续使用**: 提取的字段可在下游节点的 prompt 或 SQL 中通过 `{{data_map:customer_name}}` 引用。

---

## 7. extract_regex — 正则提取

**功能**: 用正则表达式从用户输入中提取字段，结果存入 `session.data_map`。

**调用格式**: `tool: extract_regex`

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `extract` | list | 是 | 提取规则列表 |

**字段定义** (`extract[]`):

| 字段 | 类型 | 说明 |
|------|------|------|
| `key` | str | 字段名 (存入 data_map 的 key) |
| `pattern` | str | 正则表达式 |

**返回值**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `text` | str | "matched N fields" 消息 |
| `extracted` | list[str] | 匹配到的字段 key 列表 |

**node 配置示例**:
```yaml
# extract_order.yaml
tool: extract_regex
extract:
  - key: phone
    pattern: "1[3-9]\\d{9}"
  - key: order_id
    pattern: "ORD-\\d{6}"
  - key: email
    pattern: "[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\\.[a-zA-Z0-9-.]+"
```

---

## 8. api_call — 外部 API 调用

**功能**: 发送 HTTP 请求到外部 API，支持模板变量替换。

**调用格式**: `tool: api_call`

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `url` | str | 是 | 请求 URL，支持 `{{query}}`, `{{chat_id}}`, `{{data_map.key}}` 占位符 |
| `method` | str | 否 | HTTP 方法，默认 GET |
| `headers` | dict | 否 | 请求头 (值支持模板替换) |
| `body` | dict | 否 | JSON 请求体 |
| `timeout` | int | 否 | 超时秒数，默认 30 |

**返回值**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `text` | str | 响应体 (截断 5000 字符) |
| `status_code` | int | HTTP 状态码 |
| `url` | str | 实际请求 URL |

**node 配置示例**:
```yaml
# order_api.yaml
tool: api_call
url: "https://api.example.com/v1/orders/{{data_map:order_number}}"
method: GET
headers:
  Authorization: "Bearer {{data_map:api_token}}"
  Content-Type: "application/json"
timeout: 10
```

---

## 9. web_search — 网页搜索

**功能**: 在线搜索，返回网页摘要。

**调用格式**: `tool: web_search`

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `engine` | str | 否 | 搜索引擎，默认 duckduckgo |
| `query_template` | str | 否 | 搜索词模板，默认 `{{query}}` |
| `limit` | int | 否 | 结果数上限，默认 5 |

**返回值**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `text` | str | 格式化摘要文本 |
| `results` | list[dict] | 原始结果 (title/url/snippet) |

**node 配置示例**:
```yaml
# web_lookup.yaml
tool: web_search
engine: duckduckgo
query_template: "{{query}} 最新政策"
limit: 3
```

---

## 10. code — 安全代码执行

**功能**: 在受限沙箱中执行 Python 代码，**阻断了危险 import** (os, subprocess, sys, shutil 等)。

**调用格式**: `tool: code`

**允许的 import**: json, math, datetime, collections, itertools, functools, re, statistics, decimal, fractions, hashlib, base64, uuid, random, string, textwrap

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `code` | str | 是 | Python 代码，支持 `{{query}}`, `{{data_map.key}}` 占位符 |
| `language` | str | 否 | 语言，默认 python |
| `timeout` | int | 否 | 超时秒数 (未实现，预留)，默认 10 |

**返回值**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `text` | str | 标准输出 (或错误信息) |
| `stdout` | str | 标准输出捕获 |
| `error` | str\|null | 错误信息 |

**node 配置示例**:
```yaml
# calc_discount.yaml
tool: code
code: |
  amount = float("{{data_map:order_amount}}")
  level = "{{data_map:vip_level}}"
  discount = 0.9 if level == "gold" else 0.95 if level == "silver" else 1.0
  final = round(amount * discount, 2)
  print(json.dumps({"amount": amount, "discount": discount, "final": final}))
```

---

---

## 知识库管理工具（独立 CLI + API）

知识库管理不属于工作流节点，是独立的命令行和 API 工具。

### CLI: `python -m src.cli.manage`

| 子命令 | 说明 | 可选参数 |
|--------|------|----------|
| `list` | 列出所有 Qdrant 集合 | `--qdrant-host`, `--qdrant-port` |
| `info <name>` | 集合详情 (点数、维度、配置) | 同上 |
| `count <name>` | 集合点数统计 | 同上 |
| `browse <name>` | 分页浏览集合内容 | `--limit 20`, `--offset 0`, `--all` |
| `search <name> <query>` | 语义检索集合 | `--limit 5`, `--ollama-url`, `--embed-model`, `--score-threshold` |
| `delete <name>` | 删除集合 (交互确认) | `--yes` 跳过确认 |

**使用示例**:
```bash
# 列出所有集合
python -m src.cli.manage list

# 查看集合详情
python -m src.cli.manage info my_kb

# 语义搜索
python -m src.cli.manage search my_kb "如何退款" --limit 3

# 分页浏览
python -m src.cli.manage browse my_kb --limit 10
```

### API: Collections CRUD

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/collections` | 列出所有集合名 |
| GET | `/collections/{name}` | 集合详情 (points_count, vectors_count, config) |
| GET | `/collections/{name}/count` | 点数统计 |
| GET | `/collections/{name}/browse?limit=20&offset=0` | 分页浏览集合内容 |
| DELETE | `/collections/{name}` | 删除整个集合 |
| DELETE | `/collections/{name}/points` | 按 ID 删除点，body: `{"ids": [1, 2, 3]}` |

**使用示例**:
```bash
# 列出集合
curl http://localhost:9000/collections

# 集合详情
curl http://localhost:9000/collections/my_kb

# 分页浏览 (第1页)
curl "http://localhost:9000/collections/my_kb/browse?limit=10&offset=0"

# 删除集合
curl -X DELETE http://localhost:9000/collections/my_kb
```

### QdrantSearch Python API

```python
from src.rag.qdrant import QdrantSearch

q = QdrantSearch()

# 管理
q.list_collections()                       # -> list[str]
q.collection_info("my_kb")                 # -> dict (points_count, vectors_count, config)
q.count("my_kb")                           # -> int
q.delete_collection("my_kb")               # -> True
q.delete_points("my_kb", [1, 2, 3])       # -> {"deleted": 3, "status": "completed"}

# 查询
q.scroll("my_kb", limit=20, offset=0)     # -> (list[dict], next_offset | None)
q.search("my_kb", vector, query_text="...") # -> list[dict] (id, score, payload)
```

---

## 工具返回值通用协议

所有工具函数签名: `fn(config: dict, session: SessionData) -> dict | str`

- 返回 `dict` 时，必须包含 `text` 字段 (输出到下游节点的 data.text 和最终 reply)
- 返回 `str` 时，自动包装为 `{"text": str, "branch": str}`
- 额外字段会自动传递到下游节点的 `session.data` 中

## 工具注册

工具通过 `src/api/main.py` 中的 `ToolRegistry` 注册:

```python
_registry.register("llm", llm_tool)
_registry.register("rag_search", rag_search)
_registry.register("router", router)
# ...
```

node YAML 中的 `tool` 字段值必须匹配注册名 (如 `tool: rag_search`)。
