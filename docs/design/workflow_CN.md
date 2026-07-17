# Workflow 工作流完整指南

[English](workflow_EN.md)

## 1. 概述

KF 系统采用 **DAG（有向无环图）驱动的工作流引擎**。每个产品线拥有独立的工作流，包含自己的编排配置、知识库列表和节点定义。全局配置（`llm.yaml`、`embed.yaml`、`session.yaml`）跨产品线共享。

- 每产品线隔离：独立的 DAG 拓扑、路由规则、节点配置、知识库范围
- 全局共享：LLM 供应商、Embedding 供应商、会话存储配置
- 引擎自动创建 `input` / `output` 隐式节点，无需手动定义

---

## 2. 目录结构

```
config/
├── llm.yaml                    # 全局 LLM 供应商配置
├── embed.yaml                  # 全局 Embedding 供应商配置
├── session.yaml                # 全局会话存储配置
└── workflows/
    └── <product>/              # 产品线子目录
        ├── workflow.yaml       # DAG 拓扑 + 路由 + 知识库列表
        └── nodes/              # 节点实现
            ├── node_a.yaml
            └── node_b.yaml
```

---

## 3. workflow.yaml 格式

### 字段参考

| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | 是 | 工作流名称，全局唯一 |
| `enabled` | 否 | 是否启用，默认 `true` |
| `description` | 否 | 描述文本 |
| `collections` | 否 | 知识库列表，默认 `["default"]`。rag_search 节点默认查询这些集合 |
| `return_mode` | 是 | 固定 `"full"`，返回完整会话 |
| `conversation` | 否 | 多轮对话配置 |
| `conversation.max_turns` | 否 | 历史最大轮数，`null` 不限 |
| `nodes[].name` | 是 | 节点名称 |
| `nodes[].next_type` | 是 | 路由类型：`"one"` / `"if-then"` / `"switch"` |
| `nodes[].next` | 是 | `one` 填字符串，`if-then` / `switch` 填列表。空字符串 `""` 表示结束 |
| `nodes[].parallel` | 否 | `switch` 时是否并行执行，默认 `false` |
| `nodes[].metrics` | 是 | 是否采集性能指标 |

### 示例

```yaml
name: my_workflow
enabled: true
description: "产品支持工作流"
collections:
  - faq
  - product_manual
return_mode: full

conversation:
  max_turns: null

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

---

## 4. 节点配置（nodes/*.yaml）

每个节点 YAML 文件定义该节点的工具类型及相关参数。节点 key 格式为 `"{product}:{node_name}"`（全局唯一）。

### 通用字段

| 字段 | 说明 |
|------|------|
| `tool` | 工具类型：`llm`、`rag_search`、`router`、`db_query`、`api_call`、`web_search`、`code`、`merge` |

### 4.1 llm 节点

```yaml
# generate_answer.yaml
tool: llm
llm_provider: deepseek          # 可选，默认使用 llm.yaml 的 default
system_prompt: |
  你是一名客服助手。根据以下上下文回答用户问题。

  知识库内容：
  {{context}}

  用户问题：{{query}}

  历史对话：
  {{history}}
```

### 4.2 rag_search 节点

**单知识库：**

```yaml
# search_kb.yaml
tool: rag_search
collection: faq_v1              # 覆盖 workflow 级 collections
limit: 10
score_threshold: 0.5
prefetch_limit: 20
```

**多知识库（合并排序）：**

```yaml
# search_kb.yaml
tool: rag_search
collection:
  - faq_v1
  - faq_v2
limit: 10
score_threshold: 0.4
prefetch_limit: 10
```

**不指定 collection（继承 workflow 级）：**

```yaml
# search_kb.yaml
tool: rag_search
limit: 5
```

### 4.3 router 节点

```yaml
# intent_route.yaml
tool: router
router:
  match_field: text             # 匹配字段
  default: fallback_node        # 默认分支
  rules:
    - value: "product"
      match: exact              # exact / contains / startswith
      branch: product_node
    - value: "non_product"
      match: exact
      branch: other_node
```

### 4.4 db_query 节点

```yaml
# query_db.yaml
tool: db_query
db: mysql_main                  # config/db.yaml 中的连接池名称
query: "SELECT question, answer FROM faq WHERE question LIKE %s"
params:
  - "%{{query}}%"
limit: 20
```

---

## 5. 路由类型（next_type）

### 5.1 `one` — 顺序执行

单一路由，执行完后跳到指定的下一个节点。

```yaml
nodes:
  - name: retrieve
    next_type: one
    next: generate              # 单个节点名
```

`next: ""` 表示流程结束，到达 `output` 隐式节点。

### 5.2 `if-then` — 条件分支

使用 `router` 工具根据规则匹配选择分支。

- 匹配字段默认为 `text`（前序节点的输出文本）
- 匹配类型：`exact`（精确）、`contains`（包含）、`startswith`（前缀）
- 未命中任何规则时走 `default` 分支

**workflow.yaml：**

```yaml
nodes:
  - name: intent_route
    next_type: if-then
    next:
      - product_search
      - non_product_reply
```

**nodes/intent_route.yaml：**

```yaml
tool: router
router:
  match_field: text
  default: non_product_reply
  rules:
    - value: "太阳膜"
      match: contains
      branch: product_search
    - value: "车衣"
      match: contains
      branch: product_search
```

### 5.3 `switch` — 多路执行

所有分支全部执行：

- `parallel: true` → ThreadPoolExecutor 并发执行（默认 4 工作线程）
- `parallel: false` → 顺序执行
- 结果按时间戳合并

```yaml
nodes:
  - name: dispatcher
    next_type: switch
    next:
      - branch_a
      - branch_b
    parallel: true
```

---

## 6. 多知识库支持

### Workflow 级定义

```yaml
# workflow.yaml
collections:
  - faq
  - product_v2
  - internal_docs
```

### 节点级覆盖

单个集合：
```yaml
tool: rag_search
collection: faq
limit: 10
```

多个集合：
```yaml
tool: rag_search
collection:
  - faq
  - product_v2
limit: 10
```

### 合并逻辑

1. 节点未指定 `collection` → 继承 workflow 的 `collections` 列表
2. 节点 `collection` 为字符串 → 查单个集合
3. 节点 `collection` 为列表 → 查多个集合，结果按 score 降序合并，取前 `limit` 条

---

## 7. 隐式节点

引擎自动创建以下节点，**无需在 YAML 中定义**：

| 节点 | 说明 |
|------|------|
| `input` | DAG 入口。`data.text` = API 请求中的 `query` |
| `output` | DAG 出口。`data.text` = 最后一个节点的 `data.text` |

每个工作流的总节点数 = 隐式节点（2）+ 用户定义节点。

---

## 8. 并行分支执行

`switch` + `parallel: true` 的工作原理：

1. 每个分支独立构建节点列表
2. 通过 `ThreadPoolExecutor`（最多 4 工作线程）并发执行
3. `merge_branches()` 按时间戳排序合并所有分支结果
4. `branches` 字段回填各分支索引

并行适用于多角度检索、多渠道查询等无需相互等待的场景。

---

## 9. Session 集成

### 9.1 SessionData 数据结构

```python
class TurnRecord:
    input: str               # 用户输入
    output: str              # 系统回复
    input_timestamp: float
    output_timestamp: float

class SessionData:
    chat_id: str             # 唯一标识 "chat_<uuid>"
    turn_id: int             # 轮次计数，从 0 开始
    history: [TurnRecord]    # 跨轮次对话记忆 ← 参与 trim/compress
    data_map: {str:str}      # 节点间结构化数据共享，永不清除
    long_mem_data: str       # 长期记忆，永不清除
    nodes: [dict]            # 仅当前轮 DAG 执行日志，每轮结束自动清除
```

### 9.2 字段生命周期

| 字段 | 跨轮次 | 参与 trim | 返回 client |
|------|--------|-----------|-------------|
| `history` | ✅ 跨轮累积 | ✅ | ❌ |
| `data_map` | ✅ 跨轮保留 | ❌ | ❌ |
| `long_mem_data` | ✅ 永久保留 | ❌ | ❌ |
| `nodes` | ❌ 每轮清除 | ❌ | ❌ |

### 9.3 多轮对话流程

每轮 `DAGEngine.run()` 执行完毕后：

1. `add_turn(query, answer)` → history 追加 TurnRecord，turn_id += 1
2. `trim_or_compress()` → 仅裁剪 history（超过 max_turns 或 max_chars 时触发）
3. `nodes.clear()` → 清除本轮节点日志

LLM 工具自动将 history 注入 messages：
```
messages = [system_prompt, ...history_as_user_assistant_pairs, current_query]
```

### 9.4 会话存储

| 后端 | store 值 | 适用场景 |
|------|----------|---------|
| 内存 | `memory` | 开发环境、单实例，重启丢失 |
| Redis | `redis` | 生产环境、多实例 |

配置见 `config/session.yaml`：

```yaml
store: memory
max_age: 3600              # 过期时间（秒）
max_turns: 100             # 触发 trim 的最大轮数
max_chars: 100000          # 触发 trim 的最大字符数
keep: 20                   # trim 后保留的最小轮数
compress_max_words: 1000   # LLM 摘要最大字数

memory:
  max_sessions: 2000

redis:
  url: redis://localhost:6379/0
  prefix: "kf:sess:"

summary:                   # LLM 摘要（独立于 llm.yaml）
  base_url: "https://api.deepseek.com/v1"
  api_key: "${DEEPSEEK_KEY}"
  model: "deepseek-v4-flash"
  system_prompt: "请将以下对话压缩为{max_words}字以内的摘要..."
```

### 9.5 API 调用

```bash
# 首轮（无 chat_id，自动创建）
curl -X POST http://localhost:9000/api/v1/workflows/my_product/run \
  -H "Content-Type: application/json" \
  -d '{"query": "什么是智能客服?", "long_mem_data": "VIP 客户"}'
# → {"chat_id": "chat_xxx", "turn_id": 1, "reply": "您好..."}

# 续接（传入 chat_id）
curl -X POST http://localhost:9000/api/v1/workflows/my_product/run \
  -H "Content-Type: application/json" \
  -d '{"query": "继续", "chat_id": "chat_xxx"}'
# → {"chat_id": "chat_xxx", "turn_id": 2, "reply": "继续回答..."}

# 删除会话
curl -X DELETE http://localhost:9000/api/v1/sessions/chat_xxx
# → 204 No Content
```

跨 workflow 的 session 不可混用（API 校验 `_workflow` 匹配）。

---

## 10. 模板变量参考

工具配置（`system_prompt`、`query`、`url` 等）支持以下模板变量：

| 变量 | 来源 | 示例值 |
|------|------|--------|
| `{{query}}` | 当前用户输入 | `"隔热膜多少钱"` |
| `{{context}}` | 前序节点的 data.text | `"太阳膜价格范围 500-3000 元"` |
| `{{history}}` | 格式化历史对话 | `"用户: 有车膜吗\n客服: 有的..."` |
| `{{data_map}}` | data_map 的 JSON 字符串 | `{"order_id":"123"}` |
| `{{data_map:key}}` 或 `{{key}}` | data_map 中的特定字段 | `"123"` |
| `{{long_mem}}` | 长期记忆文本 | `"VIP 客户"` |
| `{{chat_id}}` | 会话 ID | `"chat_abc123"` |
| `{{_workflow}}` | 当前工作流名称 | `"auto_film"` |
| `{{return_mode}}` | 返回模式 | `"full"` |
| `{{<field>}}` | 任意节点输出的 data 字段 | 来自 `session.nodes[*].data` |

**替换优先级**（后者覆盖前者）：
1. `{{query}}` 直接替换
2. 节点输出字段（`session.nodes[*].data`）
3. data_map 字段
4. 会话元数据（`chat_id`、`_workflow`、`return_mode`、`long_mem_data`）

---

## 11. 工作流校验

```bash
# 校验产品目录
python -m src.cli.validate_workflow config/workflows/my_product/

# 校验指定 workflow.yaml
python -m src.cli.validate_workflow config/workflows/my_product/workflow.yaml

# 详细输出
python -m src.cli.validate_workflow config/workflows/my_product/ --verbose
```

**校验内容：**

1. **存在性**：workflow.yaml 及所有被引用的节点 YAML 文件是否存在
2. **连通性**：所有节点是否可达（无孤立节点）
3. **收敛性**：所有路径是否最终到达 output（无死循环/死路）

**通过输出示例：**
```
[OK] workflow "my_product" passed
     product dir: config\workflows\my_product
     nodes: 4 (input + 2 tool + output)
     collections: ['my_kb']
     connectivity: all nodes reachable
     convergence: all paths lead to output
```

---

## 12. 完整示例：auto_film 工作流

```
流程: intent_classify(LLM) → intent_route(router if-then) ─┬→ search_kb(RAG) → generate_answer(LLM)
                                                            └→ non_product_reply(LLM)
```

### 12.1 workflow.yaml

```yaml
name: auto_film
enabled: true
description: "汽车衣膜智能问答 — 太阳膜/隐形车衣/车窗膜/车衣膜产品咨询"
collections:
  - car_films
return_mode: full

conversation:
  max_turns: null

nodes:
  - name: intent_classify
    next_type: one
    next: intent_route
    metrics: true

  - name: intent_route
    next_type: if-then
    next:
      - search_kb
      - non_product_reply
    metrics: true

  - name: search_kb
    next_type: one
    next: generate_answer
    metrics: true

  - name: generate_answer
    next_type: one
    next: ""
    metrics: true

  - name: non_product_reply
    next_type: one
    next: ""
    metrics: true
```

### 12.2 nodes/intent_classify.yaml

```yaml
tool: llm
system_prompt: >
  判断用户输入是否与汽车膜产品相关。
  产品包括：太阳膜、隔热膜、防晒膜、隐形车衣、漆面保护膜、车窗膜、车衣膜。
  打招呼、问候也算产品相关（用户准备咨询）。

  只回复一个单词：product 或 non_product。
  不要回复任何其他内容。
```

### 12.3 nodes/intent_route.yaml

```yaml
tool: router
router:
  match_field: text
  default: search_kb
  rules:
    - match: exact
      value: "product"
      branch: search_kb
    - match: exact
      value: "non_product"
      branch: non_product_reply
```

### 12.4 nodes/search_kb.yaml

```yaml
tool: rag_search
limit: 5
score_threshold: 0.4
prefetch_limit: 10
```

### 12.5 nodes/generate_answer.yaml

```yaml
tool: llm
system_prompt: >
  你是一名汽车膜产品的客服助手，负责回答用户关于以下产品的问题：
  - 太阳膜（隔热膜、防晒膜）
  - 隐形车衣（漆面保护膜）
  - 车窗膜
  - 车衣膜

  回答规则：
  1. 根据以下知识库内容回答用户的问题，不要编造知识库没有的信息
  2. 用亲切、通俗易懂的语气回答，就像在跟朋友聊天一样
  3. 回答要简短，控制在2-3句话以内，如果涉及多个要点最多5句话
  4. 适当使用口语化表达，比如"咱们的""这个膜""贴上去之后"等
  5. 如果知识库中有相关信息但不够完整，如实告诉用户并给出已有信息
  6. 如果知识库中没有相关信息，告诉用户"这个问题我暂时不太清楚，建议你咨询我们的专业客服哦~"

  知识库内容：
  {{context}}

  用户问题：{{query}}

  {{long_mem}}

  历史对话：
  {{history}}
```

### 12.6 nodes/non_product_reply.yaml

```yaml
tool: llm
system_prompt: >
  你是汽车膜产品的客服助手，只回答产品相关问题。
  如果用户问的不是产品相关问题，请友善地提醒：

  "不好意思呀~ 我只能回答咱们汽车膜产品相关的问题哦！比如太阳膜、隐形车衣、车窗膜、车衣膜这些，你有想了解的吗？😊"

  注意：
  1. 语气要亲切友善，不要生硬
  2. 可以适当引导用户回到产品话题
  3. 控制在1-2句话

  用户问题：{{query}}
```

---

## 工具系统速查

| 工具 | 说明 |
|------|------|
| `llm` | LLM 对话，自动注入多轮历史，支持模板变量 |
| `rag_search` | Qdrant 混合检索（Dense + Sparse BM25），RRF 融合，支持单/多知识库 |
| `router` | 条件路由，支持 exact / contains / startswith 匹配 |
| `db_query` | 数据库查询（MySQL / PostgreSQL），参数化查询 + 模板变量 |
| `api_call` | 外部 HTTP API 调用，URL 和 headers 支持模板变量 |
| `web_search` | 网络搜索 |
| `code` | Python 代码执行（沙箱），可访问 session 数据 |
| `merge` | switch 并行分支结果合并 |
