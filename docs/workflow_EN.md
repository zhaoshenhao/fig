# Workflow Guide

[中文](workflow_CN.md)

## 1. Overview

The KF system uses a **DAG (Directed Acyclic Graph) workflow engine**. Each product line has its own independent workflow with its own orchestration config, knowledge base list, and node definitions. Global configs (`llm.yaml`, `embed.yaml`, `session.yaml`) are shared across product lines.

- Per-product isolation: independent DAG topology, routing rules, node configs, and knowledge base scope
- Globally shared: LLM providers, Embedding providers, session storage config
- The engine auto-creates `input` / `output` implicit nodes — no manual definition needed

---

## 2. Directory Structure

```
config/
├── llm.yaml                    # Global LLM provider config
├── embed.yaml                  # Global Embedding provider config
├── session.yaml                # Global session storage config
└── workflows/
    └── <product>/              # Product-line subdirectory
        ├── workflow.yaml       # DAG topology + routing + knowledge base list
        └── nodes/              # Node implementations
            ├── node_a.yaml
            └── node_b.yaml
```

---

## 3. workflow.yaml Format

### Field Reference

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Unique workflow name |
| `enabled` | No | Enable/disable, default `true` |
| `description` | No | Description text |
| `collections` | No | Knowledge base list, default `["default"]`. rag_search nodes query these collections by default |
| `return_mode` | Yes | Must be `"full"` |
| `conversation` | No | Multi-turn conversation config |
| `conversation.max_turns` | No | Max history turns, `null` = unlimited |
| `nodes[].name` | Yes | Node name |
| `nodes[].next_type` | Yes | Routing type: `"one"` / `"if-then"` / `"switch"` |
| `nodes[].next` | Yes | String for `one`, list for `if-then` / `switch`. Empty `""` = terminal |
| `nodes[].parallel` | No | For `switch`: execute branches in parallel (default `false`) |
| `nodes[].metrics` | Yes | Collect performance metrics |

### Example

```yaml
name: my_workflow
enabled: true
description: "Product support workflow"
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

## 4. Node Configuration (nodes/*.yaml)

Each node YAML file defines the tool type and parameters. Node key format: `"{product}:{node_name}"` (globally unique).

### Common Fields

| Field | Description |
|-------|-------------|
| `tool` | Tool type: `llm`, `rag_search`, `router`, `db_query`, `api_call`, `web_search`, `code`, `merge` |

### 4.1 llm Node

```yaml
# generate_answer.yaml
tool: llm
llm_provider: deepseek          # Optional, defaults to llm.yaml default
system_prompt: |
  You are a customer service assistant. Answer based on the context below.

  Knowledge base:
  {{context}}

  User question: {{query}}

  Conversation history:
  {{history}}
```

### 4.2 rag_search Node

**Single collection:**

```yaml
# search_kb.yaml
tool: rag_search
collection: faq_v1              # Overrides workflow-level collections
limit: 10
score_threshold: 0.5
prefetch_limit: 20
```

**Multiple collections (merged & sorted):**

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

**No collection specified (inherits workflow-level):**

```yaml
# search_kb.yaml
tool: rag_search
limit: 5
```

### 4.3 router Node

```yaml
# intent_route.yaml
tool: router
router:
  match_field: text             # Field to match against
  default: fallback_node        # Default branch
  rules:
    - value: "product"
      match: exact              # exact / contains / startswith
      branch: product_node
    - value: "non_product"
      match: exact
      branch: other_node
```

### 4.4 db_query Node

```yaml
# query_db.yaml
tool: db_query
db: mysql_main                  # Connection pool name in config/db.yaml
query: "SELECT question, answer FROM faq WHERE question LIKE %s"
params:
  - "%{{query}}%"
limit: 20
```

---

## 5. Routing Types (next_type)

### 5.1 `one` — Sequential Execution

Single next node. After execution, jumps to the specified node.

```yaml
nodes:
  - name: retrieve
    next_type: one
    next: generate              # Single node name
```

`next: ""` means the workflow ends, reaching the `output` implicit node.

### 5.2 `if-then` — Conditional Branching

Uses a `router` tool to select a branch based on rules.

- Match field defaults to `text` (output text of the preceding node)
- Match types: `exact`, `contains`, `startswith`
- Falls back to the `default` branch when no rule matches

**workflow.yaml:**

```yaml
nodes:
  - name: intent_route
    next_type: if-then
    next:
      - product_search
      - non_product_reply
```

**nodes/intent_route.yaml:**

```yaml
tool: router
router:
  match_field: text
  default: non_product_reply
  rules:
    - value: "pricing"
      match: contains
      branch: product_search
    - value: "warranty"
      match: contains
      branch: product_search
```

### 5.3 `switch` — Multi-Branch Execution

All branches execute:

- `parallel: true` → concurrent via ThreadPoolExecutor (default 4 workers)
- `parallel: false` → sequential execution
- Results merged by timestamp

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

## 6. Multi-Knowledge-Base Support

### Workflow-Level Definition

```yaml
# workflow.yaml
collections:
  - faq
  - product_v2
  - internal_docs
```

### Node-Level Override

Single collection:
```yaml
tool: rag_search
collection: faq
limit: 10
```

Multiple collections:
```yaml
tool: rag_search
collection:
  - faq
  - product_v2
limit: 10
```

### Merge Logic

1. Node `collection` not specified → inherits workflow's `collections` list
2. Node `collection` is a string → query single collection
3. Node `collection` is a list → query multiple collections, merge results by score descending, take top `limit`

---

## 7. Implicit Nodes

The engine auto-creates these nodes — **no YAML definition needed**:

| Node | Description |
|------|-------------|
| `input` | DAG entry point. `data.text` = API request `query` |
| `output` | DAG exit point. `data.text` = last node's `data.text` |

Total nodes per workflow = implicit (2) + user-defined nodes.

---

## 8. Parallel Branch Execution

How `switch` + `parallel: true` works:

1. Each branch builds an independent node list
2. Branches execute concurrently via `ThreadPoolExecutor` (max 4 workers)
3. `merge_branches()` sorts all results by timestamp and merges
4. `branches` field backfills each branch index

Ideal for multi-angle retrieval, multi-channel queries, and other scenarios where branches don't depend on each other.

---

## 9. Session Integration

### 9.1 SessionData Structure

```python
class TurnRecord:
    input: str               # User input
    output: str              # System reply
    input_timestamp: float
    output_timestamp: float

class SessionData:
    chat_id: str             # Unique ID "chat_<uuid>"
    turn_id: int             # Turn counter, starts at 0
    history: [TurnRecord]    # Cross-turn conversation memory ← participates in trim/compress
    data_map: {str:str}      # Cross-node structured data sharing, never cleared
    long_mem_data: str       # Long-term memory, never cleared
    nodes: [dict]            # Current-turn DAG execution log, cleared each turn
```

### 9.2 Field Lifecycle

| Field | Cross-turn | Trimmed | Returned to client |
|-------|------------|---------|-------------------|
| `history` | ✅ Accumulated | ✅ | ❌ |
| `data_map` | ✅ Preserved | ❌ | ❌ |
| `long_mem_data` | ✅ Permanent | ❌ | ❌ |
| `nodes` | ❌ Cleared each turn | ❌ | ❌ |

### 9.3 Multi-Turn Flow

After each `DAGEngine.run()` call:

1. `add_turn(query, answer)` → appends TurnRecord to history, turn_id += 1
2. `trim_or_compress()` → trims history only (triggered when exceeding max_turns or max_chars)
3. `nodes.clear()` → clears current-turn node logs

LLM tool auto-injects history into messages:
```
messages = [system_prompt, ...history_as_user_assistant_pairs, current_query]
```

### 9.4 Session Storage

| Backend | store value | Use case |
|---------|------------|----------|
| Memory | `memory` | Development, single-instance, lost on restart |
| Redis | `redis` | Production, multi-instance, persistent |

Configuration in `config/session.yaml`:

```yaml
store: memory
max_age: 3600              # Session TTL (seconds)
max_turns: 100             # Max turns before trim
max_chars: 100000          # Max chars before trim
keep: 20                   # Min turns to retain after trim
compress_max_words: 1000   # Max words for LLM summary

memory:
  max_sessions: 2000

redis:
  url: redis://localhost:6379/0
  prefix: "kf:sess:"

summary:                   # LLM summary (independent of llm.yaml)
  base_url: "https://api.deepseek.com/v1"
  api_key: "${DEEPSEEK_KEY}"
  model: "deepseek-v4-flash"
  system_prompt: "Summarize the following conversation in under {max_words} words..."
```

### 9.5 API Usage

```bash
# First turn (no chat_id, auto-created)
curl -X POST http://localhost:9000/api/v1/workflows/my_product/run \
  -H "Content-Type: application/json" \
  -d '{"query": "What is a smart customer service?", "long_mem_data": "VIP customer"}'
# → {"chat_id": "chat_xxx", "turn_id": 1, "reply": "Hello..."}

# Continuation (with chat_id)
curl -X POST http://localhost:9000/api/v1/workflows/my_product/run \
  -H "Content-Type: application/json" \
  -d '{"query": "Tell me more", "chat_id": "chat_xxx"}'
# → {"chat_id": "chat_xxx", "turn_id": 2, "reply": "Continuing..."}

# Delete session
curl -X DELETE http://localhost:9000/api/v1/sessions/chat_xxx
# → 204 No Content
```

Cross-workflow sessions cannot be mixed (API validates `_workflow` match).

---

## 10. Template Variable Reference

Tool configs (`system_prompt`, `query`, `url`, etc.) support these template variables:

| Variable | Source | Example |
|----------|--------|---------|
| `{{query}}` | Current user input | `"How much is window film?"` |
| `{{context}}` | Preceding node's data.text | `"Window film price: $50-300"` |
| `{{history}}` | Formatted chat history | `"User: Hello\nAssistant: Hi..."` |
| `{{data_map}}` | JSON string of data_map | `{"order_id":"123"}` |
| `{{data_map:key}}` or `{{key}}` | Specific data_map field | `"123"` |
| `{{long_mem}}` | Long-term memory text | `"VIP customer"` |
| `{{chat_id}}` | Session ID | `"chat_abc123"` |
| `{{_workflow}}` | Current workflow name | `"auto_film"` |
| `{{return_mode}}` | Return mode | `"full"` |
| `{{<field>}}` | Any node output data field | From `session.nodes[*].data` |

**Replacement priority** (later overrides earlier):
1. `{{query}}` — direct substitution
2. Node output fields (`session.nodes[*].data`)
3. data_map fields
4. Session metadata (`chat_id`, `_workflow`, `return_mode`, `long_mem_data`)

---

## 11. Workflow Validation

```bash
# Validate a product directory
python -m src.cli.validate_workflow config/workflows/my_product/

# Validate a specific workflow.yaml
python -m src.cli.validate_workflow config/workflows/my_product/workflow.yaml

# Verbose output
python -m src.cli.validate_workflow config/workflows/my_product/ --verbose
```

**Validation checks:**

1. **Existence**: workflow.yaml and all referenced node YAML files exist
2. **Connectivity**: all nodes are reachable (no orphans)
3. **Convergence**: all paths eventually reach output (no dead ends)

**Pass output example:**
```
[OK] workflow "my_product" passed
     product dir: config\workflows\my_product
     nodes: 4 (input + 2 tool + output)
     collections: ['my_kb']
     connectivity: all nodes reachable
     convergence: all paths lead to output
```

---

## 12. Complete Example: auto_film Workflow

```
Flow: intent_classify(LLM) → intent_route(router if-then) ─┬→ search_kb(RAG) → generate_answer(LLM)
                                                            └→ non_product_reply(LLM)
```

### 12.1 workflow.yaml

```yaml
name: auto_film
enabled: true
description: "Auto film Q&A — sun film / PPF / window film / car wrap consultation"
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
  Determine if the user input is related to auto film products.
  Products include: sun film, heat insulation film, solar control film,
  PPF (paint protection film), window film, car wrap film.
  Greetings also count as product-related (user is about to inquire).

  Reply with a single word: product or non_product.
  Do not reply with anything else.
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
  You are a customer service assistant for auto film products, responsible
  for answering questions about:
  - Sun film (heat insulation film, solar control film)
  - PPF (paint protection film)
  - Window film
  - Car wrap film

  Rules:
  1. Answer based on the knowledge base content below; do not fabricate information
  2. Use a friendly, conversational tone, like chatting with a friend
  3. Keep answers short — 2-3 sentences, at most 5 for multiple points
  4. Use casual, natural expressions
  5. If the knowledge base has partial info, honestly share what's available
  6. If no relevant information exists, say: "I'm not sure about that — I recommend consulting our specialist!"

  Knowledge base content:
  {{context}}

  User question: {{query}}

  {{long_mem}}

  Conversation history:
  {{history}}
```

### 12.6 nodes/non_product_reply.yaml

```yaml
tool: llm
system_prompt: >
  You are a customer service assistant for auto film products.
  Politely remind users to stay on topic if they ask non-product questions.

  Say something like:
  "Sorry, I can only answer questions about our auto film products — like sun film, PPF, window film, car wrap film. Is there anything you'd like to know about these?"

  Notes:
  1. Keep the tone friendly, not blunt
  2. Gently guide the user back to product topics
  3. Keep it to 1-2 sentences

  User question: {{query}}
```

---

## Tool System Quick Reference

| Tool | Description |
|------|-------------|
| `llm` | LLM chat, auto-injects multi-turn history, supports template variables |
| `rag_search` | Qdrant hybrid search (Dense + Sparse BM25), RRF fusion, single/multi-collection |
| `router` | Conditional routing with exact / contains / startswith matching |
| `db_query` | Database query (MySQL / PostgreSQL), parameterized + template variables |
| `api_call` | External HTTP API call, URL and headers support template variables |
| `web_search` | Web search |
| `code` | Python code execution (sandboxed), can access session data |
| `merge` | Merge results from parallel switch branches |
