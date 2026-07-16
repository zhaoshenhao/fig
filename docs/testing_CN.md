# KF 项目测试文档

[English](testing_EN.md)

## 1. 测试框架

- **pytest** — 主测试框架，`asyncio_mode = "auto"` 自动处理异步测试
- **pytest-mock** — mock 外部依赖（httpx2、Qdrant 客户端）
- **pytest-cov** — 覆盖率报告，最低阈值 95%
- ** pytest-httpx** — 不使用（与 httpx2 不兼容）

## 2. 测试配置（pyproject.toml）

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.coverage.run]
source = ["src"]
omit = [
    "src/gui/*",
    "src/ingestion/*",
    "src/__init__.py",
    "src/*/__init__.py",
    "src/api/main.py",
    "src/cli/build.py",
    "src/cli/manage.py",
]
[tool.coverage.report]
fail_under = 95
exclude_also = ["if TYPE_CHECKING:", "pragma: no cover"]
```

## 3. 运行测试

```bash
# 安装开发依赖
pip install -e .[dev]

# 运行所有测试
pytest

# 详细输出模式
pytest -v

# 运行指定测试文件
pytest tests/test_dag_engine.py

# 运行指定测试类
pytest tests/test_dag_engine.py::TestDAGEngineOneChain

# 运行指定测试函数
pytest tests/test_dag_engine.py::TestDAGEngineOneChain::test_basic_one_chain

# 按关键字匹配运行
pytest -k "dag"

# 带覆盖率运行
pytest --cov=src --cov-report=term --cov-report=html

# 代码风格检查（ruff）
ruff check .
```

## 4. 共享夹具（conftest.py）

### temp_config_dir

创建临时配置目录，包含：

- `llm.yaml` — 测试 LLM provider（mock URL）
- `embed.yaml` — 测试 Embedding provider
- 多产品线工作流：`default`、`if_then_wf`、`switch_wf`、`switch_parallel_wf`、`last_mode_wf`、`metrics_wf`
- 每个产品线对应的节点 YAML 配置
- 返回临时配置目录的 `Path`

```python
@pytest.fixture
def temp_config_dir(tmp_path: Path) -> Path:
    cfg = tmp_path / "config"
    cfg.mkdir(parents=True)
    wp = cfg / "workflows"

    (cfg / "llm.yaml").write_text(yaml.dump({...}), encoding="utf-8")
    (cfg / "embed.yaml").write_text(yaml.dump({...}), encoding="utf-8")

    _make_product(wp, "default", [
        {"name": "retrieve", "next_type": "one", "next": "generate"},
        {"name": "generate", "next_type": "one", "next": ""},
    ])
    # ... 更多工作流
    return cfg
```

### mock_tools

创建 `ToolRegistry` 实例，包含以下 mock 工具：

| 工具名 | 作用 | 返回值 |
|-------|------|--------|
| mock_search | 模拟知识库检索 | `{text, chunks, results}` |
| mock_llm | 模拟 LLM 调用 | `{text, model}` |
| mock_echo | 回显配置中的消息 | `{text: config.message}` |
| mock_switch | 模拟 switch 触发 | `{text: "switch triggered"}` |
| router | **真实** router 工具实现 | 路由分支名称 |

```python
@pytest.fixture
def mock_tools():
    from src.engine.tool import ToolRegistry

    registry = ToolRegistry()

    def mock_search(_config, session):
        return {"text": "search result text", "chunks": ["doc1", "doc2"], "results": []}

    def mock_llm(_config, session):
        return {"text": "generated response", "model": "test-model"}

    def mock_echo(config, _session):
        return {"text": config.get("message", "default")}

    def mock_switch(_config, session):
        return {"text": "switch triggered"}

    from src.engine.tools.router import router as _router

    registry.register("mock_search", mock_search)
    registry.register("mock_llm", mock_llm)
    registry.register("mock_echo", mock_echo)
    registry.register("mock_switch", mock_switch)
    registry.register("router", _router)

    return registry
```

### tmp_path

pytest 内置夹具，提供临时目录用于文件相关测试。

### sys.path 注入

`conftest.py` 自动将项目根目录注入 `sys.path`，各测试文件顶部也有同样的注入代码：

```python
_proj_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_proj_root))
```

## 5. 测试文件目录

| 文件 | 测试数 | 覆盖内容 |
|------|--------|---------|
| `test_api.py` | 52 | API 路由：Chat 端点、会话 CRUD、工作流执行、流式响应、错误处理 |
| `test_auth.py` | 7 | AuthMiddleware：API key 验证、skip_paths、缺少 key、无效 key |
| `test_builder.py` | 31 | 文档构建：文档摄取、分块、向量化、upsert、多格式支持 |
| `test_chunker.py` | 10 | 文本分块：段落合并、重叠、边界情况 |
| `test_cli.py` | 25 | CLI 工具：validate_workflow、build、manage 命令 |
| `test_config.py` | 22 | 配置加载：YAML 解析、环境变量插值、provider 解析、重载 |
| `test_coverage_edge.py` | 78 | 边界情况：空输入、缺失字段、错误路径、边界条件 |
| `test_dag_engine.py` | 20 | DAG 引擎：单链、if-then 路由、switch 并行、指标、错误处理 |
| `test_db.py` | 22 | 数据库连接池：创建、连接、查询执行、池管理 |
| `test_db_integration.py` | 6 | 数据库集成测试（需要实际数据库） |
| `test_embed_service.py` | 20 | kf-embed 服务：健康检查、向量化 API、模型加载 |
| `test_gui.py` | 20 | GUI 组件、agent、聊天界面 |
| `test_llm_client.py` | 17 | LLMClient：chat、stream、embed、错误处理 |
| `test_metrics.py` | 72 | Metrics 存储：写入、查询、聚合、数据保留 |
| `test_qdrant.py` | 10 | QdrantSearch：集合管理、搜索、scroll、混合检索 |
| `test_session_store.py` | 45 | SessionData、MemorySessionStore、RedisSessionStore、TTL、LRU |
| `test_tool_impl.py` | 20 | 工具实现：llm、rag_search、router、db_query |
| `test_tool_impl_extra.py` | 20 | 扩展工具：extract_llm、extract_regex、api_call、web_search、code |
| `test_tools.py` | 12 | ToolRegistry：注册、获取、覆盖、未知工具 |

## 6. Mock 模式

### Mock httpx2.Client（LLM/RAG 测试标准模式）

```python
from unittest.mock import MagicMock

mock_response = MagicMock()
mock_response.status_code = 200
mock_response.json.return_value = {"choices": [{"message": {"content": "test"}}]}

with patch("httpx2.Client", return_value=mock_client):
    result = tool_fn(config, session)
```

### 使用 pytest-mock（mocker fixture）

```python
def test_llm_tool_returns_generated_text(self, mocker, temp_config_dir):
    mock_response = mocker.MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "generated answer", "role": "assistant"}}]
    }
    mock_client = mocker.MagicMock()
    mock_client.post.return_value = mock_response
    mocker.patch("httpx2.Client", return_value=mock_client)
    # ... 测试逻辑
```

### Mock Qdrant（不需要真实 Qdrant 的测试）

```python
mock_qdrant = MagicMock()
mock_qdrant.get_collections.return_value = MagicMock(collections=[])
```

### Mock 会话数据

```python
session = {"nodes": [{"name": "input", "data": {"text": "hello"}}]}
```

## 7. 测试约定

- 测试类使用 **CamelCase**（如 `TestDAGEngineOneChain`）
- 测试方法使用 `test_` 前缀的 **snake_case**
- 每个测试函数只测试 **一个行为**
- 文件相关测试使用 **tmp_path** 临时目录
- Mock 所有外部依赖（httpx2、Qdrant 客户端）
- 模块在**测试函数内部**导入（不在模块层级），以配合 sys.path 操作
- `conftest.py` 注入项目根目录到 `sys.path`

## 8. 各模块测试模式

### 引擎测试模式

```python
class TestDAGEngineOneChain:
    def test_basic_one_chain(self, temp_config_dir, mock_tools):
        from src.config import load_app_config
        from src.engine.dag import DAGEngine

        app_cfg = load_app_config(temp_config_dir)
        engine = DAGEngine(tools=mock_tools, app_config=app_cfg)
        result = engine.run("default", {"query": "hello"})

        assert result is not None
        nodes = result["nodes"]
        assert nodes[0]["name"] == "input"
        assert nodes[-1]["name"] == "output"

    def test_workflow_not_found(self, temp_config_dir, mock_tools):
        from src.config import load_app_config
        from src.engine.dag import DAGEngine

        app_cfg = load_app_config(temp_config_dir)
        engine = DAGEngine(tools=mock_tools, app_config=app_cfg)

        with pytest.raises(KeyError, match="not found"):
            engine.run("bogus", {"query": "x"})
```

### 工具测试模式

```python
class TestLLMTool:
    def test_llm_tool_returns_generated_text(self, mocker, temp_config_dir):
        mock_response = mocker.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "generated answer"}}]
        }
        mock_client = mocker.MagicMock()
        mock_client.post.return_value = mock_response
        mocker.patch("httpx2.Client", return_value=mock_client)

        from src.config import load_app_config
        from src.engine.tools.llm import llm

        app_cfg = load_app_config(temp_config_dir)
        config = {"provider": "test_llm", "system_prompt": "You are helpful."}
        session = {"nodes": [{"name": "input", "data": {"text": "hello"}}]}

        result = llm(config, session)
        assert "text" in result
```

### Router 测试模式

```python
class TestRouter:
    def test_exact_match(self):
        from src.engine.tools.router import router

        config = {
            "router": {
                "match_field": "text",
                "rules": [{"value": "hello", "match": "exact", "branch": "greet"}],
                "default": "fallback",
            }
        }
        session = {"nodes": [{"name": "input", "data": {"text": "  hello  "}}]}
        result = router(config, session)
        assert result == "greet"
```

### 会话测试模式

```python
class TestSessionData:
    def test_chat_id_starts_with_chat_prefix(self):
        from src.session.data import SessionData

        sess = SessionData()
        assert sess.chat_id.startswith("chat_")

    def test_add_turn_creates_turn_record(self):
        from src.session.data import SessionData

        sess = SessionData()
        sess.add_turn("hello", "world")
        assert len(sess.history) == 1
        assert sess.history[0].input == "hello"
```

### Auth 测试模式

```python
class TestAuthMiddleware:
    def test_missing_key_returns_401(self):
        client = _make_app({"api_keys": ["secret"], "skip_paths": []})
        r = client.get("/workflows/default")
        assert r.status_code == 401
        assert "X-API-Key" in r.json()["error"]

    def test_valid_key_passes(self):
        client = _make_app({"api_keys": ["secret", "key2"], "skip_paths": []})
        r = client.get("/workflows/default", headers={"X-API-Key": "secret"})
        assert r.status_code == 200
```

## 9. 覆盖率要求

- **最低覆盖率**：95%
- **排除目录**：`src/gui/`、`src/ingestion/`、所有 `__init__.py`、`main.py`、`build.py`、`manage.py`
- **排除代码标记**：`if TYPE_CHECKING:`、`pragma: no cover`
- **报告格式**：终端输出（`--cov-report=term`）、HTML 报告（`--cov-report=html`）
- HTML 报告生成在 `htmlcov/index.html`，可在浏览器中查看逐行覆盖详情
