# Workflow 设计规范

## 1. 目录结构

每个产品线一个独立子目录，包含自己的 workflow 编排和节点配置：

```
config/
├── llm.yaml               ← 聊天供应商
├── embed.yaml             ← 嵌入供应商
├── session.yaml           ← 会话存储配置
└── workflows/
    ├── default/           ← 产品线子目录
    │   ├── workflow.yaml  ← 编排：节点顺序 + 路由 + 知识库列表
    │   └── nodes/         ← 节点实现
    │       ├── retrieve.yaml
    │       └── generate.yaml
    └── product_b/         ← 另一个产品线
        ├── workflow.yaml
        └── nodes/
            └── ...
```

每产品线隔离：
- 独立的 workflow 编排（节点顺序、路由规则、控制参数）
- 独立的 node 配置（`nodes/{name}.yaml`）
- 独立的知识库列表（`collections` 字段控制 rag_search 查询范围）
- 全局共享：llm.yaml / embed.yaml / session.yaml（供应商 + 会话配置）

## 2. workflow.yaml 格式

```yaml
name: my_workflow
description: "产品说明"
collections:                   # 知识库列表（rag_search 默认查询这些集合）
  - faq
  - product_manual
return_mode: full             # full

conversation:                 # 可选，多轮对话配置
  max_turns: null             # null = 不限（另见 session.yaml 全局 max_turns）

nodes:
  - name: retrieve
    next_type: one
    next: generate
    metrics: true

  - name: generate
    next_type: one
    next: ""
    metrics: true
```

### 字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | 是 | 工作流名称（全局唯一） |
| `description` | 否 | 描述 |
| `collections` | 否 | 知识库列表，默认 `["default"]` |
| `return_mode` | 是 | `full` 返回完整会话 |
| `conversation` | 否 | 多轮对话配置 |
| `conversation.max_turns` | 否 | 历史最大轮数，null 不限 |
| `nodes[].name` | 是 | 节点名称 |
| `nodes[].next_type` | 是 | `one` / `if-then` / `switch` |
| `nodes[].next` | 是 | `one` 填字符串，`if-then`/`switch` 填列表 |
| `nodes[].metrics` | 是 | 是否采集性能数据 |
| `nodes[].parallel` | 否 | `switch` 时是否并行 |

## 3. 多知识库支持

### workflow 级定义

在 workflow.yaml 的 `collections` 字段列出该产品线涉及的知识库：

```yaml
collections:
  - faq
  - product_v2
  - internal_docs
```

### 节点级覆盖

在 retrieve.yaml 中可通过 `collection` 显式指定：

```yaml
tool: rag_search
collection: faq
limit: 10
```

```yaml
tool: rag_search
collection:
  - faq
  - product_v2
limit: 10
```

### 合并逻辑

1. 节点 `collection` 未指定 → 继承 workflow 的 `collections` 列表
2. 节点 `collection` 为字符串 → 查单个集合
3. 节点 `collection` 为列表 → 查多个集合，结果按 score 降序合并，取前 `limit` 条

## 4. Session 设计

### 4.1 数据结构

`src/session/data.py` — `SessionData` dataclass，支持 dict 兼容访问：

```python
@dataclass
class TurnRecord:
    input: str              # 用户输入
    output: str             # 系统回复
    input_timestamp: float
    output_timestamp: float

@dataclass
class SessionData:
    chat_id: str            # "chat_<uuid4.hex[:20]>"，仅创建时生成，唯一标识
    turn_id: int            # 从 0 开始，每轮 add_turn 后 +1
    created_at: float       # 创建时间戳
    last_active_at: float   # 每次 save() 时刷新
    _workflow: str          # 绑定的 workflow 名称（禁止混用）
    return_mode: str        # "full"
    history: list[TurnRecord]  # 跨轮次记忆 ← 会参与 trim / compress
    data_map: dict[str,str]    # 结构化数据，extract 工具写入，永不清除
    long_mem_data: str         # 长期记忆文本，client 传入一次，永不清除
    nodes: list[dict]          # 仅当前轮 DAG 执行日志，每轮结束后自动清除
```

**Dict 兼容**：实现 `__getitem__` / `__setitem__` / `get` / `__contains__` / `setdefault`。

### 4.2 职责划分

| 字段 | 用途 | 跨轮次 | 参与 trim | 返回 client |
|------|------|--------|-----------|------------|
| `history` | 多轮对话记忆 | ✅ 跨轮累积 | ✅ | ❌ |
| `data_map` | 节点间结构化数据共享 | ✅ 跨轮保留 | ❌ | ❌ |
| `long_mem_data` | 长期记忆 | ✅ 写入即永久 | ❌ | ❌ |
| `nodes` | 当前轮 DAG 执行日志 | ❌ 每轮清除 | ❌ | ❌ |

### 4.3 多轮对话流程

每轮 `DAGEngine.run()` 执行完毕后：

```python
# dag.py — run() 末尾
session.add_turn(query_text, answer_text)   # → history 追加 TurnRecord，turn_id += 1
session.trim_or_compress(...)               # → 仅裁剪 history
session.nodes.clear()                       # → 清除本轮节点日志
```

LLM 工具构建 messages 时自动注入历史：

```python
# llm_tool.py
messages = [{"role": "system", "content": system_prompt}]
for t in session.history:
    messages.append({"role": "user", "content": t.input})
    messages.append({"role": "assistant", "content": t.output})
messages.append({"role": "user", "content": session.current_query})
```

支持模板占位符：
- `{{history}}` — 文本格式的历史对话
- `{{data_map}}` — JSON 格式的结构化数据
- `{{long_mem}}` — 长期记忆文本

### 4.4 Trim / Compress（只针对 history）

`session.trim_or_compress()` 仅操作 `history` 字段。`nodes` / `data_map` / `long_mem_data` 不参与。

触发条件（任一满足即触发）：
- `total_turns > max_turns`
- `total_chars > max_chars`

流程：
1. 计算超出量 `excess = total_turns - keep`
2. 摘出最旧 `excess` 轮 → 保留最近 `keep` 轮
3. 若配置了 summary LLM → 对旧轮生成摘要 → 摘要以 `TurnRecord("[前N轮摘要]", summary)` 插入 history 头部
4. LLM 调用失败 → 硬截断（不插入摘要）
5. 未配置 summary → 直接硬截断

### 4.5 存储后端

| 后端 | 实现 | 适用 |
|------|------|------|
| Memory | `MemorySessionStore` — 进程内 `dict` + TTL + LRU 驱逐 | 开发 / 单实例 |
| Redis | `RedisSessionStore` — `SETEX {prefix}{chat_id} json` + Redis TTL | 生产 / 多实例 |

配置见 `config/session.yaml`：

```yaml
store: memory              # memory | redis
max_age: 3600              # 会话过期时间（秒）
max_turns: 100             # 触发 trim 的历史最大轮数
max_chars: 100000          # 触发 trim 的历史最大字符数
keep: 20                   # trim 后至少保留的轮数
compress_max_words: 1000   # LLM 摘要最大字数

memory:
  max_sessions: 2000       # 内存最大会话数

redis:
  url: redis://localhost:6379/0
  prefix: "kf:sess:"

summary:                   # LLM 摘要配置（独立于 llm.yaml）
  base_url: "https://api.deepseek.com/v1"
  api_key: "${DEEPSEEK_KEY}"
  model: "deepseek-v4-flash"
  system_prompt: "请将以下对话压缩为{max_words}字以内的摘要..."
```

### 4.6 API 用法

**首轮**（无 chat_id，自动创建）：
```
POST /workflows/default/run  {"query": "什么是智能客服?"}
→ {"chat_id": "chat_xxx", "turn_id": 1, "reply": "您好..."}
```

**续接**（传入 chat_id）：
```
POST /workflows/default/run  {"query": "继续", "chat_id": "chat_xxx"}
→ {"chat_id": "chat_xxx", "turn_id": 2, "reply": "继续回答..."}
```

**删除会话**：
```
DELETE /sessions/chat_xxx → 204 No Content
```

**隔离**：跨 workflow 的 session 不可混用（API 校验 `_workflow` 匹配）。

## 5. input 和 output 隐式节点

引擎自动创建，无需定义：
- **input**：`data.text` = API 请求中的 `query`
- **output**：继承最后一个节点 `data.text`

## 6. next_type 路由类型

| 类型 | next 值 | 含义 |
|------|---------|------|
| `one` | 单个节点名 | 顺序执行 |
| `if-then` | 节点名列表 | 路由器选择分支 |
| `switch` | 节点名列表 | 执行所有分支 |

### router 规则

```yaml
router:
  match_field: text
  rules:
    - value: "faq"
      match: exact        # exact | contains | startswith
      branch: faq_node
  default: fallback
```

## 7. switch 并行

```yaml
- name: classify
  next_type: switch
  next: [faq, transfer]
  parallel: true
```

分支独立执行 → 按 timestamp 合并 → `branches` 回填索引。

## 8. 校验

```bash
# 校验产品目录
python -m src.cli.validate_workflow config/workflows/default/
# 或直接指定 workflow.yaml
python -m src.cli.validate_workflow config/workflows/default/workflow.yaml
# 详细输出
python -m src.cli.validate_workflow config/workflows/default/ --verbose
```

三步校验：存在性 → 连通性 → 收敛性。

## 9. 工具系统

| 工具 | 说明 |
|------|------|
| `llm` | LLM 聊天（OpenAI + Anthropic 格式），自动注入多轮历史 |
| `rag_search` | Qdrant 混合检索，支持单/多知识库 |
| `router` | 条件路由 |
| `db_query` | 数据库查询（MySQL / PostgreSQL），参数化查询 + 模板变量 |
| `merge` | switch 并行分支结果合并 |

### db_query 节点示例

```yaml
tool: db_query
db: mysql_main                    # config/db.yaml 中的连接池名称
query: "SELECT question, answer FROM faq WHERE question LIKE %s"
params:
  - "%{{query}}%"                # {{query}} 替换为当前用户输入
limit: 20
```

详见 `docs/db-config.md`。
