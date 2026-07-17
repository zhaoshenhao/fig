[中文](session_CN.md)

# Session Management — Complete Guide

## 1. Overview

Session is the core data carrier for multi-turn conversations. It carries cross-turn memory (`history`), inter-node structured data (`data_map`), long-term memory (`long_mem_data`), and current-turn DAG execution logs (`nodes`).

```
Session Lifecycle:  create → [run → add_turn → trim → clear_nodes → save] × N → delete
```

---

## 2. Data Structures

### 2.1 TurnRecord — Single Turn Record

`src/session/data.py`

```python
@dataclass
class TurnRecord:
    input: str              # User input
    output: str             # System reply
    input_timestamp: float  # Input timestamp
    output_timestamp: float # Reply timestamp
```

### 2.2 SessionData — Session Body

`src/session/data.py`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `chat_id` | `str` | `chat_{uuid4.hex[:20]}` | Unique ID, generated on creation |
| `turn_id` | `int` | `0` | Turn counter, increments after each `add_turn` |
| `created_at` | `float` | `time.time()` | Creation timestamp |
| `last_active_at` | `float` | `time.time()` | Updated on each `save()` |
| `_workflow` | `str` | `""` | Bound workflow name (no cross-workflow mixing) |
| `return_mode` | `str` | `"full"` | Return mode: `"full"` or `"text"` |
| `title` | `str` | `""` | Session title (externally writable for integration management) |
| `tags` | `list[str]` | `[]` | Session tags |
| `history` | `list[TurnRecord]` | `[]` | Cross-turn memory ← participates in trim/compress |
| `data_map` | `dict[str,str]` | `{}` | Structured data (written by extract tools) |
| `long_mem_data` | `str` | `""` | Long-term memory (client-provided, persistent) |
| `nodes` | `list[dict]` | `[]` | Current-turn DAG execution log (cleared after each turn) |

---

## 3. Field Lifecycle

| Field | Writer | Persisted | Cross-turn | trim/compress |
|-------|--------|-----------|------------|---------------|
| `chat_id` | Auto | ✅ Serialized | ✅ Unchanged | ❌ |
| `turn_id` | Engine | ✅ Serialized | ✅ Increments | ❌ |
| `history` | Engine | ✅ Serialized | ✅ Accumulates | ✅ **(only this field)** |
| `data_map` | extract tools | ✅ Serialized | ✅ Accumulates (never cleared) | ❌ |
| `long_mem_data` | client | ✅ Serialized | ✅ Unchanged (write-once) | ❌ |
| `nodes` | Engine | ❌ Cleared per turn | ❌ | ❌ |

### Key Constraints

- `history` is the **only** field participating in trim/compress
- `nodes` is only valid for the current turn, cleared after each run (`session.nodes.clear()`)
- `data_map` is never cleared, accumulates across turns
- `long_mem_data` is written once by the client and persists forever

---

## 4. Detailed Field Usage

### 4.1 history — Cross-turn Memory

The LLM tool expands it into user/assistant message pairs for context injection:

```python
for turn in session.history:
    messages.append({"role": "user", "content": turn.input})
    messages.append({"role": "assistant", "content": turn.output})
```

How turns are added (called automatically by the engine):

```python
session.add_turn(query_text, answer_text)
# → history.append(TurnRecord(input, output, now, now))
# → turn_id += 1
```

### 4.2 data_map — Inter-node Structured Sharing

`extract_llm` / `extract_regex` tools extract information from user input and write to `data_map`:

```python
# extract_llm example
session.data_map["order_id"] = "ORD-20240101"
session.data_map["phone"] = "13800138000"

# extract_regex multi-value example
session.data_map["emails"] = json.dumps(["a@x.com", "b@x.com"])
```

Other nodes read via:

- **LLM tool**: use `{{data_map}}` in system_prompt, auto-expanded to JSON
- **db_query**: use `{{data_map}}` or `{{data_map:key}}` in SQL
- **In code**: `session.data_map.get("order_id")`

> **Important**: `data_map` values are always `str` type. Use `json.dumps(list)` for multiple values.

### 4.3 long_mem_data — Long-term Memory

Provided once by the client and never changed. Used for user profiles, preferences, and other cross-session persistent information:

```bash
curl -X POST /workflows/default/run \
  -d '{"query": "Check my order", "chat_id": "chat_xxx", "long_mem_data": "VIP customer, prefers concise replies"}'
```

Referenced in templates as `{{long_mem}}`.

### 4.4 nodes — Current-turn DAG Log

Valid only for the current turn. Records the complete DAG execution path:

```python
[
    {"name": "input",    "pre": None,     "data": {"text": "Check order ORD-123"}, ...},
    {"name": "retrieve", "pre": "input",  "data": {"text": "Relevant KB content..."}, ...},
    {"name": "generate", "pre": "retrieve","data": {"text": "Your order..."}, ...},
    {"name": "output",   "pre": "generate","data": {"text": "Your order..."}, ...},
]
```

After each turn, `session.nodes.clear()` clears it; the next turn rebuilds from scratch.

> **Do not rely on nodes data across turns in tool implementations. Use `data_map` for cross-turn data sharing.**

### 4.5 current_query / current_context — Convenience Properties

`src/session/data.py:332-359`

```python
@property
def current_query(self) -> str:
    """Searches nodes in reverse for the last input node's data.text"""
    ...

@property
def current_context(self) -> str:
    """Searches nodes in reverse for the last non-input node's data.text"""
    ...

@property
def completed_turns(self) -> int:
    """Returns the length of the history list"""
    return len(self.history)
```

---

## 5. Complete Execution Flow

### 5.1 DAG Execution (DAGEngine.run)

```
                    ┌──────────────────┐
                    │  session.nodes   │
                    │  ← [] (empty)    │
                    └────────┬─────────┘
                             │
  ① session.nodes.append(input_entry)
                             │
  ② _traverse(session, nodes, product)
     │                        │
     ├─ tool_fn(config, s)  ─┤ session.current_query    ← nodes[-input]
     │                        │ session.current_context  ← nodes[-non-input]
     │                        │ session.history          ← TurnRecord[]
     │                        │ session.data_map         ← {str:str}
     │                        │ session.long_mem_data    ← str
     │                        │
     └─ session.nodes.append(output_entry)
                             │
  ③ _finish(session, return_mode) → append output node
                             │
  ④ _collect_metrics(session, ...) → SQLite/MySQL/PG
                             │
  ⑤ session.add_turn(query, answer) → append to history
                             │
  ⑥ session.trim_or_compress(...) → operates only on history
                             │
  ⑦ session.nodes.clear()    → nodes = []
                    ┌────────┴─────────┐
                    │  session.nodes   │
                    │  ← [] (empty)    │
                    └──────────────────┘
```

### 5.2 API Layer Sequence

```
POST /workflows/{name}/run  {chat_id, query, long_mem_data}
  │
  ├─ 1. Get session
  │     chat_id provided → store.get(chat_id)   ← resume
  │     chat_id empty    → store.create(name, mode)  ← new
  │
  ├─ 2. Inject long_mem_data
  │     session.long_mem_data = req.long_mem_data
  │
  ├─ 3. Execute DAG
  │     asyncio.to_thread(dag_engine.run, name, query, session)
  │
  ├─ 4. Persist
  │     store.save(session)
  │
  └─ 5. Return
       {"chat_id": "chat_xxx", "turn_id": 5, "reply": "..."}
```

### 5.3 Exception Handling

If an exception is thrown during `run()`:
- `add_turn` is not called (state is not updated)
- `nodes` is not cleared
- Session is not `save()`d
- API returns 500, client can retry (session state unchanged)

---

## 6. Trim / Compress Algorithm

### 6.1 Trigger Conditions

Either condition triggers the operation:
- `total_turns > max_turns`
- `total_chars > max_chars`

(No trigger when both are `None`)

### 6.2 Algorithm Flow

```
trim_or_compress(max_turns, max_chars, keep, compress_max_words, summary_*)

  ① Check trigger
     total_turns > max_turns? OR total_chars > max_chars?
     NO  → return
     YES →
  ② Calculate excess
     excess = total_turns - keep
     excess <= 0 → return (keep all, no action needed)
  ③ Split history
     old_turns = history[:excess]   ← removed old turns
     history   = history[excess:]   ← kept recent keep turns
  ④ Optional: generate summary
     Summary LLM configured?
     YES → _generate_summary(old_turns) → LLM summary
     NO  → skip
  ⑤ Insert summary
     summary_text non-empty?
     YES → history.insert(0, TurnRecord("[Summary of first N turns]", summary_text, ...))
     NO  → do nothing (hard truncation)

_generate_summary failure → silent fallback to hard truncation
```

### 6.3 Configuration

```yaml
# config/session.yaml
max_turns: 100            # Turn count threshold to trigger trim
max_chars: 100000         # Character count threshold to trigger trim
keep: 20                  # Minimum turns to keep after trim
compress_max_words: 1000  # Maximum words for LLM summary

summary:                  # Optional; hard truncation if not configured
  base_url: "https://api.deepseek.com/v1"
  api_key: "${DEEPSEEK_API_KEY}"
  model: "deepseek-v4-flash"
  system_prompt: "Compress the following conversation to {max_words} words or fewer..."
```

> `summary` uses an independent LLM provider configuration, unrelated to the workflow chat LLM. This allows using a cheaper model for summarization.

### 6.4 Design Constraints

- `keep` minimum value is forced to 1, preventing complete history loss
- Turn 1 is never trimmed (`excess=0` when `total_turns=1`)
- Summary turn is inserted at history head as `TurnRecord("[Summary of first N turns]", summary_text)`
- `nodes`, `data_map`, `long_mem_data` do not participate in trim

---

## 7. Storage Backends

### 7.1 Abstract Interface

`src/session/base.py` — `SessionStore` (ABC)

```python
class SessionStore(ABC):
    def get(self, chat_id: str) -> SessionData | None: ...
    def create(self, workflow_name: str, return_mode: str) -> SessionData: ...
    def save(self, session: SessionData) -> None: ...
    def delete(self, chat_id: str) -> bool: ...
```

### 7.2 MemorySessionStore

`src/session/memory.py`

- In-process `dict[str, dict]` storage
- **Thread-safe**: `threading.Lock` protects all read/write operations
- **TTL**: lazy check on `get()` + background daemon thread periodic cleanup
- **LRU**: when creating a new session and `max_sessions` is exceeded, evicts the oldest
- Additional methods: `touch(chat_id)`, `cleanup_expired()`

```
Use case: development / single-instance deployment
Config:
  memory:
    max_sessions: 2000
  cleanup_interval: 300   # background cleanup interval (seconds), 0 disables
```

### 7.3 RedisSessionStore

`src/session/redis_store.py`

- External Redis storage
- `SETEX {prefix}{chat_id} max_age json_data`
- TTL managed automatically by Redis
- **Lazy import**: fails at construction time if `redis` package is not installed (not at import time)

```
Use case: production / multi-instance deployment
Config:
  redis:
    url: redis://localhost:6379/0
    prefix: "kf:sess:"
```

### 7.4 Factory

`src/session/__init__.py` — `create_session_store(config)`

```python
from src.session import create_session_store

store = create_session_store({"store": "memory"})
store = create_session_store({"store": "redis", "redis": {"url": "..."}})
```

### 7.5 Cleanup Mechanism Comparison

| Backend | Cleanup Method |
|---------|---------------|
| Memory | `cleanup_interval`-second daemon thread scanning + `get()` lazy check |
| Redis | `SETEX` TTL, Redis auto-deletes expired keys, `get()` returns `None` |

---

## 8. Dict Compatibility Protocol

SessionData implements dict-like access; all existing `session["key"]` syntax works without changes:

```python
session["_workflow"]                      # __getitem__ → getattr
session["return_mode"] = "full"           # __setitem__ → setattr
session.get("bogus", "fallback")          # .get → fallback
"chat_id" in session                      # __contains__ → hasattr
session.setdefault("_workflow", "default")  # set if not exists
session.keys()                            # returns set of dataclass field names
```

---

## 9. Serialization

```python
session.to_dict()            # dataclasses.asdict → dict
SessionData.from_dict(data)  # dict → SessionData
```

`from_dict` is backward-compatible with the legacy `{role, content}` history format (fallback: `item["content"]` → `input`).

> `to_dict()` includes all fields. Since nodes are cleared after execution, serialized sessions do not contain nodes.

---

## 10. API Contract

### Request

```
POST /workflows/{name}/run
{
    "query": "Check my order",
    "chat_id": "chat_xxx",          // optional; creates new if empty
    "long_mem_data": "VIP customer"  // optional; retained after first submission
}
```

### Response

```json
{
    "chat_id": "chat_a1b2c3d4e5f6g7h8i9j0",
    "turn_id": 3,
    "reply": "Your order details are as follows..."
}
```

> `data_map`, `long_mem_data`, `history`, and `nodes` are not returned. These are server-side internal state.

### Delete

```
DELETE /sessions/{chat_id}
→ 204 No Content   (success)
→ 404 Not Found    (not found)
```

### Workflow Isolation

Cross-workflow session mixing is not allowed. The API layer validates `_workflow` match and returns 400 on mismatch.

---

## 11. Development Guide

### 11.1 Reading Session in Tools

```python
from src.session.data import SessionData

def my_tool(config: dict, session: SessionData) -> dict:
    query = session.current_query           # current turn user input
    context = session.current_context       # previous node output text

    for turn in session.history:            # cross-turn dialogue history
        print(turn.input, turn.output)

    order_id = session.data_map.get("order_id", "")  # structured data
    memory = session.long_mem_data                   # long-term memory
    chat_id = session.chat_id                        # session ID
    workflow = session._workflow                     # bound workflow
    turn_num = session.turn_id                       # current turn number

    return {"text": "done"}
```

### 11.2 Writing Session in Tools

```python
def my_extract_tool(config: dict, session: SessionData) -> dict:
    session.data_map["order_id"] = "ORD-123"
    session.data_map["customer_name"] = "Zhang San"

    # Note: only write str type values
    session.data_map["count"] = str(3)                      # ✅
    session.data_map["items"] = json.dumps(["a", "b"])      # ✅ JSON string
    # session.data_map["items"] = ["a", "b"]                 # ❌ cannot store list

    return {"text": f"extracted {len(session.data_map)} fields"}
```

### 11.3 Template Placeholders

Placeholders available in LLM tool system_prompt:

| Placeholder | Expands to |
|-------------|-----------|
| `{{query}}` | `session.current_query` |
| `{{context}}` | `session.current_context` |
| `{{data_map}}` | `json.dumps(session.data_map)` |
| `{{data_map:key}}` | `session.data_map["key"]` |
| `{{long_mem}}` | `session.long_mem_data` (raw text) |
| `{{history}}` | `"User: ...\nAssistant: ..."` formatted multi-turn text |

db_query SQL templates also support `{{query}}`, `{{chat_id}}`, `{{_workflow}}`, `{{data_map}}`.

### 11.4 What NOT to Do

```python
# ❌ Do not directly modify history
session.history[0].input = "modified"     # corrupts records

# ❌ Do not rely on nodes for cross-turn communication (cleared each turn)
prev_data = session.nodes[-1]["data"]     # previous turn data no longer exists

# ✅ Use data_map for cross-turn sharing
prev_order = session.data_map.get("order_id")

# ❌ Do not arbitrarily delete data_map keys (may break downstream logic)
del session.data_map["order_id"]

# ❌ Do not rely on absolute history length for indexing after trim
assert len(session.history) == 100        # trim may have fired

# ✅ Use completed_turns property
print(f"Total completed turns: {session.completed_turns}")
```

### 11.5 Handling Multi-value Extraction

```python
# extract_regex multi-value pattern
emails = re.findall(r"[\w.]+@[\w.]+", query)
if len(emails) == 1:
    session.data_map["email"] = emails[0]           # single value, store directly
else:
    session.data_map["emails"] = json.dumps(emails) # multi-value, JSON array

# Downstream reading
import json
raw = session.data_map.get("emails", "[]")
email_list = json.loads(raw)
```

---

## 12. Testing

### 12.1 Testing Tool Functions

```python
from src.session.data import SessionData

def test_my_tool():
    session = SessionData()
    session.nodes = [
        {"name": "input", "data": {"text": "My order ORD-123"}},
    ]
    result = my_tool({"key": "value"}, session)
    assert result["text"] == "extracted order_id"
    assert session.data_map["order_id"] == "ORD-123"
```

### 12.2 Testing Tools with History Dependencies

```python
def test_tool_with_history():
    session = SessionData()
    session.nodes = [
        {"name": "input", "data": {"text": "Third question"}},
    ]
    session.add_turn("First question", "First answer")
    session.add_turn("Second question", "Second answer")
    result = my_tool({}, session)
    assert len(session.history) == 2  # tool does not modify history
```

### 12.3 Testing Multi-turn Workflow

```python
def test_multi_turn():
    session = SessionData()
    session.nodes = [{"name": "input", "data": {"text": "Check order"}}]
    session.add_turn("Check order", "Please provide your order number")
    session.nodes.clear()  # simulate engine behavior

    session.nodes = [{"name": "input", "data": {"text": "ORD-123"}}]
    session.data_map["order_id"] = "ORD-123"
    session.add_turn("ORD-123", "Your order status is: shipped")

    assert session.turn_id == 2
    assert session.data_map["order_id"] == "ORD-123"
    assert session.history[-1].output == "Your order status is: shipped"
```

### 12.4 Testing trim/compress

```python
from src.session.data import SessionData

def test_trim_basic():
    session = SessionData()
    for i in range(50):
        session.add_turn(f"q{i}", f"a{i}")
    session.trim_or_compress(max_turns=30, keep=10)
    assert len(session.history) == 10
    assert session.history[0].input == "q40"
    assert session.history[-1].input == "q49"

def test_trim_noop_when_under():
    session = SessionData()
    session.add_turn("q", "a")
    session.trim_or_compress(max_turns=10, keep=5)
    assert len(session.history) == 1  # unchanged

def test_compress_with_summary():
    session = SessionData()
    for i in range(100):
        session.add_turn(f"question {i}", f"answer {i}")
    session.trim_or_compress(
        max_turns=50, keep=5, compress_max_words=500,
        summary_base_url="http://localhost:11434/v1",
        summary_api_key="",
        summary_model="llama3",
    )
    assert len(session.history) == 6  # 1 summary + 5 recent
    assert session.history[0].input == "[Summary of first 95 turns]"
```

### 12.5 Testing Storage Backends

```python
from src.session.memory import MemorySessionStore

def test_memory_store_lifecycle():
    store = MemorySessionStore(max_age=5, max_sessions=3)
    s = store.create("my_wf", "full")
    cid = s["chat_id"]
    assert s["turn_id"] == 0

    loaded = store.get(cid)
    assert loaded is not None

    s.data_map["key"] = "val"
    store.save(s)
    loaded2 = store.get(cid)
    assert loaded2.data_map["key"] == "val"

    assert store.delete(cid) is True
    assert store.get(cid) is None
```

---

## 13. Adding a New Storage Backend

1. Create `src/session/my_store.py`
2. Subclass `SessionStore`, implement the 4 methods
3. Add a branch in `src/session/__init__.py`'s `create_session_store()`

```python
from src.session.base import SessionStore
from src.session.data import SessionData

class MyCustomStore(SessionStore):
    def get(self, chat_id: str) -> SessionData | None: ...
    def create(self, workflow_name: str, return_mode: str) -> SessionData: ...
    def save(self, session: SessionData) -> None: ...
    def delete(self, chat_id: str) -> bool: ...
```

---

## 14. Configuration Reference

### 14.1 Complete config/session.yaml

```yaml
store: memory              # memory | redis

max_age: 3600              # session TTL (seconds)

max_turns: 100             # turn count threshold to trigger trim
max_chars: 100000          # character count threshold to trigger trim
keep: 20                   # minimum turns to keep after trim
compress_max_words: 1000   # max words for LLM summary
cleanup_interval: 300      # memory mode background cleanup interval (seconds), 0 disables

memory:
  max_sessions: 2000       # max sessions in memory mode

redis:
  url: redis://localhost:6379/0
  prefix: "kf:sess:"

summary:                   # optional
  base_url: "https://api.deepseek.com/v1"
  api_key: "${DEEPSEEK_API_KEY}"
  model: "deepseek-v4-flash"
  system_prompt: "Compress the following conversation to {max_words} words or fewer..."
```

### 14.2 Workflow-level Session Override

```yaml
# config/workflows/my_product/workflow.yaml
session:                   # optional, overrides global config
  max_turns: 50            # only overrides this item; others inherit from global
```

### 14.3 Reading Config in Code

```python
from src.config import get_app_config

app = get_app_config()
sc = app.session           # SessionConfig

print(sc.store)            # "memory"
print(sc.max_turns)        # 100
print(sc.max_chars)        # 100000
print(sc.keep)             # 20
print(sc.cleanup_interval) # 300
print(sc.summary.model)    # "deepseek-v4-flash"
```

---

## 15. Debugging Tips

### 15.1 Inspecting Current Session State

```python
import logging
logger = logging.getLogger(__name__)

def my_tool(config, session):
    logger.debug(f"chat_id={session.chat_id} turn={session.turn_id}")
    logger.debug(f"data_map={session.data_map}")
    logger.debug(f"history length={len(session.history)}")
    logger.debug(f"current_query={session.current_query}")
    logger.debug(f"current_context={session.current_context}")
```

### 15.2 Checking Session Serialization Size

```python
import json
raw = session.to_dict()
size = len(json.dumps(raw, ensure_ascii=False))
print(f"session size: {size} bytes")

# If too large, consider:
# 1. Lowering the keep value
# 2. Enabling compress
# 3. Reducing unnecessary keys in data_map
```

### 15.3 Manually Triggering Trim for Testing

```python
session = SessionData()
for i in range(200):
    session.add_turn(f"Question {i}" * 100, f"Answer {i}" * 100)

session.trim_or_compress(max_turns=50, keep=10)
print(f"After trim: {len(session.history)} turns")  # 10 or 11 (with summary)
```

---

## 16. Common Pitfalls

| Pitfall | Wrong Approach | Correct Approach |
|---------|---------------|-----------------|
| Getting previous turn data | `session.nodes[-1]["data"]` (cleared) | `session.history[-1].output` or `data_map` |
| Storing non-str in data_map | `session.data_map["score"] = 95` | `session.data_map["score"] = "95"` |
| Directly modifying history | `session.history[0].input = "x"` | Do not modify history |
| Depending on absolute turn count | `assert len(session.history) == 100` | `session.completed_turns` |
| Cross-workflow session mixing | Using workflow A's session for workflow B | API layer returns 400 |

---

## 17. Architecture Diagram

```
┌─────────────────────────────────────────────────────┐
│                     API Layer                        │
│  POST /run  →  get/create  →  run  →  save  →  response │
│  DELETE     →  delete  →  204/404                         │
└────────┬────────────────────────────────┬───────────┘
         │                                │
    ┌────▼─────┐                    ┌─────▼──────┐
    │ Session  │                    │  DAGEngine │
    │  Store   │── get/create ───→ │            │
    │          │←── save/delete ─── │  _traverse│
    │ Memory   │                    │  _finish  │
    │ Redis    │                    │  add_turn │
    └──────────┘                    │  trim     │
                                    │  clear_nodes│
                                    └─────┬──────┘
                                          │
                                    ┌─────▼──────┐
                                    │  Session   │
                                    │   Data     │
                                    │            │
                                    │ history ←──┤ Cross-turn memory
                                    │ data_map ←─┤ Structured data
                                    │ long_mem   │ Long-term memory
                                    │ nodes (tmp)│ Current turn
                                    └────────────┘
```

---

## 18. File Index

| File | Responsibility |
|------|---------------|
| `src/session/data.py` | SessionData + TurnRecord definitions, trim/compress algorithm |
| `src/session/base.py` | SessionStore abstract interface (ABC) |
| `src/session/memory.py` | MemorySessionStore implementation |
| `src/session/redis_store.py` | RedisSessionStore implementation |
| `src/session/__init__.py` | Exports + create_session_store factory function |
| `src/config.py` | SessionConfig + SummaryConfig loading |
| `config/session.yaml` | Global session configuration |
| `src/engine/dag.py` | DAGEngine.run — session operation entry point |
| `src/api/routes_chat.py` | Chat API endpoints — session create/get/save/delete |
| `src/llm/client.py` | LLMClient — summary generation (lazy import) |
| `tests/test_session_store.py` | SessionData + Store tests |
