# 工具开发指南

本文档说明如何开发自定义工具 (Tool) 并注册到工作流引擎中。

## 1. 工具签名

所有工具遵循统一的函数签名:

```python
def my_tool(config: dict, session: SessionData) -> dict:
    ...
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `config` | dict | 节点 YAML 中的全部配置 (含 tool, llm_provider 等所有字段) |
| `session` | SessionData | 当前会话对象，可读写 data_map, long_mem_data, history, nodes 等 |

**返回值**: `dict` (必须包含 `text` 字段) 或 `str` (自动包装为 `{"text": ..., "branch": ...}`)

## 2. 创建工具文件

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

## 3. 注册工具

### 3.1 在 `__init__.py` 中添加导出

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

### 3.2 在 `dag.py` 的 `_register_builtins` 中注册

```python
# src/engine/dag.py

def _register_builtins(registry: ToolRegistry) -> None:
    from src.engine.tools import (
        ...,
        my_tool,        # 新增
    )
    ...
    registry.register("my_tool", my_tool)
```

### 3.3 在 `api/main.py` 中注册

```python
# src/api/main.py

from src.engine.tools import (
    ...,
    my_tool,            # 新增
)
...
_registry.register("my_tool", my_tool)
```

## 4. 在工作流中使用

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

## 5. Session 对象使用要点

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

## 6. 模板变量替换

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

## 7. 日志与指标

### 结构化日志

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

### Prometheus 指标

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

## 8. 编写测试

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

## 9. 工具开发检查清单

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

## 10. 禁止事项

```
□ 禁止在工具函数中直接使用 os.system / subprocess
□ 禁止在工具中修改 session.nodes (由引擎管理)
□ 禁止在模块顶层导入 httpx2 (使用函数内延迟导入)
□ 禁止返回 None 或不含 "text" 的 dict
```
