[English](session_EN.md)

# Session 管理 — 完整指南

## 1. 概述

Session 是多轮对话的核心数据载体。它承载跨轮次记忆（`history`）、节点间结构化数据（`data_map`）、长期记忆（`long_mem_data`）以及当前轮次 DAG 执行日志（`nodes`）。

```
Session 生命周期:  create → [run → add_turn → trim → clear_nodes → save] × N → delete
```

---

## 2. 数据结构

### 2.1 TurnRecord —— 单轮记录

`src/session/data.py`

```python
@dataclass
class TurnRecord:
    input: str              # 用户输入
    output: str             # 系统回复
    input_timestamp: float  # 输入时间戳
    output_timestamp: float # 回复时间戳
```

### 2.2 SessionData —— 会话主体

`src/session/data.py`

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `chat_id` | `str` | `chat_{uuid4.hex[:20]}` | 唯一标识，仅创建时生成 |
| `turn_id` | `int` | `0` | 轮次计数，每轮 `add_turn` 后 +1 |
| `created_at` | `float` | `time.time()` | 创建时间戳 |
| `last_active_at` | `float` | `time.time()` | 每次 `save()` 更新 |
| `_workflow` | `str` | `""` | 所属 workflow，禁止跨 workflow 混用 |
| `return_mode` | `str` | `"full"` | 返回模式：`"full"` 或 `"text"` |
| `title` | `str` | `""` | 会话标题（外部可读写，便于集成方管理） |
| `tags` | `list[str]` | `[]` | 会话标签 |
| `history` | `list[TurnRecord]` | `[]` | 跨轮次对话记忆 ← 参与 trim/compress |
| `data_map` | `dict[str,str]` | `{}` | 结构化数据（extract 工具写入） |
| `long_mem_data` | `str` | `""` | 长期记忆（client 传入，持久保留） |
| `nodes` | `list[dict]` | `[]` | 当前轮 DAG 执行日志（每轮结束后清除） |

---

## 3. 字段生命周期

| 字段 | 写入者 | 持久化 | 跨轮次 | trim/compress |
|------|--------|--------|--------|---------------|
| `chat_id` | 自生成 | ✅ 序列化 | ✅ 不变 | ❌ |
| `turn_id` | 引擎 | ✅ 序列化 | ✅ 递增 | ❌ |
| `history` | 引擎 | ✅ 序列化 | ✅ 累积 | ✅ **（仅此字段）** |
| `data_map` | extract 工具 | ✅ 序列化 | ✅ 累积（永不清除） | ❌ |
| `long_mem_data` | client | ✅ 序列化 | ✅ 不变（只写一次） | ❌ |
| `nodes` | 引擎 | ❌ 每轮清除 | ❌ | ❌ |

### 关键约束

- `history` 是**唯一**参与 trim/compress 的字段
- `nodes` 仅保留当前轮次，每轮执行完毕后自动清除（`session.nodes.clear()`）
- `data_map` 永不清除，跨轮累积
- `long_mem_data` client 传入一次即永久保留

---

## 4. Field 详细说明

### 4.1 history —— 跨轮次记忆

LLM tool 会将其展开为 user/assistant 消息对注入上下文：

```python
for turn in session.history:
    messages.append({"role": "user", "content": turn.input})
    messages.append({"role": "assistant", "content": turn.output})
```

每轮添加方式（引擎自动调用）：

```python
session.add_turn(query_text, answer_text)
# → history.append(TurnRecord(input, output, now, now))
# → turn_id += 1
```

### 4.2 data_map —— 节点间结构化共享

`extract_llm` / `extract_regex` 工具从用户输入中提取信息，写入 `data_map`：

```python
# extract_llm 示例
session.data_map["order_id"] = "ORD-20240101"
session.data_map["phone"] = "13800138000"

# extract_regex 多值示例
session.data_map["emails"] = json.dumps(["a@x.com", "b@x.com"])
```

其他节点通过以下方式读取：

- **LLM tool**：system_prompt 中使用 `{{data_map}}`，自动展开为 JSON
- **db_query**：SQL 中使用 `{{data_map}}` 或 `{{data_map:key}}`
- **代码中**：`session.data_map.get("order_id")`

> **重要**：`data_map` 值始终是 `str` 类型。多值用 `json.dumps(list)` 存储。

### 4.3 long_mem_data —— 长期记忆

client 传入一次，不再改变。用于存储用户画像、偏好等跨会话的持久信息：

```bash
curl -X POST /workflows/default/run \
  -d '{"query": "帮我查订单", "chat_id": "chat_xxx", "long_mem_data": "VIP客户, 偏好简洁回复"}'
```

节点中通过 `{{long_mem}}` 占位符使用。

### 4.4 nodes —— 当前轮 DAG 日志

仅当前轮次有效。记录本轮的完整 DAG 执行路径：

```python
[
    {"name": "input",    "pre": None,     "data": {"text": "帮我查订单 ORD-123"}, ...},
    {"name": "retrieve", "pre": "input",  "data": {"text": "相关知识库内容..."}, ...},
    {"name": "generate", "pre": "retrieve","data": {"text": "您的订单..."}, ...},
    {"name": "output",   "pre": "generate","data": {"text": "您的订单..."}, ...},
]
```

每轮结束后 `session.nodes.clear()` 清空，下一轮重新构建。

> **不要在 tool 实现中跨轮依赖 nodes 数据。如需跨轮共享，请使用 `data_map`。**

### 4.5 current_query / current_context —— 便捷属性

`src/session/data.py:332-359`

```python
@property
def current_query(self) -> str:
    """从 nodes 倒序找最后一个 input node 的 data.text"""
    ...

@property
def current_context(self) -> str:
    """从 nodes 倒序找最后一个非 input node 的 data.text"""
    ...

@property
def completed_turns(self) -> int:
    """返回 history 列表的长度"""
    return len(self.history)
```

---

## 5. 完整执行流程

### 5.1 DAG 执行（DAGEngine.run）

```
                    ┌──────────────────┐
                    │  session.nodes   │
                    │  ← [] (空)       │
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
  ⑤ session.add_turn(query, answer) → history 追加
                             │
  ⑥ session.trim_or_compress(...) → 仅操作 history
                             │
  ⑦ session.nodes.clear()    → nodes = []
                    ┌────────┴─────────┐
                    │  session.nodes   │
                    │  ← [] (空)       │
                    └──────────────────┘
```

### 5.2 API 层调用时序

```
POST /workflows/{name}/run  {chat_id, query, long_mem_data}
  │
  ├─ 1. 获取 session
  │     chat_id 有值 → store.get(chat_id)  ← 续接
  │     chat_id 空   → store.create(name, mode)  ← 新会话
  │
  ├─ 2. 注入 long_mem_data
  │     session.long_mem_data = req.long_mem_data
  │
  ├─ 3. 执行 DAG
  │     asyncio.to_thread(dag_engine.run, name, query, session)
  │
  ├─ 4. 持久化
  │     store.save(session)
  │
  └─ 5. 返回
       {"chat_id": "chat_xxx", "turn_id": 5, "reply": "..."}
```

### 5.3 异常处理

如果在 `run()` 中抛出异常：
- `add_turn` 不会被调用（状态不更新）
- `nodes` 不会被清除
- session 不会被 `save()`
- API 返回 500，客户端可重试（session 状态不变）

---

## 6. Trim / Compress 算法

### 6.1 触发条件

任一满足即触发：
- `total_turns > max_turns`
- `total_chars > max_chars`

（两者均为 `None` 时不触发）

### 6.2 算法流程

```
trim_or_compress(max_turns, max_chars, keep, compress_max_words, summary_*)

  ① 检查触发
     total_turns > max_turns? OR total_chars > max_chars?
     NO  → return
     YES →
  ② 计算超出量
     excess = total_turns - keep
     excess <= 0 → return (保留全部，无需操作)
  ③ 分离历史
     old_turns = history[:excess]   ← 移除的旧轮
     history   = history[excess:]   ← 保留的最近 keep 轮
  ④ 可选：生成摘要
     配置了 summary LLM?
     YES → _generate_summary(old_turns) → LLM 摘要
     NO  → 跳过
  ⑤ 插入摘要
     summary_text 非空?
     YES → history.insert(0, TurnRecord("[前N轮摘要]", summary_text, ...))
     NO  → 不做任何事（硬截断）

_generate_summary 失败时静默 fallback → 硬截断
```

### 6.3 配置

```yaml
# config/session.yaml
max_turns: 100            # 触发 trim 的轮数阈值
max_chars: 100000         # 触发 trim 的字符数阈值
keep: 20                  # trim 后最少保留的轮数
compress_max_words: 1000  # 摘要最大字数

summary:                  # 可选，不配则硬截断
  base_url: "https://api.deepseek.com/v1"
  api_key: "${DEEPSEEK_API_KEY}"
  model: "deepseek-v4-flash"
  system_prompt: "请将以下对话压缩为{max_words}字以内的摘要..."
```

> `summary` 使用独立的 LLM provider 配置，与 workflow 聊天的 LLM 无关。这允许使用更便宜的模型做摘要。

### 6.4 设计约束

- `keep` 最小值被强制为 1，防止清空所有历史
- 第 1 轮永远不被 trim（`total_turns=1` 时 `excess=0`）
- 摘要轮以 `TurnRecord("[前N轮摘要]", summary_text)` 形式插入 history 头部
- `nodes`、`data_map`、`long_mem_data` 不参与 trim

---

## 7. 存储后端

### 7.1 抽象接口

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

- 进程内 `dict[str, dict]` 存储
- **线程安全**: `threading.Lock` 保护所有读写操作
- **TTL**: `get()` 时惰性检查 + 后台 daemon 线程定期清理
- **LRU**: 创建新 session 时若超过 `max_sessions`，驱逐最旧的
- 额外方法: `touch(chat_id)`, `cleanup_expired()`

```
适用: 开发环境 / 单实例部署
配置:
  memory:
    max_sessions: 2000
  cleanup_interval: 300   # 后台清理间隔（秒），0 则禁用
```

### 7.3 RedisSessionStore

`src/session/redis_store.py`

- 外部 Redis 存储
- `SETEX {prefix}{chat_id} max_age json_data`
- TTL 由 Redis 自动管理
- **惰性导入**: `redis` 包不存在时构造时报错（而非 import 时报错）

```
适用: 生产环境 / 多实例部署
配置:
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

### 7.5 清理机制对比

| 后端 | 清理方式 |
|------|---------|
| Memory | `cleanup_interval` 秒间隔 daemon 线程扫描 + `get()` 惰性检查 |
| Redis | `SETEX` TTL，Redis 自动删除过期 key，`get()` 返回 `None` |

---

## 8. Dict 兼容协议

SessionData 实现了类 dict 访问，所有现有 `session["key"]` 写法无需改动：

```python
session["_workflow"]                  # __getitem__ → getattr
session["return_mode"] = "full"       # __setitem__ → setattr
session.get("bogus", "fallback")      # .get → fallback
"chat_id" in session                  # __contains__ → hasattr
session.setdefault("_workflow", "default")  # 不存在则设
session.keys()                        # 返回 dataclass 字段名集合
```

---

## 9. 序列化

```python
session.to_dict()            # dataclasses.asdict → dict
SessionData.from_dict(data)  # dict → SessionData
```

`from_dict` 兼容旧的 `{role, content}` 格式 history（fallback: `item["content"]` → `input`）。

> `to_dict()` 包含全部字段。由于 nodes 在运行结束后已被清除，序列化存储的 session 不包含 nodes。

---

## 10. API 契约

### 请求

```
POST /workflows/{name}/run
{
    "query": "帮我查订单",
    "chat_id": "chat_xxx",          // 可选；空则新创建
    "long_mem_data": "VIP客户"       // 可选；首次传入后保留
}
```

### 响应

```json
{
    "chat_id": "chat_a1b2c3d4e5f6g7h8i9j0",
    "turn_id": 3,
    "reply": "您的订单信息如下..."
}
```

> 不返回 `data_map`、`long_mem_data`、`history`、`nodes`。这些是服务端内部状态。

### 删除

```
DELETE /sessions/{chat_id}
→ 204 No Content   (成功)
→ 404 Not Found    (不存在)
```

### 工作流隔离

跨 workflow 的 session 不可混用。API 层校验 `_workflow` 匹配，不匹配返回 400。

---

## 11. 开发指南

### 11.1 在 tool 中读取 session

```python
from src.session.data import SessionData

def my_tool(config: dict, session: SessionData) -> dict:
    query = session.current_query           # 当前轮用户输入
    context = session.current_context       # 前一个节点的输出文本

    for turn in session.history:            # 跨轮对话历史
        print(turn.input, turn.output)

    order_id = session.data_map.get("order_id", "")  # 结构化数据
    memory = session.long_mem_data                   # 长期记忆
    chat_id = session.chat_id                        # 会话 ID
    workflow = session._workflow                     # 所属工作流
    turn_num = session.turn_id                       # 当前轮次

    return {"text": "done"}
```

### 11.2 在 tool 中写入 session

```python
def my_extract_tool(config: dict, session: SessionData) -> dict:
    session.data_map["order_id"] = "ORD-123"
    session.data_map["customer_name"] = "张三"

    # 注意：只写入 str 类型
    session.data_map["count"] = str(3)                      # ✅
    session.data_map["items"] = json.dumps(["a", "b"])     # ✅ JSON 字符串
    # session.data_map["items"] = ["a", "b"]                # ❌ 不能存 list

    return {"text": f"extracted {len(session.data_map)} fields"}
```

### 11.3 模板占位符

LLM tool 的 system_prompt 中可用的占位符：

| 占位符 | 展开为 |
|--------|--------|
| `{{query}}` | `session.current_query` |
| `{{context}}` | `session.current_context` |
| `{{data_map}}` | `json.dumps(session.data_map)` |
| `{{data_map:key}}` | `session.data_map["key"]` |
| `{{long_mem}}` | `session.long_mem_data` (原始文本) |
| `{{history}}` | `"用户: ...\n客服: ..."` 格式的多轮文本 |

db_query 的 SQL 模板还支持 `{{query}}`, `{{chat_id}}`, `{{_workflow}}`, `{{data_map}}`。

### 11.4 不能做的事

```python
# ❌ 不要直接修改 history
session.history[0].input = "modified"     # 破坏记录

# ❌ 不要依赖 nodes 做跨轮通信（每轮结束即清除）
prev_data = session.nodes[-1]["data"]     # 上轮数据已不存在

# ✅ 跨轮共享用 data_map
prev_order = session.data_map.get("order_id")

# ❌ 不要随意删除 data_map 中的 key（可能破坏后续逻辑）
del session.data_map["order_id"]

# ❌ 不要在 trim 后依赖 history 长度做绝对索引
assert len(session.history) == 100        # trim 可能触发，长度会变

# ✅ 用 completed_turns 属性
print(f"共 {session.completed_turns} 轮对话")
```

### 11.5 处理多值提取

```python
# extract_regex 的多值模式
emails = re.findall(r"[\w.]+@[\w.]+", query)
if len(emails) == 1:
    session.data_map["email"] = emails[0]           # 单值直接存
else:
    session.data_map["emails"] = json.dumps(emails) # 多值 JSON 数组

# 下游读取
import json
raw = session.data_map.get("emails", "[]")
email_list = json.loads(raw)
```

---

## 12. 测试

### 12.1 测试 tool 函数

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

### 12.2 测试依赖历史对话的 tool

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

### 12.3 测试多轮对话流程

```python
def test_multi_turn():
    session = SessionData()
    session.nodes = [{"name": "input", "data": {"text": "查订单"}}]
    session.add_turn("查订单", "请提供订单号")
    session.nodes.clear()  # 模拟引擎行为

    session.nodes = [{"name": "input", "data": {"text": "ORD-123"}}]
    session.data_map["order_id"] = "ORD-123"
    session.add_turn("ORD-123", "您的订单状态为已发货")

    assert session.turn_id == 2
    assert session.data_map["order_id"] == "ORD-123"
    assert session.history[-1].output == "您的订单状态为已发货"
```

### 12.4 测试 trim/compress

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
    assert len(session.history) == 6  # 1 summary + 5 recent
    assert session.history[0].input == "[前95轮摘要]"
```

### 12.5 测试存储后端

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

## 13. 添加新的存储后端

1. 创建 `src/session/my_store.py`
2. 继承 `SessionStore`，实现 4 个方法
3. 在 `src/session/__init__.py` 的 `create_session_store()` 中添加分支

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

## 14. 配置参考

### 14.1 完整 config/session.yaml

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
  api_key: "${DEEPSEEK_API_KEY}"
  model: "deepseek-v4-flash"
  system_prompt: "请将以下对话压缩为{max_words}字以内的摘要..."
```

### 14.2 工作流级 session 覆盖

```yaml
# config/workflows/my_product/workflow.yaml
session:                   # 可选，override 全局配置
  max_turns: 50            # 仅覆盖此项，其余继承全局
```

### 14.3 代码中读取配置

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

## 15. 调试技巧

### 15.1 查看当前 session 状态

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

### 15.2 检查 session 序列化大小

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

### 15.3 手动触发 trim 测试

```python
session = SessionData()
for i in range(200):
    session.add_turn(f"问题 {i}" * 100, f"答案 {i}" * 100)

session.trim_or_compress(max_turns=50, keep=10)
print(f"trim 后: {len(session.history)} 轮")  # 10 或 11 (含摘要)
```

---

## 16. 常见陷阱

| 陷阱 | 错误写法 | 正确写法 |
|------|---------|---------|
| 获取上轮数据 | `session.nodes[-1]["data"]` (已清除) | `session.history[-1].output` 或 `data_map` |
| data_map 存非 str | `session.data_map["score"] = 95` | `session.data_map["score"] = "95"` |
| 直接修改 history | `session.history[0].input = "x"` | 不要修改 history |
| 依赖绝对轮数 | `assert len(session.history) == 100` | `session.completed_turns` |
| 跨 workflow 混用 | 用 A 的 session 调 B 的 workflow | API 层返回 400 |

---

## 17. 架构图

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
                                    │ history ←──┤ 跨轮记忆
                                    │ data_map ←─┤ 结构数据
                                    │ long_mem   │ 长期记忆
                                    │ nodes (临时)│ 本回合
                                    └────────────┘
```

---

## 18. 文件索引

| 文件 | 职责 |
|------|------|
| `src/session/data.py` | SessionData + TurnRecord 定义，trim/compress 算法 |
| `src/session/base.py` | SessionStore 抽象接口 (ABC) |
| `src/session/memory.py` | MemorySessionStore 实现 |
| `src/session/redis_store.py` | RedisSessionStore 实现 |
| `src/session/__init__.py` | 导出 + create_session_store 工厂函数 |
| `src/config.py` | SessionConfig + SummaryConfig 加载 |
| `config/session.yaml` | 全局 session 配置 |
| `src/engine/dag.py` | DAGEngine.run — session 操作入口 |
| `src/api/routes_chat.py` | Chat API 端点 — session 创建/获取/保存/删除 |
| `src/llm/client.py` | LLMClient — 摘要生成 (延迟导入) |
| `tests/test_session_store.py` | SessionData + Store 测试 |
