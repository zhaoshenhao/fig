# Session 管理 — 开发指南

## 1. 快速入门

### 在 tool 中读取 session

```python
from src.session.data import SessionData

def my_tool(config: dict, session: SessionData) -> dict:
    # 读取当前轮用户输入
    query = session.current_query           # str

    # 读取前一个节点的输出文本
    context = session.current_context       # str

    # 读取跨轮对话历史
    for turn in session.history:
        print(turn.input, turn.output)      # TurnRecord

    # 读取已提取的结构化数据
    order_id = session.data_map.get("order_id", "")

    # 读取长期记忆
    memory = session.long_mem_data

    # 读取 session 元数据
    chat_id = session.chat_id
    workflow = session._workflow
    turn_num = session.turn_id

    return {"text": "done"}
```

### 在 tool 中写入 session

```python
def my_extract_tool(config: dict, session: SessionData) -> dict:
    # 写入 data_map（跨轮保留）
    session.data_map["order_id"] = "ORD-123"
    session.data_map["customer_name"] = "张三"

    # 注意：只写入 str 类型
    session.data_map["count"] = str(3)           # ✅
    # session.data_map["items"] = ["a", "b"]      # ❌ 不能存 list
    session.data_map["items"] = json.dumps(["a", "b"])  # ✅ JSON 字符串

    return {"text": f"extracted {len(session.data_map)} fields"}
```

## 2. 不能做的事

```python
# ❌ 不要直接修改 history
session.history[0].input = "modified"     # 破坏记录

# ❌ 不要依赖 nodes 做跨轮通信
# nodes 每轮结束即清除，下轮为空
prev_data = session.nodes[-1]["data"]     # 上轮数据已不存在

# ✅ 跨轮共享用 data_map
prev_order = session.data_map.get("order_id")

# ❌ 不要直接删 data_map 中的 key（除非明确设计如此）
del session.data_map["order_id"]          # 可能破坏后续逻辑
```

## 3. 常用模式

### 3.1 在 LLM system_prompt 中使用 session 变量

```yaml
# generate.yaml
tool: llm
system_prompt: |
  你是客服助手。

  用户长期画像: {{long_mem}}

  已提取的结构化信息:
  {{data_map}}

  历史对话摘要:
  {{history}}

  当前上下文:
  {{context}}

  用户问题: {{query}}
```

**可用占位符**：

| 占位符 | 展开为 |
|--------|--------|
| `{{query}}` | `session.current_query` |
| `{{context}}` | `session.current_context` |
| `{{data_map}}` | `json.dumps(session.data_map)` |
| `{{long_mem}}` | `session.long_mem_data` (原始文本) |
| `{{history}}` | `"用户: ...\n客服: ..."` 格式的多轮文本 |

### 3.2 在 db_query 中使用 session 变量

```yaml
# query_order.yaml
tool: db_query
db: mysql_main
query: "SELECT * FROM orders WHERE order_id = %s"
params:
  - "{{order_id}}"            # ← data_map 中的值
```

`db_query` 的模板解析还支持 `{{query}}`, `{{chat_id}}`, `{{_workflow}}`, `{{data_map}}`。

### 3.3 编写 extract 工具的正确方式

```python
def my_extract(config: dict, session: SessionData) -> dict:
    query = session.current_query

    # 从用户输入中提取
    match = re.search(r"ORD-\d+", query)
    if match:
        session.data_map["order_id"] = match.group(0)

    # 不要返回大量文本 —— 返回简洁摘要即可
    return {"text": f"extracted order_id", "extracted": ["order_id"]}
```

**为什么 data_map 值必须是 str？**
- 序列化/反序列化时不会有类型损失
- LLM tool 的 `{{data_map}}` 展开为 JSON 字符串，下游自行解析

### 3.4 处理多值提取

```python
# extract_regex 的多值模式
emails = re.findall(r"[\w.]+@[\w.]+", query)
if len(emails) == 1:
    session.data_map["email"] = emails[0]          # 单值直接存
else:
    session.data_map["emails"] = json.dumps(emails) # 多值 JSON 数组

# 下游读取
import json
raw = session.data_map.get("emails", "[]")
email_list = json.loads(raw)
```

## 4. 测试

### 4.1 测试 tool 函数

```python
from src.session.data import SessionData

def test_my_tool():
    session = SessionData()
    session.nodes = [
        {"name": "input", "data": {"text": "我的订单 ORD-123"}},
    ]

    result = my_tool({"key": "value"}, session)

    assert result["text"] == "extracted order_id"
    assert session.data_map["order_id"] == "ORD-123"
```

### 4.2 测试依赖历史对话的 tool

```python
def test_tool_with_history():
    session = SessionData()
    session.nodes = [
        {"name": "input", "data": {"text": "第三个问题"}},
    ]
    session.add_turn("第一个问题", "第一个回答")
    session.add_turn("第二个问题", "第二个回答")

    result = my_tool({}, session)

    assert len(session.history) == 2  # tool 不修改 history
```

### 4.3 测试多轮对话流程

```python
def test_multi_turn():
    # 第 1 轮
    session = SessionData()
    session.nodes = [{"name": "input", "data": {"text": "查订单"}}]
    session.add_turn("查订单", "请提供订单号")

    # nodes 被清除（模拟引擎行为）
    session.nodes.clear()

    # 第 2 轮 — extract 提取订单号
    session.nodes = [{"name": "input", "data": {"text": "ORD-123"}}]
    session.data_map["order_id"] = "ORD-123"
    session.add_turn("ORD-123", "您的订单状态为已发货")

    assert session.turn_id == 2
    assert session.data_map["order_id"] == "ORD-123"
    assert session.history[-1].output == "您的订单状态为已发货"
```

### 4.4 测试 trim/compress

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
    assert len(session.history) == 1  # 不变

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
    # 应有摘要轮 + 保留的 keep 轮
    assert len(session.history) == 6  # 1 summary + 5 recent
    assert session.history[0].input == "[前95轮摘要]"
```

### 4.5 测试存储后端

```python
from src.session.memory import MemorySessionStore

def test_memory_store_lifecycle():
    store = MemorySessionStore(max_age=5, max_sessions=3)
    
    # 创建
    s = store.create("my_wf", "full")
    cid = s["chat_id"]
    assert s["turn_id"] == 0

    # 获取
    loaded = store.get(cid)
    assert loaded is not None

    # 保存
    s.data_map["key"] = "val"
    store.save(s)
    loaded2 = store.get(cid)
    assert loaded2.data_map["key"] == "val"

    # 删除
    assert store.delete(cid) is True
    assert store.get(cid) is None
```

## 5. 添加新的 Storage Backend

1. 创建 `src/session/my_store.py`
2. 继承 `SessionStore`，实现 4 个方法
3. 在 `src/session/__init__.py` 的 `create_session_store()` 中添加分支

```python
# src/session/my_store.py
from src.session.base import SessionStore
from src.session.data import SessionData

class MyCustomStore(SessionStore):
    def get(self, chat_id: str) -> SessionData | None:
        ...

    def create(self, workflow_name: str, return_mode: str) -> SessionData:
        ...

    def save(self, session: SessionData) -> None:
        ...

    def delete(self, chat_id: str) -> bool:
        ...
```

## 6. Session 生命周期详解

```
┌────────────────────────────────────────────────────┐
│  新会话 (chat_id = null)                            │
│  store.create(workflow_name, return_mode)           │
│  → SessionData(chat_id=chat_xxx, turn_id=0, ...)   │
│  → 存入 Memory/Redis                                │
└──────────────┬─────────────────────────────────────┘
               │
               ▼
┌────────────────────────────────────────────────────┐
│  续接 (chat_id = "chat_xxx")                       │
│  store.get(chat_id)                                │
│  → Memory: 检查 TTL → from_dict()                   │
│  → Redis:  GET → json.loads → from_dict()          │
│  → 不存在/过期 → 404                                │
│  → _workflow 不匹配 → 400                           │
└──────────────┬─────────────────────────────────────┘
               │
               ▼
┌────────────────────────────────────────────────────┐
│  DAG 执行                                           │
│  dag_engine.run(workflow_name, query, session)      │
│  ├─ nodes.append(input_entry)                       │
│  ├─ _traverse → _walk → tool_fn(session)            │
│  ├─ _finish → nodes.append(output_entry)            │
│  ├─ _collect_metrics(session.nodes → SQLite)        │
│  ├─ session.add_turn(query, answer)                 │
│  │    → turn_id += 1                                │
│  │    → history.append(TurnRecord(...))             │
│  ├─ session.trim_or_compress(...)                   │
│  │    → 仅操作 history                               │
│  └─ session.nodes.clear()                            │
└──────────────┬─────────────────────────────────────┘
               │
               ▼
┌────────────────────────────────────────────────────┐
│  持久化                                             │
│  store.save(session)                               │
│  → last_active_at = now                            │
│  → to_dict() → Memory/Redis                        │
│  → _build_response(session)                        │
│    → chat_id, turn_id, history[-1].output          │
└────────────────────────────────────────────────────┘
```

**注意**: 如果在 `run()` 中抛出异常：
- `add_turn` 不会被调用（状态不更新）
- `nodes` 不会被清除
- session 不会被 `save()`
- API 返回 500，客户端可重试（session 状态不变）

### 后台清理 (Memory 模式)

应用启动时，FastAPI lifespan 会启动一个 daemon 线程，按 `cleanup_interval` 秒间隔扫描并删除过期 session：

```python
# src/api/main.py — lifespan
if isinstance(_session_store, MemorySessionStore) and sc.cleanup_interval > 0:
    _cleanup_thread = threading.Thread(
        target=_session_store.cleanup_loop,
        args=(sc.cleanup_interval, stop_event),
        daemon=True,
    )
    _cleanup_thread.start()
```

同时 `get()` 调用时也会惰性检查 TTL，双重保障不会返回过期 session。

## 7. 常见陷阱

### 7.1 试图在 tool 中获取上一轮的数据

```python
# ❌ 错误 — nodes 已清除
last_answer = session.nodes[-1]["data"]["text"]

# ✅ 正确 — 用 history 或 data_map
last_answer = session.history[-1].output
# 或提前在 extract 中把需要的值写入 data_map
```

### 7.2 忘记 data_map 值必须是 str

```python
# ❌ 错误
session.data_map["score"] = 95

# ✅ 正确
session.data_map["score"] = "95"
```

### 7.3 在 trim 后依赖 history 长度做索引

```python
# 危险 — trim 可能触发，长度会变
assert len(session.history) == 100

# 安全 — 用 completed_turns 属性
print(f"共 {session.completed_turns} 轮对话")
```

### 7.4 混用 workflow

```python
# ❌ API 层会拒绝 — 400 Bad Request
# session._workflow = "default"
# POST /workflows/other/run  {"chat_id": "chat_xxx"}
```

## 8. 配置参考

### 完整 config/session.yaml

```yaml
store: memory              # memory | redis

max_age: 3600              # 会话 TTL（秒）

max_turns: 100             # 触发 trim 的轮数阈值
max_chars: 100000          # 触发 trim 的字符数阈值
keep: 20                   # trim 后保留的最少轮数
compress_max_words: 1000   # LLM 摘要最大字数
cleanup_interval: 300      # memory 模式后台清理间隔（秒），0 禁用

memory:
  max_sessions: 2000       # 内存模式下最大 session 数

redis:
  url: redis://localhost:6379/0
  prefix: "kf:sess:"

summary:                   # 可选
  base_url: "https://api.deepseek.com/v1"
  api_key: "${DEEPSEEK_KEY}"
  model: "deepseek-v4-flash"
  system_prompt: "请将以下对话压缩为{max_words}字以内的摘要..."
```

### 存储后端清理机制

| 后端 | 清理方式 |
|------|---------|
| Memory | `cleanup_interval` 秒间隔 daemon 线程扫描过期 session + `get()` 惰性检查 |
| Redis | `SETEX` TTL，Redis 自动删除过期 key，`get()` 返回 `None` |

### 工作流级 session 覆盖

```yaml
# config/workflows/my_product/workflow.yaml
session:                   # 可选，override 全局配置
  max_turns: 50            # 仅覆盖此项，其余继承全局
```

### 代码中读取配置

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

## 9. 调试技巧

### 查看当前 session 状态

```python
# 在 tool 中加日志
import logging
logger = logging.getLogger(__name__)

def my_tool(config, session):
    logger.debug(f"chat_id={session.chat_id} turn={session.turn_id}")
    logger.debug(f"data_map={session.data_map}")
    logger.debug(f"history length={len(session.history)}")
    logger.debug(f"current_query={session.current_query}")
    logger.debug(f"current_context={session.current_context}")
```

### 检查 session 序列化大小

```python
import json
raw = session.to_dict()
size = len(json.dumps(raw, ensure_ascii=False))
print(f"session size: {size} bytes")

# 如果过大，考虑:
# 1. 降低 keep 值
# 2. 开启 compress
# 3. 减少 data_map 中不必要的 key
```

### 手动触发 trim 进行测试

```python
# 创建大量历史模拟长会话
session = SessionData()
for i in range(200):
    session.add_turn(f"问题 {i}" * 100, f"答案 {i}" * 100)

# 手动触发
session.trim_or_compress(max_turns=50, keep=10)
print(f"trim 后: {len(session.history)} 轮")  # 10 或 11 (含摘要)
```

## 10. 文件索引

| 文件 | 说明 |
|------|------|
| `src/session/data.py` | TurnRecord + SessionData 定义 |
| `src/session/base.py` | SessionStore ABC |
| `src/session/memory.py` | MemorySessionStore |
| `src/session/redis_store.py` | RedisSessionStore |
| `src/session/__init__.py` | 导出 + create_session_store |
| `config/session.yaml` | 配置文件 |
| `tests/test_session_store.py` | 测试用例 (466行) |
| `docs/session-design.md` | 设计规范（本文档的架构版） |
