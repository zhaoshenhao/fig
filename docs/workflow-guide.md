# Workflow 编写指南

## 五步法创建新工作流

```
步骤 A: 创建产品子目录 + workflow.yaml
步骤 B: 创建 nodes/ 目录下的节点配置
步骤 C: 配置 llm.yaml + embed.yaml（全局）
步骤 D: 配置 session.yaml（全局会话）
步骤 E: 校验
```

---

## 步骤 A：创建产品子目录

```bash
mkdir -p config/workflows/my_product/nodes
touch config/workflows/my_product/workflow.yaml
```

### config/workflows/my_product/workflow.yaml

```yaml
name: my_product
description: "我的产品线客服"
collections:
  - my_kb
return_mode: full

conversation:           # 可选，多轮对话
  max_turns: null       # 历史最大轮数，null 不限（也可在 session.yaml 全局设）

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

### 知识库配置

`collections` 字段控制 rag_search 节点默认查询哪些 Qdrant 集合：

```yaml
# 不写表示默认 ["default"]
collections:
  - faq_v1
  - faq_v2
```

---

## 步骤 B：节点配置

### config/workflows/my_product/nodes/retrieve.yaml

单知识库：

```yaml
tool: rag_search
collection: faq_v1         # 覆盖 workflow 级 collections
limit: 10
score_threshold: 0.5
prefetch_limit: 20
```

多知识库（合并排序）：

```yaml
tool: rag_search
collection:
  - faq_v1
  - faq_v2
limit: 10
```

不指定 collection（继承 workflow 级）：

```yaml
tool: rag_search
limit: 10
```

### config/workflows/my_product/nodes/generate.yaml

```yaml
tool: llm
llm_provider: deepseek      # 可选，默认用 llm.yaml 的 default
system_prompt: "你是一个客服助手。根据上下文回答：\n\n{{context}}\n\n问题：{{query}}"
```

### 模板变量

| 变量 | 来源 |
|------|------|
| `{{query}}` | input 节点的用户问题 |
| `{{context}}` | 前一个节点的 data.text |

---

## 步骤 C：供应商配置（全局）

### config/llm.yaml

```yaml
default: deepseek

providers:
  deepseek:
    type: openai
    base_url: https://api.deepseek.com/v1
    api_key: ${DEEPSEEK_API_KEY}
    model: deepseek-v4-flash
```

### config/embed.yaml

```yaml
default: ollama

providers:
  ollama:
    type: openai
    base_url: http://localhost:11434/v1
    api_key: ""
    model: nomic-embed-text
    dims: 768
```

---

## 步骤 D：会话配置（全局，config/session.yaml）

```yaml
store: memory              # memory（开发） | redis（生产）

max_age: 3600              # 会话过期时间（秒），1h

max_turns: 100             # 触发 trim 的历史最大轮数
max_chars: 100000          # 触发 trim 的历史最大字符数
keep: 20                   # trim 后至少保留的轮数
compress_max_words: 1000   # LLM 摘要最大字数

memory:                    # memory store 参数
  max_sessions: 2000       # 最大会话数，超过驱逐最旧的

redis:                     # redis store 参数
  url: redis://localhost:6379/0
  prefix: "kf:sess:"

summary:                   # LLM 摘要配置（独立于 llm.yaml，用于压缩历史）
  base_url: "https://api.deepseek.com/v1"
  api_key: "${DEEPSEEK_KEY}"
  model: "deepseek-v4-flash"
  system_prompt: "请将以下对话压缩为{max_words}字以内的摘要..."
```

### 会话存储选择

| 后端 | store 值 | 适用场景 |
|------|----------|---------|
| 内存 | `memory` | 开发环境、单实例，重启丢失 |
| Redis | `redis` | 生产环境、多实例，支持持久化 |

### Session 数据结构

```python
class TurnRecord:
    input: str              # 用户输入
    output: str             # 系统回复
    input_timestamp: float
    output_timestamp: float

class SessionData:
    chat_id: str            # 唯一标识，自动生成
    turn_id: int            # 轮次计数，每轮 +1
    history: [TurnRecord]   # ← 跨轮次记忆，参与 trim/compress
    data_map: {str:str}     # 结构化数据，永不清除
    long_mem_data: str      # 长期记忆，永不清除
    nodes: [dict]           # 仅当前轮 DAG 日志，每轮结束后自动清除
```

### 多轮对话

LLM 工具自动将 `session.history`（TurnRecord 列表）转为 messages：

```
messages = [system_prompt, ...history_as_user_assistant_pairs, current_query]
```

每轮执行完毕后引擎自动：
1. `add_turn(query, answer)` → history 追加 TurnRecord
2. `trim_or_compress()` → 仅裁剪 history（超过 max_turns 或 max_chars 时触发）
3. `nodes.clear()` → 清除本轮节点日志

支持模板占位符（在 system_prompt 中使用）：
- `{{history}}` — 文本格式的历史对话
- `{{data_map}}` — JSON 格式的结构化数据
- `{{long_mem}}` — 长期记忆文本

### API 调用

```bash
# 首轮（无 chat_id，自动创建）
curl -X POST http://localhost:8000/workflows/my_product/run \
  -H "Content-Type: application/json" \
  -d '{"query": "什么是智能客服?"}'
# → {"chat_id": "chat_xxx", "turn_id": 1, "reply": "您好..."}

# 续接（传入 chat_id）
curl -X POST http://localhost:8000/workflows/my_product/run \
  -H "Content-Type: application/json" \
  -d '{"query": "继续", "chat_id": "chat_xxx"}'
# → {"chat_id": "chat_xxx", "turn_id": 2, "reply": "继续回答..."}

# 删除会话
curl -X DELETE http://localhost:8000/sessions/chat_xxx
# → 204 No Content
```

---

## 步骤 E：校验

```bash
# 校验产品目录
python -m src.cli.validate_workflow config/workflows/my_product/

# 校验通过输出：
#   [OK] workflow "my_product" passed
#        product dir: config\workflows\my_product
#        nodes: 4 (input + 2 tool + output)
#        collections: ['my_kb']
#        connectivity: all nodes reachable
#        convergence: all paths lead to output
```

---

## 高级路由

### if-then 条件路由

```yaml
nodes:
  - name: classify
    next_type: if-then
    next: [faq_handler, transfer_handler]

  - name: faq_handler
    next_type: one
    next: ""

  - name: transfer_handler
    next_type: one
    next: ""
```

节点配置 `classify.yaml`：

```yaml
tool: router
router:
  match_field: text
  rules:
    - value: "转人工"
      match: contains
      branch: transfer_handler
  default: faq_handler
```

### switch 多路执行

```yaml
nodes:
  - name: dispatcher
    next_type: switch
    next: [branch_a, branch_b]

  - name: branch_a
    next_type: one
    next: ""

  - name: branch_b
    next_type: one
    next: ""
```

---

## 多产品线示例

```
config/workflows/
├── customer_service/
│   ├── workflow.yaml      ← collections: [cs_faq, cs_v2]
│   └── nodes/
│       ├── retrieve.yaml
│       └── generate.yaml
├── tech_support/
│   ├── workflow.yaml      ← collections: [tech_docs, bug_db]
│   └── nodes/
│       ├── classify.yaml   ← router: if-then
│       ├── kb_search.yaml
│       ├── ticket.yaml
│       └── generate.yaml
└── internal_hr/
    ├── workflow.yaml      ← collections: [hr_policy]
    └── nodes/
        ├── retrieve.yaml
        └── generate.yaml
```

三个产品线完全隔离：各自独立的 DAG、知识库、node 配置。共享全局 llm.yaml / embed.yaml / session.yaml。
