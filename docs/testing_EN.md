# KF Project Test Documentation

[中文](testing_CN.md)

## 1. Test Framework

- **pytest** — primary test framework, `asyncio_mode = "auto"` for automatic async handling
- **pytest-mock** — mocking external dependencies (httpx2, Qdrant client)
- **pytest-cov** — coverage reporting, minimum threshold 95%
- ** pytest-httpx** — not used (incompatible with httpx2)

## 2. Test Configuration (pyproject.toml)

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

## 3. Running Tests

```bash
# Install dev dependencies
pip install -e .[dev]

# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_dag_engine.py

# Run specific test class
pytest tests/test_dag_engine.py::TestDAGEngineOneChain

# Run specific test function
pytest tests/test_dag_engine.py::TestDAGEngineOneChain::test_basic_one_chain

# Run tests matching keyword
pytest -k "dag"

# Run with coverage
pytest --cov=src --cov-report=term --cov-report=html

# Lint check (ruff)
ruff check .
```

## 4. Shared Fixtures (conftest.py)

### temp_config_dir

Creates a temporary config directory containing:

- `llm.yaml` — test LLM provider with mock URLs
- `embed.yaml` — test embedding provider
- Multiple workflow products: `default`, `if_then_wf`, `switch_wf`, `switch_parallel_wf`, `last_mode_wf`, `metrics_wf`
- Per-product node YAML configs
- Returns `Path` to the temporary config directory

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
    # ... more workflows
    return cfg
```

### mock_tools

Creates a `ToolRegistry` instance with the following mock tools:

| Tool | Purpose | Returns |
|------|---------|---------|
| mock_search | Mock knowledge base search | `{text, chunks, results}` |
| mock_llm | Mock LLM call | `{text, model}` |
| mock_echo | Echo config message | `{text: config.message}` |
| mock_switch | Mock switch trigger | `{text: "switch triggered"}` |
| router | **Real** router implementation | Route branch name |

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

Built-in pytest fixture providing a temporary directory for file-based tests.

### sys.path Injection

`conftest.py` automatically injects the project root into `sys.path`. Individual test files also include the same injection at the top:

```python
_proj_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_proj_root))
```

## 5. Test File Catalog

| File | Tests | What It Covers |
|------|-------|---------------|
| `test_api.py` | 52 | API routes: chat endpoints, session CRUD, workflow execution, streaming, error handling |
| `test_auth.py` | 7 | AuthMiddleware: API key validation, skip paths, missing/invalid keys |
| `test_builder.py` | 31 | Document builder: ingestion, chunking, embedding, upsert, multi-format support |
| `test_chunker.py` | 10 | Text chunking: paragraph merging, overlap, edge cases |
| `test_cli.py` | 25 | CLI tools: validate_workflow, build, manage commands |
| `test_config.py` | 22 | Config loading: YAML parsing, env interpolation, provider resolution, reload |
| `test_coverage_edge.py` | 78 | Edge cases: empty inputs, missing fields, error paths, boundary conditions |
| `test_dag_engine.py` | 20 | DAG engine: one chain, if-then routing, switch parallel, metrics, error handling |
| `test_db.py` | 22 | DB pool: creation, connection, query execution, pool management |
| `test_db_integration.py` | 6 | Integration tests for database operations (requires real database) |
| `test_embed_service.py` | 20 | kf-embed service: health, embeddings API, model loading |
| `test_gui.py` | 20 | GUI components, agent, chat interface |
| `test_llm_client.py` | 17 | LLMClient: chat, stream, embed, error handling |
| `test_metrics.py` | 72 | Metrics store: insert, query, aggregation, retention |
| `test_qdrant.py` | 10 | QdrantSearch: collection management, search, scroll, hybrid |
| `test_session_store.py` | 45 | SessionData, MemorySessionStore, RedisSessionStore, TTL, LRU |
| `test_tool_impl.py` | 20 | Tool implementations: llm, rag_search, router, db_query |
| `test_tool_impl_extra.py` | 20 | Extended tools: extract_llm, extract_regex, api_call, web_search, code |
| `test_tools.py` | 12 | ToolRegistry: register, get, override, unknown tool |

## 6. Mocking Patterns

### Mock httpx2.Client (standard pattern for LLM/RAG tests)

```python
from unittest.mock import MagicMock

mock_response = MagicMock()
mock_response.status_code = 200
mock_response.json.return_value = {"choices": [{"message": {"content": "test"}}]}

with patch("httpx2.Client", return_value=mock_client):
    result = tool_fn(config, session)
```

### Using pytest-mock (mocker fixture)

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
    # ... test logic
```

### Mock Qdrant (for tests not needing real Qdrant)

```python
mock_qdrant = MagicMock()
mock_qdrant.get_collections.return_value = MagicMock(collections=[])
```

### Mock Session Data

```python
session = {"nodes": [{"name": "input", "data": {"text": "hello"}}]}
```

## 7. Testing Conventions

- Test classes use **CamelCase** (e.g., `TestDAGEngineOneChain`)
- Test methods use `test_` prefix with **snake_case**
- Each test function tests **ONE behavior**
- Use **tmp_path** temporary directories for file-based tests
- Mock all external dependencies (httpx2, Qdrant client)
- Import modules **inside test functions** (not at module level) to work with sys.path manipulation
- `conftest.py` injects project root into `sys.path`

## 8. Test Patterns by Module

### Engine Test Pattern

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

### Tool Test Pattern

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

### Router Test Pattern

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

### Session Test Pattern

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

### Auth Test Pattern

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

## 9. Coverage Requirements

- **Minimum coverage**: 95%
- **Excluded from coverage**: `src/gui/`, `src/ingestion/`, all `__init__.py` files, `main.py`, `build.py`, `manage.py`
- **Exclude markers**: `if TYPE_CHECKING:`, `pragma: no cover`
- **Report formats**: terminal (`--cov-report=term`), HTML (`--cov-report=html`)
- HTML report generated at `htmlcov/index.html`, viewable in browser for line-by-line coverage details
