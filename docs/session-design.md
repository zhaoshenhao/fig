# Session 管理 — 设计规范

## 1. 概述

Session 是多轮对话的核心数据载体。它承载跨轮次记忆（`history`）、节点间结构化数据（`data_map`）、长期记忆（`long_mem_data`）以及当前轮次 DAG 执行日志（`nodes`）。

```
session 生命周期:  create → [run → add_turn → trim → clear_nodes → save] × N → delete
```

## 2. 数据结构

### 2.1 TurnRecord —— 单轮记录

```
src/session/data.py
```

```python
@dataclass
class TurnRecord:
    input: str              # 用户输入
    output: str             # 系统回复
    input_timestamp: float  # 输入时间戳
    output_timestamp: float # 回复时间戳
```

### 2.2 SessionData —— 会话主体

```
src/session/data.py
```

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `chat_id` | `str` | `chat_{uuid4.hex[:20]}` | 唯一标识，仅创建时生成 |
| `turn_id` | `int` | `0` | 轮次计数，每轮 `add_turn` 后 +1 |
| `created_at` | `float` | `time.time()` | 创建时间戳 |
| `last_active_at` | `float` | `time.time()` | 每次 `save()` 更新 |
| `_workflow` | `str` | `""` | 所属 workflow，禁止跨 workflow 混用 |
| `return_mode` | `str` | `"full"` | `"full"` 或 `"last"` |
| `history` | `list[TurnRecord]` | `[]` | 跨轮次对话记忆 |
| `data_map` | `dict[str,str]` | `{}` | 结构化数据（extract 工具写入） |
| `long_mem_data` | `str` | `""` | 长期记忆（client 传入） |
| `nodes` | `list[dict]` | `[]` | 当前轮 DAG 执行日志 |

### 2.3 字段生命周期

```
┌──────────────┬──────────┬────────────┬───────────┬──────────────┐
│ 字段          │ 谁写入   │ 持久化     │ 跨轮次    │ trim/compress │
├──────────────┼──────────┼────────────┼───────────┼──────────────┤
│ chat_id      │ 自生成   │ ✅ 序列化  │ ✅ 不变   │ ❌           │
│ turn_id      │ 引擎     │ ✅ 序列化  │ ✅ 递增   │ ❌           │
│ history      │ 引擎     │ ✅ 序列化  │ ✅ 累积   │ ✅ (仅此字段) │
│ data_map     │ extract  │ ✅ 序列化  │ ✅ 累积   │ ❌           │
│ long_mem_data│ client   │ ✅ 序列化  │ ✅ 不变   │ ❌           │
│ nodes        │ 引擎     │ ❌ 每轮清  │ ❌        │ ❌           │
└──────────────┴──────────┴────────────┴───────────┴──────────────┘
```

**关键约束**：
- `history` 是唯一参与 trim/compress 的字段
- `nodes` 仅保留当前轮次，每轮执行完毕后自动清除（`session.nodes.clear()`）
- `data_map` 永不清除，跨轮累积
- `long_mem_data` client 传入一次即永久保留

## 3. Field 详细说明

### 3.1 history —— 跨轮次记忆

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

### 3.2 data_map —— 节点间结构化共享

`extract_llm` / `extract_regex` 工具从用户输入中提取信息，写入 `data_map`：

```python
# extract_llm 示例
session.data_map["order_id"] = "ORD-20240101"
session.data_map["phone"] = "13800138000"

# extract_regex 示例
session.data_map["phone"] = json.dumps(["13800138000", "13900139000"])
```

其他节点通过以下方式读取：
- **LLM tool**：system_prompt 中使用 `{{data_map}}`，自动展开为 JSON
- **db_query**：SQL 中使用 `{{data_map}}`，自动展开为 JSON
- **代码中**：`session.data_map.get("order_id")`

> data_map 值始终是 `str` 类型。多值用 `json.dumps(list)` 存储。

### 3.3 long_mem_data —— 长期记忆

client 传入一次，不再改变。用于存储用户画像、偏好等跨会话的持久信息：

```bash
# API 调用
curl -X POST /workflows/default/run \
  -d '{"query": "帮我查订单", "chat_id": "chat_xxx", "long_mem_data": "VIP客户, 偏好简洁回复"}'
```

节点中通过 `{{long_mem}}` 占位符使用。

### 3.4 nodes —— 当前轮 DAG 日志

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

**不要在 tool 实现中跨轮依赖 nodes 数据。如需跨轮共享，请使用 `data_map`。**

### 3.5 current_query / current_context —— 便捷属性

```
src/session/data.py:142-154
```

```python
@property
def current_query(self) -> str:
    # 从 nodes 倒序找最后一个 input node 的 data.text
    ...

@property
def current_context(self) -> str:
    # 从 nodes 倒序找最后一个非 input node 的 data.text
    ...
```

## 4. 完整执行流程

### 一次 DAG 执行（DAGEngine.run）

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
  ④ _collect_metrics(session, ...) → SQLite
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

### API 层调用时序

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

## 5. Trim / Compress 算法

### 5.1 触发条件

任一满足即触发：
- `total_turns > max_turns`
- `total_chars > max_chars`

（两者均为 `None` 时不触发）

### 5.2 算法流程

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

### 5.3 配置

```yaml
# config/session.yaml
max_turns: 100            # 触发 trim 的轮数阈值
max_chars: 100000         # 触发 trim 的字符数阈值
keep: 20                  # trim 后最少保留的轮数
compress_max_words: 1000  # 摘要最大字数

summary:                  # 可选，不配则硬截断
  base_url: "https://api.deepseek.com/v1"
  api_key: "${DEEPSEEK_KEY}"
  model: "deepseek-v4-flash"
  system_prompt: "请将以下对话压缩为{max_words}字以内的摘要..."
```

> summary 使用独立的 LLM provider 配置，与 workflow 聊天的 LLM 无关。这允许使用更便宜的模型做摘要。

### 5.4 设计约束

- `keep` 最小值被强制为 1，防止清空所有历史
- 第 1 轮永远不被 trim（`total_turns=1` 时 `excess=0`）
- 摘要轮以 `TurnRecord("[前N轮摘要]", summary_text)` 形式插入 history 头部
- `nodes`、`data_map`、`long_mem_data` 不参与 trim

## 6. 存储后端

### 6.1 抽象接口

```
src/session/base.py  — SessionStore (ABC)
```

```python
class SessionStore(ABC):
    def get(self, chat_id: str) -> SessionData | None: ...
    def create(self, workflow_name: str, return_mode: str) -> SessionData: ...
    def save(self, session: SessionData) -> None: ...
    def delete(self, chat_id: str) -> bool: ...
```

### 6.2 Memory SessionStore

```
src/session/memory.py
```

- 进程内 `dict[str, dict]` 存储
- **线程安全**: `threading.Lock` 保护所有读写操作
- TTL: `get()` 读取时惰性检查 + 后台定期清理
- LRU: 创建新 session 时若超过 `max_sessions`，驱逐最旧的
- 额外方法: `touch(chat_id)`, `cleanup_expired()`
- **后台清理**: FastAPI lifespan 启动时创建 daemon 线程，按 `cleanup_interval` 秒间隔调用 `cleanup_expired()`

```
适用: 开发环境 / 单实例部署
配置:
  memory:
    max_sessions: 2000
  cleanup_interval: 300   # 后台清理间隔（秒），0 则禁用
```

### 6.3 Redis SessionStore

```
src/session/redis_store.py
```

- 外部 Redis 存储
- `SETEX {prefix}{chat_id} max_age json_data`
- TTL 由 Redis 自动管理
- 惰性安装: `redis` 包不存在时构造时报错（而非 import 时报错）

```
适用: 生产环境 / 多实例部署
配置:
  redis:
    url: redis://localhost:6379/0
    prefix: "kf:sess:"
```

### 6.4 Factory

```
src/session/__init__.py  — create_session_store(config)
```

```python
from src.session import create_session_store

store = create_session_store({"store": "memory"})
store = create_session_store({"store": "redis", "redis": {"url": "..."}})
```

对于 `memory` 模式创建 MemorySessionStore；对于 `redis` 模式创建 RedisSessionStore。

## 7. Dict 兼容协议

SessionData 实现了类 dict 访问，所有现有 `session["key"]` 写法无需改动：

```python
session["_workflow"]         # __getitem__ → getattr
session["return_mode"] = "full"  # __setitem__ → setattr
session.get("bogus", "fallback")  # .get → fallback
"chat_id" in session              # __contains__ → hasattr
session.setdefault("_workflow", "default")  # 不存在则设
session.keys()                    # 返回 dataclass 字段名集合
```

## 8. 序列化

```python
session.to_dict()            # dataclasses.asdict → dict
SessionData.from_dict(data)  # dict → SessionData
```

`from_dict` 兼容旧的 `{role, content}` 格式 history（fallback: `item["content"]` → `input`）。

```
to_dict() 包含全部字段，包括 workflow、return_mode、data_map、long_mem_data 等。
  仅 "logs" 节点的数据会在存入时被清除（运行结束后清除 nodes）

  因此序列化存储的 session 不包含 nodes（已清除）。
```

## 9. API 契约

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

## 10. 架构图

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

## 11. 文件索引

| 文件 | 职责 |
|------|------|
| `src/session/data.py` | SessionData + TurnRecord 定义 |
| `src/session/base.py` | SessionStore 抽象接口 |
| `src/session/memory.py` | MemorySessionStore 实现 |
| `src/session/redis_store.py` | RedisSessionStore 实现 |
| `src/session/__init__.py` | 导出 + create_session_store 工厂 |
| `src/config.py` | SessionConfig + SummaryConfig 加载 |
| `config/session.yaml` | 全局 session 配置 |
| `src/engine/dag.py` | DAGEngine.run — session 操作入口 |
| `src/api/main.py` | API 端点 — session 创建/获取/保存/删除 |
| `tests/test_session_store.py` | SessionData + Store 测试 |
