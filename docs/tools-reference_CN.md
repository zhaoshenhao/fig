# KF 工具参考与开发指南

[English](tools-reference_EN.md)

---

## 目录

- [Part 1: 内置工具 (10 个)](#part-1-内置工具-10-个)
  - [1. llm — LLM 调用](#1-llm--llm-调用)
  - [2. rag_search — 向量库检索](#2-rag_search--向量库检索)
  - [3. router — 条件路由](#3-router--条件路由)
  - [4. merge — 并行分支合并](#4-merge--并行分支合并)
  - [5. db_query — 数据库查询](#5-db_query--数据库查询)
  - [6. extract_llm — LLM 信息提取](#6-extract_llm--llm-信息提取)
  - [7. extract_regex — 正则提取](#7-extract_regex--正则提取)
  - [8. api_call — 外部 API 调用](#8-api_call--外部-api-调用)
  - [9. web_search — 网页搜索](#9-web_search--网页搜索)
  - [10. code — 安全代码执行](#10-code--安全代码执行)
- [Part 2: 工具返回值通用协议](#part-2-工具返回值通用协议)
- [Part 3: 工具注册](#part-3-工具注册)
- [Part 4: CLI 工具](#part-4-cli-工具)
  - [文档入库 — `python -m src.cli.build`](#文档入库--python--m-srcclibuild)
  - [知识库管理 — `python -m src.cli.manage`](#知识库管理--python--m-srcclimanage)
  - [工作流校验 — `python -m src.cli.validate_workflow`](#工作流校验--python--m-srcclivalidate_workflow)
- [Part 5: 工具开发指南](#part-5-工具开发指南)
  - [工具签名](#工具签名)
  - [创建新工具](#创建新工具)
  - [Session 对象使用要点](#session-对象使用要点)
  - [模板变量替换](#模板变量替换)
  - [日志与指标](#日志与指标)
  - [编写测试](#编写测试)
  - [开发检查清单](#开发检查清单)
  - [禁止事项](#禁止事项)

---

## Part 1: 内置工具 (10 个)

系统内置 10 个工具 (Tool)，在工作流节点 YAML 中通过 `tool` 字段指定。

### 1. llm — LLM 调用

**功能**: 调用 LLM 生成回复，注入对话历史、上下文和 session 变量。支持流式输出（SSE）。

**调用格式**: `tool: llm`

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `llm_provider` | str | 否 | LLM 供应商名 (config/auth.yaml 中的 provider key)，省略则用 default |
| `system_prompt` | str | 是 | 系统提示词，支持 `{{query}}`, `{{context}}`, `{{data_map}}`, `{{long_mem}}`, `{{history}}` 占位符 |

**模板占位符**:

| 占位符 | 说明 |
|--------|------|
| `{{query}}` | 当前用户输入文本 |
| `{{context}}` | 上游节点输出文本 (next_type=one 的前驱节点 data.text) |
| `{{data_map}}` | session.data_map (JSON 序列化) |
| `{{long_mem}}` | 客户端传入的长期记忆文本 |
| `{{history}}` | 对话历史格式化文本 (用户: ...\n客服: ...) |

**返回值**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `text` | str | LLM 生成的文本回复 |
| `model` | str | 使用的模型名 |
| `usage` | dict | token 用量 (非流式模式)，含 `prompt_tokens`, `completion_tokens` |

**流式输出**: 当 session 对象设置 `stream_callback` 属性时，llm_tool 调用 `LLMClient.stream_chat()` 逐 token 推送文本。回调签名为 `fn(token: str) -> None`。非流式模式使用 `LLMClient.chat()` 阻塞调用。

**node 配置示例**:

```yaml
# generate_answer.yaml
tool: llm
llm_provider: deepseek
system_prompt: |
  你是 {{query}} 领域的智能客服专家。
  参考以下上下文回答用户问题。

  上下文: {{context}}
  历史对话: {{history}}
```

---

### 2. rag_search — 向量库检索

**功能**: 将用户输入向量化后检索 Qdrant 向量库，返回相关文档片段。支持混合检索 (Dense Cosine + Sparse BM25 + RRF 融合)。

**调用格式**: `tool: rag_search`

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `embed_provider` | str | 否 | Embedding 供应商名 |
| `collection` | str\|list | 否 | 检索集合，省略则取 workflow 配置的 collections (collection inheritance from workflow.yaml) |
| `limit` | int | 否 | 返回结果数，默认 10 |
| `score_threshold` | float | 否 | 分数阈值过滤 |
| `prefetch_limit` | int | 否 | 混合检索预取数 (RRF 融合前的候选集大小)，默认 20 |

**多集合合并逻辑**: 当 `collection` 为列表或多个集合时，逐一检索后将结果合并，按 score 降序排序，截取 top-N。

**集合继承**: 当未指定 `collection` 时，根据 session._workflow 从全局配置中查找该工作流关联的集合列表；若未配置则回退到 `default`。

**返回值**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `text` | str | 拼接后的文档片段文本 (双换行分隔) |
| `chunks` | list[str] | 文档片段列表 |
| `results` | list[dict] | 原始结果 (含 id/score/payload) |

**node 配置示例**:

```yaml
# search_kb.yaml
tool: rag_search
collection: faq_kb
limit: 5
score_threshold: 0.5
```

---

### 3. router — 条件路由

**功能**: 根据规则匹配上游节点输出，返回分支名。配合 `next_type: if-then` 实现条件分支。

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
| `match` | str | 匹配模式: `exact` (精确，忽略大小写/空白) \| `contains` (包含) \| `startswith` (前缀) |

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

### 4. merge — 并行分支合并

**功能**: 合并 `switch` + `parallel: true` 的多条并行分支结果。此工具由 DAG 引擎内部调用，**不在 node YAML 中配置**。

**触发条件**: workflow.yaml 中 `next_type: switch` 且 `parallel: true`

**工作方式**:
1. 为每个分支节点标记来源分支 (`_branch` 字段)，设置父节点 (`pre` 字段)
2. 按 `timestamp` 升序排序所有分支节点
3. 将所有分支节点追加到 session.nodes 末尾
4. 在 switch 节点上记录各分支的起止索引范围 (`branches` 字段)

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

### 5. db_query — 数据库查询

**功能**: 执行 SQL 查询，返回格式化结果。

**前置条件**: `config/db.yaml` 中需要配置连接池。

**调用格式**: `tool: db_query`

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `db` | str | 是 | 数据库池名 (config/db.yaml 中的 key) |
| `query` | str | 是 | SQL 模板，支持 `{{query}}`, `{{data_map:key}}` 占位符 |
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
db: mysql_main
query: |
  SELECT order_id, status, amount
  FROM orders
  WHERE customer_id = {{data_map:customer_id}}
  ORDER BY created_at DESC
  LIMIT 10
limit: 20
```

---

### 6. extract_llm — LLM 信息提取

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
| `description` | str | 字段描述 (用于构造 prompt) |

**返回值**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `text` | str | "extracted N fields" 消息 |
| `extracted` | list[str] | 提取到的字段 key 列表 |

**node 配置示例**:

```yaml
# extract_info.yaml
tool: extract_llm
llm_provider: deepseek
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

### 7. extract_regex — 正则提取

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
# extract_contact.yaml
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

### 8. api_call — 外部 API 调用

**功能**: 发送 HTTP 请求到外部 API，支持模板变量替换。

**调用格式**: `tool: api_call`

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `url` | str | 是 | 请求 URL，支持 `{{query}}`, `{{chat_id}}`, `{{data_map:key}}` 占位符 |
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

### 9. web_search — 网页搜索

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

### 10. code — 安全代码执行

**功能**: 在受限沙箱中执行 Python 代码，阻断了危险 import。

**调用格式**: `tool: code`

**允许的 import**: `json`, `math`, `datetime`, `collections`, `itertools`, `functools`, `re`, `statistics`, `decimal`, `fractions`, `hashlib`, `base64`, `uuid`, `random`, `string`, `textwrap`

**阻止的 import**: `os`, `subprocess`, `sys`, `shutil` 等所有可能访问文件系统或执行外部命令的模块。

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `code` | str | 是 | Python 代码，支持 `{{query}}`, `{{data_map:key}}` 占位符 |
| `language` | str | 否 | 语言，默认 python |
| `timeout` | int | 否 | 超时秒数 (预留)，默认 10 |

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
  import json
  amount = float("{{data_map:order_amount}}")
  level = "{{data_map:vip_level}}"
  discount = 0.9 if level == "gold" else 0.95 if level == "silver" else 1.0
  final = round(amount * discount, 2)
  print(json.dumps({"amount": amount, "discount": discount, "final": final}))
```

---

## Part 2: 工具返回值通用协议

所有工具函数签名: `fn(config: dict, session: SessionData) -> dict | str`

- 返回 `dict` 时，**必须**包含 `"text"` 字段 (输出到下游节点的 data.text 和最终 reply)
- 返回 `str` 时，自动包装为 `{"text": str, "branch": str}`
- 额外字段会自动传递到下游节点的 `session.data` 中（如 `rows`, `results`, `status_code` 等）

---

## Part 3: 工具注册

工具通过两个位置注册，需保持同步：

### 1. 在 `src/api/main.py` 中通过 `ToolRegistry` 注册

```python
from src.engine.tools import api_call, code, db_query, extract_llm, extract_regex
from src.engine.tools import llm_tool, rag_search, router, web_search

_registry.register("llm", llm_tool)
_registry.register("rag_search", rag_search)
_registry.register("router", router)
_registry.register("db_query", db_query)
_registry.register("extract_llm", extract_llm)
_registry.register("extract_regex", extract_regex)
_registry.register("api_call", api_call)
_registry.register("web_search", web_search)
_registry.register("code", code)
```

### 2. 在 `src/engine/dag.py` 的 `_register_builtins()` 中注册

```python
def _register_builtins(registry: ToolRegistry) -> None:
    from src.engine.tools import (
        api_call, code, db_query, extract_llm, extract_regex,
        llm_tool, rag_search, router, web_search,
    )
    registry.register("llm", llm_tool)
    registry.register("rag_search", rag_search)
    # ... 其余工具同理
```

**注意**: node YAML 中的 `tool` 字段值必须匹配注册名 (如 `tool: rag_search`)。

---

## Part 4: CLI 工具

KF 提供 3 个命令行工具：文档入库、知识库管理、工作流校验。

### 文档入库 — `python -m src.cli.build`

扫描目录中的文档文件，分块、向量化、写入 Qdrant。

**参数**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--dir` | str | `data/documents` | 源文件目录路径 |
| `--collection` | str | `default` | 目标 Qdrant 集合名 |
| `--chunk-size` | int | `800` | 分块字符数（按字符计，中文友好） |
| `--chunk-overlap` | int | `128` | 相邻块重叠字符数 |
| `--qdrant-host` | str | `localhost` | Qdrant 主机地址 |
| `--qdrant-port` | int | `6334` | Qdrant gRPC 端口 |
| `--ollama-url` | str | `http://localhost:11434/v1` | Ollama 地址 |
| `--embed-model` | str | `nomic-embed-text` | 嵌入模型名 |
| `--extensions` | str | (空) | 逗号分隔的扩展名。空 = 自动检测全部支持格式 |

**支持格式**:

| 格式 | 扩展名 | 依赖 |
|------|--------|------|
| 纯文本 | `.txt` | 无 |
| Markdown | `.md` | 无 |
| PDF | `.pdf` | `pip install pymupdf` |
| Word | `.docx` | `pip install python-docx` |
| Excel | `.xlsx` | `pip install openpyxl` |
| CSV | `.csv` | 无 |
| HTML | `.html` `.htm` | 无 |

**使用示例**:

```bash
# 基础用法：自动检测所有格式，导入到 default 集合
python -m src.cli.build

# 指定目录和集合名
python -m src.cli.build --dir data/faq_docs --collection faq_kb

# 自定义分块大小（小文本推荐）
python -m src.cli.build --dir data/kb --collection kb --chunk-size 400 --chunk-overlap 64

# 自定义分块大小（长文档推荐）
python -m src.cli.build --dir data/manuals --collection manuals --chunk-size 1500 --chunk-overlap 200

# 仅导入 Markdown 和 PDF
python -m src.cli.build --extensions .md,.pdf

# 指定远程 Qdrant 和 Ollama
python -m src.cli.build \
  --qdrant-host 10.0.0.5 --qdrant-port 6334 \
  --ollama-url http://gpu-server:11434/v1 \
  --embed-model nomic-embed-text
```

**分块策略指南**:

| 场景 | chunk_size | chunk_overlap | 说明 |
|------|-----------|---------------|------|
| FAQ 短问答 | 200-400 | 50 | 短文本，小 chunk 精度高 |
| 产品文档 | 800 | 128 | **默认值**，中文通用 |
| 技术手册 | 1000-1500 | 200 | 长段落，保留更多上下文 |
| 法律合同 | 500-800 | 100 | 精确段落级切分 |

> chunk_size 按**字符数**计算 (`len(text)`)，非单词数。对中英文均友好。

---

### 知识库管理 — `python -m src.cli.manage`

管理 Qdrant 中的集合和文档。

**全局参数**: `--qdrant-host` `--qdrant-port` 在所有子命令中可用。

| 子命令 | 说明 | 可选参数 |
|--------|------|----------|
| `list` | 列出所有集合 | `--qdrant-host`, `--qdrant-port` |
| `info <name>` | 集合详情 (点数、维度、配置) | 同上 |
| `count <name>` | 集合点数统计 | 同上 |
| `browse <name>` | 分页浏览集合内容 | `--limit 20`, `--offset 0`, `--all` |
| `search <name> <query>` | 语义检索集合 | `--limit 5`, `--ollama-url`, `--embed-model`, `--score-threshold` |
| `delete <name>` | 删除集合 (交互确认) | `--yes` / `-y` 跳过确认 |

**使用示例**:

```bash
# 列出所有集合
python -m src.cli.manage list
# 输出:
# kb
# faq_kb
# l2_test

# 集合详情
python -m src.cli.manage info kb
# 输出: { "name": "kb", "points_count": 342, "vectors_count": 342, ... }

# 文档总数
python -m src.cli.manage count kb
# 输出: kb: 342 points

# 分页浏览
python -m src.cli.manage browse kb --limit 10       # 查看前 10 条
python -m src.cli.manage browse kb --limit 10 --offset 20  # 从第 20 条开始
python -m src.cli.manage browse kb --limit 20 --all         # 遍历全部

# 语义搜索
python -m src.cli.manage search kb "退款政策"
python -m src.cli.manage search kb "产品价格" --limit 3
python -m src.cli.manage search kb "部署方式" --score-threshold 0.6

# 删除集合
python -m src.cli.manage delete test_kb         # 交互确认
python -m src.cli.manage delete test_kb --yes   # 跳过确认

# 远程连接
python -m src.cli.manage list --qdrant-host 10.0.0.5 --qdrant-port 6334
```

**Collections CRUD API**:

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/collections` | 列出所有集合名 |
| GET | `/collections/{name}` | 集合详情 (points_count, vectors_count, config) |
| GET | `/collections/{name}/count` | 点数统计 |
| GET | `/collections/{name}/browse?limit=20&offset=0` | 分页浏览集合内容 |
| DELETE | `/collections/{name}` | 删除整个集合 |
| DELETE | `/collections/{name}/points` | 按 ID 删除点，body: `{"ids": [1, 2, 3]}` |

```bash
# API 示例
curl http://localhost:9000/collections
curl http://localhost:9000/collections/my_kb
curl "http://localhost:9000/collections/my_kb/browse?limit=10&offset=0"
curl -X DELETE http://localhost:9000/collections/my_kb
```

---

### 工作流校验 — `python -m src.cli.validate_workflow`

校验工作流定义的正确性。

**用法**:

```bash
# 校验单个工作流
python -m src.cli.validate_workflow config/workflows/customer_service/workflow.yaml

# 校验产品目录 (自动查找目录下的 workflow.yaml)
python -m src.cli.validate_workflow config/workflows/customer_service

# 显示详细校验过程
python -m src.cli.validate_workflow config/workflows/default --verbose

# 批量校验所有工作流
for d in config/workflows/*/; do
    python -m src.cli.validate_workflow "$d"
done
```

**校验项目**:

| 检查项 | 说明 |
|--------|------|
| 文件存在 | workflow.yaml + nodes/*.yaml 路径有效 |
| 节点名唯一 | 无重名节点 |
| next_type 合法 | 必须为 `one` `if-then` `switch` 之一 |
| 节点引用有效 | next 引用的节点在 nodes 中已定义 |
| 无孤立节点 | 除终止节点外，每个节点都能从起始节点到达 |
| 无死胡同 | 除终止节点外，每个节点都有后继 (next 非空) |

**输出示例**:

```
PASS: workflow 'customer_service' (5 nodes, 0 errors)
```

```
FAIL: workflow 'customer_service' (5 nodes, 2 errors)
  ERROR: node 'missing_handler' referenced but not found in nodes/
  ERROR: node 'orphan_node' is unreachable from start
```

---

## Part 5: 工具开发指南

### 工具签名

所有工具遵循统一的函数签名:

```python
def my_tool(config: dict, session: SessionData) -> dict:
    ...
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `config` | dict | 节点 YAML 中的全部配置 (含 tool, llm_provider 等所有字段) |
| `session` | SessionData | 当前会话对象，可读写 data_map, long_mem_data, history, nodes 等 |

**返回值**: `dict` (**必须**包含 `"text"` 字段) 或 `str` (自动包装为 `{"text": ..., "branch": ...}`)

---

### 创建新工具

#### 步骤 1: 创建工具文件

在 `src/engine/tools/` 下创建 `my_tool.py`:

```python
# src/engine/tools/my_tool.py

from src.session.data import SessionData


def my_tool(config: dict, session: SessionData) -> dict:
    param1 = config.get("param1", "default_value")
    param2 = config.get("param2", 10)

    user_query = session.current_query          # 当前用户输入
    previous_data = session.current_context      # 上游节点输出文本
    stored_kv = session.data_map                 # 跨节点 data_map

    result_text = f"processed: {user_query} with {param1}"

    session.data_map["my_result"] = result_text   # 写入跨节点共享变量

    return {
        "text": result_text,
        "extra_field": param2,                    # 额外字段传递给下游
    }
```

#### 步骤 2: 在 `__init__.py` 中添加导出

```python
# src/engine/tools/__init__.py

from .my_tool import my_tool

__all__ = [..., "my_tool"]
```

如果工具导入了 `httpx2` 或 `LLMClient` 等重量级依赖，使用 **延迟导入包装器** 避免启动时级联导入:

```python
# 延迟导入包装器 (避免 httpx2 级联加载)
def my_tool(config: dict, session) -> dict:
    from .my_tool import my_tool as _fn
    return _fn(config, session)
```

#### 步骤 3: 在 `dag.py` 的 `_register_builtins()` 中注册

```python
# src/engine/dag.py

def _register_builtins(registry: ToolRegistry) -> None:
    from src.engine.tools import (
        ...,
        my_tool,        # 新增
    )
    registry.register("my_tool", my_tool)
```

#### 步骤 4: 在 `api/main.py` 中注册

```python
# src/api/main.py

from src.engine.tools import (
    ...,
    my_tool,            # 新增
)
_registry.register("my_tool", my_tool)
```

#### 步骤 5: 在工作流中使用

创建 node YAML:

```yaml
# config/workflows/my_product/nodes/my_node.yaml
tool: my_tool
param1: "custom_value"
param2: 42
```

在 workflow.yaml 中引用:

```yaml
# config/workflows/my_product/workflow.yaml
nodes:
  - name: my_node
    next_type: one
    next: ""       # "" 表示终止节点
```

---

### Session 对象使用要点

```python
session = SessionData()

# 读取当前轮次输入
query = session.current_query              # → "用户输入文本"
context = session.current_context          # → 上游节点 data.text

# 读写跨节点共享变量
session.data_map["order_id"] = "12345"     # 写入
order = session.data_map.get("order_id")   # 读取

# 读取客户端传入的长期记忆
long_mem = session.long_mem_data           # → str

# 遍历对话历史 (TurnRecord 列表)
for turn in session.history:
    print(turn.input, turn.output)

# 读取会话元信息
session.chat_id                            # → "chat_abc123..."
session.turn_id                            # → 当前轮次号
session._workflow                          # → 工作流名
```

---

### 模板变量替换

多个工具支持 `{{variable}}` 模板语法。推荐实现 `_resolve()` 辅助函数:

```python
def _resolve(template: str, session: SessionData) -> str:
    result = template.replace("{{query}}", session.current_query)
    result = result.replace("{{chat_id}}", session.chat_id)
    for key, val in session.data_map.items():
        result = result.replace(f"{{{{{key}}}}}", f"{{data_map:{key}}}")  # 兼容
        result = result.replace(f"{{data_map:{key}}}", str(val))
    return result
```

---

### 日志与指标

**结构化日志**:

```python
from src.logger import get_logger

_log = get_logger(__name__)

def my_tool(config: dict, session: SessionData) -> dict:
    _log.info("my_tool start", extra={"param": config.get("key")})
    try:
        ...
    except Exception as e:
        _log.error("my_tool failed", extra={"error": str(e)})
        return {"text": "", "error": str(e)}
```

**Prometheus 指标**:

```python
from src.metrics.prometheus import llm_calls_total

def my_tool(config: dict, session: SessionData) -> dict:
    # 计数器 (累计值)
    llm_calls_total.inc({"model": "my-model"})

    # 直方图 (分布值)
    from src.metrics.prometheus import rag_search_duration_ms
    import time
    t0 = time.time()
    result = do_work()
    rag_search_duration_ms.observe((time.time() - t0) * 1000)
```

---

### 编写测试

```python
# tests/test_my_tool.py

class TestMyTool:
    def test_basic(self):
        from src.engine.tools.my_tool import my_tool
        from src.session.data import SessionData

        config = {"param1": "test", "param2": 10}
        session = SessionData()
        session.nodes = [
            {"name": "input", "data": {"text": "hello"}},
        ]

        result = my_tool(config, session)
        assert result["text"] == "processed: hello with test"
        assert result["extra_field"] == 10

    def test_missing_params(self):
        from src.engine.tools.my_tool import my_tool
        from src.session.data import SessionData

        result = my_tool({}, SessionData())
        assert "text" in result  # 不应该崩溃
```

---

### 开发检查清单

```
□ 创建 src/engine/tools/my_tool.py
□ 函数签名: fn(config: dict, session: SessionData) -> dict
□ 返回 dict 包含 "text" 字段
□ 在 __init__.py 中导出 (或延迟导入包装器)
□ 在 dag.py _register_builtins() 注册
□ 在 api/main.py ToolRegistry 注册
□ 编写 tests/test_my_tool.py
□ 编写 docs 中的节点 YAML 配置示例
□ 运行 ruff + pytest 验证
```

---

### 禁止事项

```
□ 禁止在工具函数中直接使用 os.system / subprocess
□ 禁止在工具中修改 session.nodes (由引擎管理)
□ 禁止在模块顶层导入 httpx2 (使用函数内延迟导入)
□ 禁止返回 None 或不含 "text" 的 dict
```
