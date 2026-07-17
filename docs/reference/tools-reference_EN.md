# KF Tools Reference & Development Guide

[中文](tools-reference_CN.md)

---

## Table of Contents

- [Part 1: Built-in Tools (10)](#part-1-built-in-tools-10)
  - [1. llm — LLM Call](#1-llm--llm-call)
  - [2. rag_search — Vector Search](#2-rag_search--vector-search)
  - [3. router — Conditional Routing](#3-router--conditional-routing)
  - [4. merge — Parallel Branch Merge](#4-merge--parallel-branch-merge)
  - [5. db_query — Database Query](#5-db_query--database-query)
  - [6. extract_llm — LLM Information Extraction](#6-extract_llm--llm-information-extraction)
  - [7. extract_regex — Regex Extraction](#7-extract_regex--regex-extraction)
  - [8. api_call — External API Call](#8-api_call--external-api-call)
  - [9. web_search — Web Search](#9-web_search--web-search)
  - [10. code — Safe Code Execution](#10-code--safe-code-execution)
- [Part 2: Common Tool Protocol](#part-2-common-tool-protocol)
- [Part 3: Tool Registration](#part-3-tool-registration)
- [Part 4: CLI Tools](#part-4-cli-tools)
  - [Document Ingestion — `python -m src.cli.build`](#document-ingestion--python--m-srcclibuild)
  - [KB Management — `python -m src.cli.manage`](#kb-management--python--m-srcclimanage)
  - [Workflow Validator — `python -m src.cli.validate_workflow`](#workflow-validator--python--m-srcclivalidate_workflow)
- [Part 5: Tool Development Guide](#part-5-tool-development-guide)
  - [Tool Signature](#tool-signature)
  - [Creating a New Tool](#creating-a-new-tool)
  - [Session Object Usage](#session-object-usage)
  - [Template Variable Resolution](#template-variable-resolution)
  - [Logging & Metrics](#logging--metrics)
  - [Writing Tests](#writing-tests)
  - [Development Checklist](#development-checklist)
  - [Forbidden Practices](#forbidden-practices)

---

## Part 1: Built-in Tools (10)

The system provides 10 built-in tools, specified in workflow node YAML via the `tool` field.

### 1. llm — LLM Call

**Function**: Call an LLM to generate replies, injecting dialog history, context, and session variables. Supports streaming output (SSE).

**Usage**: `tool: llm`

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `llm_provider` | str | No | LLM provider name (key in config/auth.yaml), defaults to the default provider |
| `system_prompt` | str | Yes | System prompt supporting `{{query}}`, `{{context}}`, `{{data_map}}`, `{{long_mem}}`, `{{history}}` placeholders |

**Template Placeholders**:

| Placeholder | Description |
|-------------|-------------|
| `{{query}}` | Current user input text |
| `{{context}}` | Upstream node output text (data.text from predecessor with next_type=one) |
| `{{data_map}}` | session.data_map (serialized as JSON) |
| `{{long_mem}}` | Long-term memory text passed by the client |
| `{{history}}` | Formatted dialog history (User: ...\nAgent: ...) |

**Return Value**:

| Field | Type | Description |
|-------|------|-------------|
| `text` | str | LLM-generated reply text |
| `model` | str | Model name used |
| `usage` | dict | Token usage (non-streaming mode), with `prompt_tokens`, `completion_tokens` |

**Streaming**: When the session object has a `stream_callback` attribute, llm_tool calls `LLMClient.stream_chat()` to push tokens one at a time. Callback signature: `fn(token: str) -> None`. Non-streaming mode uses `LLMClient.chat()` as a blocking call.

**Node Config Example**:

```yaml
# generate_answer.yaml
tool: llm
llm_provider: deepseek
system_prompt: |
  You are an expert in {{query}} customer service.
  Answer the user's question based on the context below.

  Context: {{context}}
  History: {{history}}
```

---

### 2. rag_search — Vector Search

**Function**: Embed the user input, search Qdrant, and return relevant documents. Uses hybrid search (Dense Cosine + Sparse BM25 + RRF fusion).

**Usage**: `tool: rag_search`

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `embed_provider` | str | No | Embedding provider name |
| `collection` | str\|list | No | Target collection; if omitted, inherits from workflow.yaml configuration |
| `limit` | int | No | Number of results to return, default 10 |
| `score_threshold` | float | No | Minimum score threshold for filtering |
| `prefetch_limit` | int | No | Prefetch count for hybrid search (candidate set size before RRF fusion), default 20 |

**Multi-Collection Merge**: When `collection` is a list or multiple collections, results from all collections are merged, sorted by score descending, and truncated to top-N.

**Collection Inheritance**: When `collection` is not specified, the workflow's associated collections are resolved from global config via `session._workflow`. Falls back to `default` if not configured.

**Return Value**:

| Field | Type | Description |
|-------|------|-------------|
| `text` | str | Concatenated document chunk text (double-newline separated) |
| `chunks` | list[str] | List of document chunks |
| `results` | list[dict] | Raw results (with id/score/payload) |

**Node Config Example**:

```yaml
# search_kb.yaml
tool: rag_search
collection: faq_kb
limit: 5
score_threshold: 0.5
```

---

### 3. router — Conditional Routing

**Function**: Match rules against upstream node output, returning a branch name. Used with `next_type: if-then` for conditional branching.

**Usage**: `tool: router`

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `router.rules` | list | Yes | List of routing rules |
| `router.match_field` | str | No | Field to match against, default "text" (upstream node output) |
| `router.default` | str | No | Default branch name when no rule matches |

**Rule Structure** (`router.rules[]`):

| Field | Type | Description |
|-------|------|-------------|
| `branch` | str | Target branch node name when matched |
| `value` | str | Value to match against |
| `match` | str | Match mode: `exact` (case/whitespace-insensitive) \| `contains` \| `startswith` |

**Return Value**: `str` — matched branch name (or default)

**Node Config Example**:

```yaml
# intent_classify.yaml
tool: router
router:
  match_field: text
  default: inquiry
  rules:
    - value: "complaint"
      match: contains
      branch: complaint
    - value: "order"
      match: contains
      branch: order
    - value: "hello"
      match: startswith
      branch: greeting
```

**Integration with workflow.yaml**:

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

### 4. merge — Parallel Branch Merge

**Function**: Merge results from multiple parallel branches (triggered by `switch` + `parallel: true`). This tool is called internally by the DAG engine and is **not configured in node YAML**.

**Trigger**: `next_type: switch` with `parallel: true` in workflow.yaml

**How it works**:
1. Tags each branch node with its source branch (`_branch` field) and parent node (`pre` field)
2. Sorts all branch nodes by `timestamp` ascending
3. Appends all branch nodes to session.nodes
4. Records start/end index ranges for each branch on the switch node (`branches` field)

```yaml
# switch node with parallel branches in workflow.yaml
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

### 5. db_query — Database Query

**Function**: Execute SQL queries with template variable substitution.

**Prerequisite**: Connection pools configured in `config/db.yaml`.

**Usage**: `tool: db_query`

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `db` | str | Yes | Database pool name (key in config/db.yaml) |
| `query` | str | Yes | SQL template supporting `{{query}}`, `{{data_map:key}}` placeholders |
| `params` | list | No | Parameterized query parameter list |
| `limit` | int | No | Max rows to return, default 50 |

**Return Value**:

| Field | Type | Description |
|-------|------|-------------|
| `text` | str | Formatted table text |
| `rows` | list[dict] | Query result rows |
| `db` | str | Database pool name |

**Node Config Example**:

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

### 6. extract_llm — LLM Information Extraction

**Function**: Use LLM to extract structured fields from user input, storing results in `session.data_map`.

**Usage**: `tool: extract_llm`

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `extract` | list | Yes | Field extraction definitions |
| `llm_provider` | str | No | LLM provider name |

**Field Definition** (`extract[]`):

| Field | Type | Description |
|-------|------|-------------|
| `key` | str | Field name (key used in data_map) |
| `description` | str | Field description (used to construct the prompt) |

**Return Value**:

| Field | Type | Description |
|-------|------|-------------|
| `text` | str | "extracted N fields" message |
| `extracted` | list[str] | List of extracted field keys |

**Node Config Example**:

```yaml
# extract_info.yaml
tool: extract_llm
llm_provider: deepseek
extract:
  - key: customer_name
    description: Customer name
  - key: order_number
    description: Order number
  - key: issue_type
    description: Issue type (return/exchange/refund/inquiry)
```

**Downstream Usage**: Extracted fields can be referenced in downstream prompts or SQL via `{{data_map:customer_name}}`.

---

### 7. extract_regex — Regex Extraction

**Function**: Extract fields from user input using regular expressions, storing results in `session.data_map`.

**Usage**: `tool: extract_regex`

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `extract` | list | Yes | Extraction rule list |

**Field Definition** (`extract[]`):

| Field | Type | Description |
|-------|------|-------------|
| `key` | str | Field name (key used in data_map) |
| `pattern` | str | Regular expression pattern |

**Return Value**:

| Field | Type | Description |
|-------|------|-------------|
| `text` | str | "matched N fields" message |
| `extracted` | list[str] | List of matched field keys |

**Node Config Example**:

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

### 8. api_call — External API Call

**Function**: Send HTTP requests to external APIs with template variable substitution.

**Usage**: `tool: api_call`

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `url` | str | Yes | Request URL, supports `{{query}}`, `{{chat_id}}`, `{{data_map:key}}` placeholders |
| `method` | str | No | HTTP method, default GET |
| `headers` | dict | No | Request headers (values support template substitution) |
| `body` | dict | No | JSON request body |
| `timeout` | int | No | Timeout in seconds, default 30 |

**Return Value**:

| Field | Type | Description |
|-------|------|-------------|
| `text` | str | Response body (truncated to 5000 chars) |
| `status_code` | int | HTTP status code |
| `url` | str | Actual request URL |

**Node Config Example**:

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

### 9. web_search — Web Search

**Function**: Perform online search and return page summaries.

**Usage**: `tool: web_search`

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `engine` | str | No | Search engine, default duckduckgo |
| `query_template` | str | No | Search query template, default `{{query}}` |
| `limit` | int | No | Max number of results, default 5 |

**Return Value**:

| Field | Type | Description |
|-------|------|-------------|
| `text` | str | Formatted summary text |
| `results` | list[dict] | Raw results (title/url/snippet) |

**Node Config Example**:

```yaml
# web_lookup.yaml
tool: web_search
engine: duckduckgo
query_template: "{{query}} latest policy"
limit: 3
```

---

### 10. code — Safe Code Execution

**Function**: Execute Python code in a restricted sandbox with dangerous imports blocked.

**Usage**: `tool: code`

**Allowed imports**: `json`, `math`, `datetime`, `collections`, `itertools`, `functools`, `re`, `statistics`, `decimal`, `fractions`, `hashlib`, `base64`, `uuid`, `random`, `string`, `textwrap`

**Blocked imports**: `os`, `subprocess`, `sys`, `shutil`, and all modules that could access the filesystem or execute external commands.

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `code` | str | Yes | Python code, supports `{{query}}`, `{{data_map:key}}` placeholders |
| `language` | str | No | Language, default python |
| `timeout` | int | No | Timeout in seconds (reserved), default 10 |

**Return Value**:

| Field | Type | Description |
|-------|------|-------------|
| `text` | str | Standard output (or error message) |
| `stdout` | str | Captured standard output |
| `error` | str\|null | Error message |

**Node Config Example**:

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

## Part 2: Common Tool Protocol

All tool function signatures: `fn(config: dict, session: SessionData) -> dict | str`

- When returning a `dict`, it **must** contain a `"text"` field (output to downstream node's data.text and final reply)
- When returning a `str`, it is automatically wrapped as `{"text": str, "branch": str}`
- Extra fields are automatically passed to the downstream node's `session.data` (e.g., `rows`, `results`, `status_code`)

---

## Part 3: Tool Registration

Tools are registered in two locations, which must be kept in sync:

### 1. In `src/api/main.py` via `ToolRegistry`

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

### 2. In `src/engine/dag.py` via `_register_builtins()`

```python
def _register_builtins(registry: ToolRegistry) -> None:
    from src.engine.tools import (
        api_call, code, db_query, extract_llm, extract_regex,
        llm_tool, rag_search, router, web_search,
    )
    registry.register("llm", llm_tool)
    registry.register("rag_search", rag_search)
    # ... register remaining tools
```

**Note**: The `tool` field value in node YAML must match the registered name (e.g., `tool: rag_search`).

---

## Part 4: CLI Tools

KF provides 3 CLI tools: document ingestion, knowledge base management, and workflow validation.

### Document Ingestion — `python -m src.cli.build`

Scans a directory for document files, chunks them, generates embeddings, and writes to Qdrant.

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `--dir` | str | `data/documents` | Source file directory path |
| `--collection` | str | `default` | Target Qdrant collection name |
| `--chunk-size` | int | `800` | Chunk size in characters (Chinese-friendly) |
| `--chunk-overlap` | int | `128` | Overlap between adjacent chunks in characters |
| `--qdrant-host` | str | `localhost` | Qdrant host address |
| `--qdrant-port` | int | `6334` | Qdrant gRPC port |
| `--ollama-url` | str | `http://localhost:11434/v1` | Ollama address |
| `--embed-model` | str | `nomic-embed-text` | Embedding model name |
| `--extensions` | str | (empty) | Comma-separated extensions. Empty = auto-detect all supported formats |

**Supported Formats**:

| Format | Extensions | Dependency |
|--------|-----------|------------|
| Plain text | `.txt` | None |
| Markdown | `.md` | None |
| PDF | `.pdf` | `pip install pymupdf` |
| Word | `.docx` | `pip install python-docx` |
| Excel | `.xlsx` | `pip install openpyxl` |
| CSV | `.csv` | None |
| HTML | `.html` `.htm` | None |

**Usage Examples**:

```bash
# Basic: auto-detect all formats, ingest into the default collection
python -m src.cli.build

# Specify directory and collection name
python -m src.cli.build --dir data/faq_docs --collection faq_kb

# Custom chunk size (recommended for short texts)
python -m src.cli.build --dir data/kb --collection kb --chunk-size 400 --chunk-overlap 64

# Custom chunk size (recommended for long documents)
python -m src.cli.build --dir data/manuals --collection manuals --chunk-size 1500 --chunk-overlap 200

# Ingest only Markdown and PDF
python -m src.cli.build --extensions .md,.pdf

# Specify remote Qdrant and Ollama
python -m src.cli.build \
  --qdrant-host 10.0.0.5 --qdrant-port 6334 \
  --ollama-url http://gpu-server:11434/v1 \
  --embed-model nomic-embed-text
```

**Chunking Strategy Guide**:

| Scenario | chunk_size | chunk_overlap | Notes |
|----------|-----------|---------------|-------|
| FAQ (short Q&A) | 200-400 | 50 | Short texts, small chunks for precision |
| Product docs | 800 | 128 | **Default**, suitable for Chinese |
| Technical manuals | 1000-1500 | 200 | Long paragraphs, preserve more context |
| Legal contracts | 500-800 | 100 | Precise paragraph-level chunking |

> chunk_size is measured in **characters** (`len(text)`), not words. Works well for both Chinese and English.

---

### KB Management — `python -m src.cli.manage`

Manage collections and documents in Qdrant.

**Global parameters**: `--qdrant-host` `--qdrant-port` available on all subcommands.

| Subcommand | Description | Options |
|------------|-------------|---------|
| `list` | List all collections | `--qdrant-host`, `--qdrant-port` |
| `info <name>` | Collection details (points, dimensions, config) | Same |
| `count <name>` | Point count | Same |
| `browse <name>` | Paginated browse | `--limit 20`, `--offset 0`, `--all` |
| `search <name> <query>` | Semantic search | `--limit 5`, `--ollama-url`, `--embed-model`, `--score-threshold` |
| `delete <name>` | Delete collection (with confirmation) | `--yes` / `-y` skip confirmation |

**Usage Examples**:

```bash
# List all collections
python -m src.cli.manage list
# Output:
# kb
# faq_kb
# l2_test

# Collection details
python -m src.cli.manage info kb
# Output: { "name": "kb", "points_count": 342, "vectors_count": 342, ... }

# Point count
python -m src.cli.manage count kb
# Output: kb: 342 points

# Paginated browse
python -m src.cli.manage browse kb --limit 10       # First 10 items
python -m src.cli.manage browse kb --limit 10 --offset 20  # Starting from item 20
python -m src.cli.manage browse kb --limit 20 --all         # Iterate all pages

# Semantic search
python -m src.cli.manage search kb "refund policy"
python -m src.cli.manage search kb "product price" --limit 3
python -m src.cli.manage search kb "deployment" --score-threshold 0.6

# Delete collection
python -m src.cli.manage delete test_kb         # Interactive confirmation
python -m src.cli.manage delete test_kb --yes   # Skip confirmation

# Remote connection
python -m src.cli.manage list --qdrant-host 10.0.0.5 --qdrant-port 6334
```

**Collections CRUD API**:

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/collections` | List all collection names |
| GET | `/collections/{name}` | Collection details (points_count, vectors_count, config) |
| GET | `/collections/{name}/count` | Point count |
| GET | `/collections/{name}/browse?limit=20&offset=0` | Paginated browse |
| DELETE | `/collections/{name}` | Delete entire collection |
| DELETE | `/collections/{name}/points` | Delete points by ID, body: `{"ids": [1, 2, 3]}` |

```bash
# API examples
curl http://localhost:9000/collections
curl http://localhost:9000/collections/my_kb
curl "http://localhost:9000/collections/my_kb/browse?limit=10&offset=0"
curl -X DELETE http://localhost:9000/collections/my_kb
```

---

### Workflow Validator — `python -m src.cli.validate_workflow`

Validate workflow definitions for correctness.

**Usage**:

```bash
# Validate a single workflow
python -m src.cli.validate_workflow config/workflows/customer_service/workflow.yaml

# Validate a product directory (auto-discovers workflow.yaml)
python -m src.cli.validate_workflow config/workflows/customer_service

# Verbose output
python -m src.cli.validate_workflow config/workflows/default --verbose

# Batch validate all workflows
for d in config/workflows/*/; do
    python -m src.cli.validate_workflow "$d"
done
```

**Validation Checks**:

| Check | Description |
|-------|-------------|
| File existence | workflow.yaml + nodes/*.yaml paths valid |
| Unique node names | No duplicate node names |
| Valid next_type | Must be one of `one` `if-then` `switch` |
| Valid node references | Nodes referenced in `next` are defined |
| No orphan nodes | All non-terminal nodes reachable from start node |
| No dead ends | All non-terminal nodes have a successor (non-empty `next`) |

**Output Examples**:

```
PASS: workflow 'customer_service' (5 nodes, 0 errors)
```

```
FAIL: workflow 'customer_service' (5 nodes, 2 errors)
  ERROR: node 'missing_handler' referenced but not found in nodes/
  ERROR: node 'orphan_node' is unreachable from start
```

---

## Part 5: Tool Development Guide

### Tool Signature

All tools follow a unified function signature:

```python
def my_tool(config: dict, session: SessionData) -> dict:
    ...
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `config` | dict | Full node YAML configuration (including tool, llm_provider, and all fields) |
| `session` | SessionData | Current session object, read/write data_map, long_mem_data, history, nodes, etc. |

**Return value**: `dict` (**must** contain `"text"` field) or `str` (auto-wrapped as `{"text": ..., "branch": ...}`)

---

### Creating a New Tool

#### Step 1: Create the tool file

Create `my_tool.py` under `src/engine/tools/`:

```python
# src/engine/tools/my_tool.py

from src.session.data import SessionData


def my_tool(config: dict, session: SessionData) -> dict:
    param1 = config.get("param1", "default_value")
    param2 = config.get("param2", 10)

    user_query = session.current_query          # Current user input
    previous_data = session.current_context      # Upstream node output text
    stored_kv = session.data_map                 # Cross-node data_map

    result_text = f"processed: {user_query} with {param1}"

    session.data_map["my_result"] = result_text   # Write to cross-node shared state

    return {
        "text": result_text,
        "extra_field": param2,                    # Extra fields passed downstream
    }
```

#### Step 2: Export in `__init__.py`

```python
# src/engine/tools/__init__.py

from .my_tool import my_tool

__all__ = [..., "my_tool"]
```

If the tool imports heavy dependencies like `httpx2` or `LLMClient`, use a **lazy import wrapper** to avoid cascading imports at startup:

```python
# Lazy import wrapper (avoids httpx2 cascading load)
def my_tool(config: dict, session) -> dict:
    from .my_tool import my_tool as _fn
    return _fn(config, session)
```

#### Step 3: Register in `dag.py` `_register_builtins()`

```python
# src/engine/dag.py

def _register_builtins(registry: ToolRegistry) -> None:
    from src.engine.tools import (
        ...,
        my_tool,        # New
    )
    registry.register("my_tool", my_tool)
```

#### Step 4: Register in `api/main.py`

```python
# src/api/main.py

from src.engine.tools import (
    ...,
    my_tool,            # New
)
_registry.register("my_tool", my_tool)
```

#### Step 5: Use in a workflow

Create the node YAML:

```yaml
# config/workflows/my_product/nodes/my_node.yaml
tool: my_tool
param1: "custom_value"
param2: 42
```

Reference in workflow.yaml:

```yaml
# config/workflows/my_product/workflow.yaml
nodes:
  - name: my_node
    next_type: one
    next: ""       # "" indicates terminal node
```

---

### Session Object Usage

```python
session = SessionData()

# Read current turn input
query = session.current_query              # → "user input text"
context = session.current_context          # → upstream node data.text

# Read/write cross-node shared variables
session.data_map["order_id"] = "12345"     # Write
order = session.data_map.get("order_id")   # Read

# Read client-provided long-term memory
long_mem = session.long_mem_data           # → str

# Iterate dialog history (TurnRecord list)
for turn in session.history:
    print(turn.input, turn.output)

# Read session metadata
session.chat_id                            # → "chat_abc123..."
session.turn_id                            # → Current turn number
session._workflow                          # → Workflow name
```

---

### Template Variable Resolution

Multiple tools support `{{variable}}` template syntax. Implement a `_resolve()` helper:

```python
def _resolve(template: str, session: SessionData) -> str:
    result = template.replace("{{query}}", session.current_query)
    result = result.replace("{{chat_id}}", session.chat_id)
    for key, val in session.data_map.items():
        result = result.replace(f"{{{{{key}}}}}", f"{{data_map:{key}}}")  # compat
        result = result.replace(f"{{data_map:{key}}}", str(val))
    return result
```

---

### Logging & Metrics

**Structured Logging**:

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

**Prometheus Metrics**:

```python
from src.metrics.prometheus import llm_calls_total

def my_tool(config: dict, session: SessionData) -> dict:
    # Counter (cumulative)
    llm_calls_total.inc({"model": "my-model"})

    # Histogram (distribution)
    from src.metrics.prometheus import rag_search_duration_ms
    import time
    t0 = time.time()
    result = do_work()
    rag_search_duration_ms.observe((time.time() - t0) * 1000)
```

---

### Writing Tests

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
        assert "text" in result  # Must not crash
```

---

### Development Checklist

```
□ Create src/engine/tools/my_tool.py
□ Function signature: fn(config: dict, session: SessionData) -> dict
□ Return dict must contain "text" field
□ Export in __init__.py (or use lazy import wrapper)
□ Register in dag.py _register_builtins()
□ Register in api/main.py ToolRegistry
□ Write tests/test_my_tool.py
□ Write node YAML config example in docs
□ Run ruff + pytest to verify
```

---

### Forbidden Practices

```
□ Do NOT use os.system / subprocess directly in tool functions
□ Do NOT modify session.nodes in tools (managed by the engine)
□ Do NOT import httpx2 at module top level (use lazy imports inside functions)
□ Do NOT return None or a dict without "text"
```
