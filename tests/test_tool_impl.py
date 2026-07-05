from __future__ import annotations

import sys
from pathlib import Path

_proj_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_proj_root))


class TestToolRegistry:
    def test_register_and_get(self):
        from src.engine.tool import ToolRegistry

        r = ToolRegistry()

        def my_func(config, session):
            return {"text": "done"}

        r.register("test_tool", my_func)
        assert r.get("test_tool") is my_func
        assert r.get("nonexistent") is None

    def test_tools_returns_copy(self):
        from src.engine.tool import ToolRegistry

        r = ToolRegistry()
        r.register("a", lambda c, s: {})

        tools = r.tools()
        assert len(tools) == 1
        tools["b"] = lambda c, s: {}
        assert r.get("b") is None


class TestLLMTool:
    def test_llm_tool_returns_generated_text(self, mocker, temp_config_dir):
        mock_response = mocker.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {"content": "generated answer", "role": "assistant"},
                }
            ]
        }
        mock_response.raise_for_status = mocker.MagicMock()
        mock_client = mocker.MagicMock()
        mock_client.post.return_value = mock_response
        mocker.patch("httpx2.Client", return_value=mock_client)

        mocker.patch.dict("src.engine.tools.llm_tool._llm_clients", clear=True)

        from src.config import load_app_config
        from src.engine.tools.llm_tool import llm_tool
        from src.session.data import SessionData

        load_app_config(temp_config_dir)

        config = {
            "llm_provider": "test_llm",
            "system_prompt": "You are a {{query}}. Context: {{context}}",
        }
        session = SessionData()
        session["nodes"] = [
            {"name": "input", "data": {"text": "test query"}},
            {"name": "retrieve", "data": {"text": "some context"}},
        ]

        result = llm_tool(config, session)
        assert result["text"] == "generated answer"
        assert result["model"] == "test-model"

    def test_llm_tool_no_context(self, mocker, temp_config_dir):
        mock_response = mocker.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {"message": {"content": "no context answer", "role": "assistant"}},
            ]
        }
        mock_response.raise_for_status = mocker.MagicMock()
        mock_client = mocker.MagicMock()
        mock_client.post.return_value = mock_response
        mocker.patch("httpx2.Client", return_value=mock_client)

        mocker.patch.dict("src.engine.tools.llm_tool._llm_clients", clear=True)

        from src.config import load_app_config
        from src.engine.tools.llm_tool import llm_tool
        from src.session.data import SessionData

        load_app_config(temp_config_dir)

        config = {"llm_provider": "test_llm", "system_prompt": "Help {{query}}"}
        session = SessionData()
        session["nodes"] = [
            {"name": "input", "data": {"text": "query only"}},
        ]

        result = llm_tool(config, session)
        assert result["text"] == "no context answer"

    def test_llm_tool_empty_session_no_query(self, mocker, temp_config_dir):
        mock_response = mocker.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "default", "role": "assistant"}}],
        }
        mock_response.raise_for_status = mocker.MagicMock()
        mock_client = mocker.MagicMock()
        mock_client.post.return_value = mock_response
        mocker.patch("httpx2.Client", return_value=mock_client)

        mocker.patch.dict("src.engine.tools.llm_tool._llm_clients", clear=True)

        from src.config import load_app_config
        from src.engine.tools.llm_tool import llm_tool
        from src.session.data import SessionData

        load_app_config(temp_config_dir)

        config = {"llm_provider": "test_llm", "system_prompt": "prompt"}
        session = SessionData()

        result = llm_tool(config, session)
        assert "text" in result

    def test_llm_tool_stream_callback(self, mocker, temp_config_dir):
        sse_lines = [
            'data: {"choices":[{"delta":{"content":"Hello"}}]}',
            'data: {"choices":[{"delta":{"content":" Stream"}}]}',
            "data: [DONE]",
        ]

        mock_response = mocker.MagicMock()
        mock_response.status_code = 200
        mock_response.iter_lines.return_value = sse_lines
        mock_response.raise_for_status = mocker.MagicMock()

        mock_client = mocker.MagicMock()
        mock_client.post.return_value = mock_response
        mocker.patch("httpx2.Client", return_value=mock_client)

        mocker.patch.dict("src.engine.tools.llm_tool._llm_clients", clear=True)

        from src.config import load_app_config
        from src.engine.tools.llm_tool import llm_tool
        from src.session.data import SessionData

        load_app_config(temp_config_dir)

        config = {"llm_provider": "test_llm", "system_prompt": "prompt"}
        session = SessionData()
        session.nodes = [{"name": "input", "data": {"text": "hi"}}]

        tokens: list[str] = []

        def _recv(token):
            tokens.append(token)

        session.stream_callback = _recv

        result = llm_tool(config, session)
        assert tokens == ["Hello", " Stream"]
        assert result["text"] == "Hello Stream"


class TestLLMToolHistory:
    def test_injects_history_messages(self, mocker, temp_config_dir):
        mock_response = mocker.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "answer", "role": "assistant"}}],
        }
        mock_response.raise_for_status = mocker.MagicMock()
        mock_client = mocker.MagicMock()
        mock_client.post.return_value = mock_response
        mocker.patch("httpx2.Client", return_value=mock_client)

        mocker.patch.dict("src.engine.tools.llm_tool._llm_clients", clear=True)

        from src.config import load_app_config
        from src.engine.tools.llm_tool import llm_tool
        from src.session.data import SessionData

        load_app_config(temp_config_dir)

        config = {"llm_provider": "test_llm", "system_prompt": "help"}
        session = SessionData()
        session["nodes"] = [{"name": "input", "data": {"text": "turn 3 query"}}]
        session.add_turn("turn 1", "answer 1")
        session.add_turn("turn 2", "answer 2")

        llm_tool(config, session)

        call_args = mock_client.post.call_args
        messages = call_args[1]["json"]["messages"]
        assert messages[0]["role"] == "system"
        assert messages[1] == {"role": "user", "content": "turn 1"}
        assert messages[2] == {"role": "assistant", "content": "answer 1"}
        assert messages[3] == {"role": "user", "content": "turn 2"}
        assert messages[4] == {"role": "assistant", "content": "answer 2"}
        assert messages[5] == {"role": "user", "content": "turn 3 query"}

    def test_empty_history_handled(self, mocker, temp_config_dir):
        mock_response = mocker.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "answer", "role": "assistant"}}],
        }
        mock_response.raise_for_status = mocker.MagicMock()
        mock_client = mocker.MagicMock()
        mock_client.post.return_value = mock_response
        mocker.patch("httpx2.Client", return_value=mock_client)

        mocker.patch.dict("src.engine.tools.llm_tool._llm_clients", clear=True)

        from src.config import load_app_config
        from src.engine.tools.llm_tool import llm_tool
        from src.session.data import SessionData

        load_app_config(temp_config_dir)

        config = {"llm_provider": "test_llm", "system_prompt": "h"}
        session = SessionData()
        session["nodes"] = [{"name": "input", "data": {"text": "query"}}]

        result = llm_tool(config, session)
        assert result["text"] == "answer"

    def test_no_history_key_handled(self, mocker, temp_config_dir):
        mock_response = mocker.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "answer", "role": "assistant"}}],
        }
        mock_response.raise_for_status = mocker.MagicMock()
        mock_client = mocker.MagicMock()
        mock_client.post.return_value = mock_response
        mocker.patch("httpx2.Client", return_value=mock_client)

        mocker.patch.dict("src.engine.tools.llm_tool._llm_clients", clear=True)

        from src.config import load_app_config
        from src.engine.tools.llm_tool import llm_tool
        from src.session.data import SessionData

        load_app_config(temp_config_dir)

        config = {"llm_provider": "test_llm", "system_prompt": "h"}
        session = SessionData()
        session["nodes"] = [{"name": "input", "data": {"text": "query"}}]

        result = llm_tool(config, session)
        assert result["text"] == "answer"


class TestRAGSearch:
    def test_rag_search_returns_context(self, mocker, temp_config_dir):
        mocker.patch("src.engine.tools.rag_search._embed_client", None)
        mocker.patch("src.engine.tools.rag_search._embed_provider_key", None)
        mocker.patch("src.engine.tools.rag_search._qdrant", None)

        mock_embed_response = mocker.MagicMock()
        mock_embed_response.status_code = 200
        mock_embed_response.json.return_value = {
            "data": [{"embedding": [0.1] * 768, "index": 0}]
        }
        mock_embed_response.raise_for_status = mocker.MagicMock()
        mock_client = mocker.MagicMock()
        mock_client.post.return_value = mock_embed_response
        mocker.patch("httpx2.Client", return_value=mock_client)

        mock_qdrant = mocker.patch("src.rag.qdrant.QdrantClient")
        fake_point = mocker.MagicMock()
        fake_point.id = 1
        fake_point.score = 0.9
        fake_point.payload = {"text": "chunk one"}
        fake_point2 = mocker.MagicMock()
        fake_point2.id = 2
        fake_point2.score = 0.8
        fake_point2.payload = {"text": "chunk two"}
        mock_qdrant.return_value.query_points.return_value.points = [
            fake_point, fake_point2
        ]

        from src.config import load_app_config
        from src.engine.tools.rag_search import rag_search
        from src.session.data import SessionData

        load_app_config(temp_config_dir)

        config = {
            "embed_provider": "test_embed",
            "collection": "test_col",
            "limit": 5,
        }
        session = SessionData(_workflow="nonexistent_wf")
        session["nodes"] = [{"name": "input", "data": {"text": "search query"}}]

        result = rag_search(config, session)
        assert "text" in result
        assert "chunks" in result
        assert "results" in result
        assert len(result["chunks"]) == 2

    def test_rag_search_with_list_collections(self, mocker, temp_config_dir):
        mocker.patch("src.engine.tools.rag_search._embed_client", None)
        mocker.patch("src.engine.tools.rag_search._embed_provider_key", None)
        mocker.patch("src.engine.tools.rag_search._qdrant", None)

        mock_embed_response = mocker.MagicMock()
        mock_embed_response.status_code = 200
        mock_embed_response.json.return_value = {
            "data": [{"embedding": [0.1] * 768, "index": 0}]
        }
        mock_embed_response.raise_for_status = mocker.MagicMock()
        mock_client = mocker.MagicMock()
        mock_client.post.return_value = mock_embed_response
        mocker.patch("httpx2.Client", return_value=mock_client)

        mock_qdrant = mocker.patch("src.rag.qdrant.QdrantClient")
        fake_point = mocker.MagicMock()
        fake_point.id = 1
        fake_point.score = 0.9
        fake_point.payload = {"text": "col a result"}
        mock_qdrant.return_value.query_points.return_value.points = [fake_point]

        from src.config import load_app_config
        from src.engine.tools.rag_search import rag_search
        from src.session.data import SessionData

        load_app_config(temp_config_dir)

        config = {
            "embed_provider": "test_embed",
            "collection": ["col_a", "col_b"],
            "limit": 5,
        }
        session = SessionData()
        session["nodes"] = [{"name": "input", "data": {"text": "multi kb search"}}]

        result = rag_search(config, session)
        assert "text" in result
        assert len(result["chunks"]) >= 1


class TestExtractLLM:
    def test_extracts_fields_from_llm(self, mocker, temp_config_dir):
        mock_response = mocker.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '{"order_id":"ORD-123","name":"Alice"}',
                                      "role": "assistant"}}],
        }
        mock_response.raise_for_status = mocker.MagicMock()
        mock_client = mocker.MagicMock()
        mock_client.post.return_value = mock_response
        mocker.patch("httpx2.Client", return_value=mock_client)

        mocker.patch.dict("src.engine.tools.llm_tool._llm_clients", clear=True)

        from src.config import load_app_config
        from src.engine.tools.extract_llm import extract_llm
        from src.session.data import SessionData

        load_app_config(temp_config_dir)

        config = {
            "llm_provider": "test_llm",
            "extract": [
                {"key": "order_id", "description": "订单号"},
                {"key": "name", "description": "姓名"},
            ],
        }
        session = SessionData()
        session.nodes = [{"name": "input", "data": {"text": "我的订单号是ORD-123"}}]

        result = extract_llm(config, session)
        assert result["extracted"] == ["order_id", "name"]
        assert session.data_map["order_id"] == "ORD-123"

    def test_skips_non_json_response(self, mocker, temp_config_dir):
        mock_response = mocker.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "not json at all",
                                      "role": "assistant"}}],
        }
        mock_response.raise_for_status = mocker.MagicMock()
        mock_client = mocker.MagicMock()
        mock_client.post.return_value = mock_response
        mocker.patch("httpx2.Client", return_value=mock_client)

        mocker.patch.dict("src.engine.tools.llm_tool._llm_clients", clear=True)

        from src.config import load_app_config
        from src.engine.tools.extract_llm import extract_llm
        from src.session.data import SessionData

        load_app_config(temp_config_dir)

        config = {"llm_provider": "test_llm", "extract": [{"key": "x"}]}
        session = SessionData()
        session.nodes = [{"name": "input", "data": {"text": "hi"}}]

        result = extract_llm(config, session)
        assert result["extracted"] == []

    def test_handles_markdown_code_block(self, mocker, temp_config_dir):
        mock_response = mocker.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '```json\n{"k":"v"}\n```',
                                      "role": "assistant"}}],
        }
        mock_response.raise_for_status = mocker.MagicMock()
        mock_client = mocker.MagicMock()
        mock_client.post.return_value = mock_response
        mocker.patch("httpx2.Client", return_value=mock_client)

        mocker.patch.dict("src.engine.tools.llm_tool._llm_clients", clear=True)

        from src.config import load_app_config
        from src.engine.tools.extract_llm import extract_llm
        from src.session.data import SessionData

        load_app_config(temp_config_dir)

        config = {"llm_provider": "test_llm", "extract": [{"key": "k"}]}
        session = SessionData()
        session.nodes = [{"name": "input", "data": {"text": "x"}}]

        result = extract_llm(config, session)
        assert result["extracted"] == ["k"]
        assert session.data_map["k"] == "v"

    def test_no_extract_fields(self):
        from src.engine.tools.extract_llm import extract_llm
        from src.session.data import SessionData

        config = {"extract": []}
        session = SessionData()
        result = extract_llm(config, session)
        assert result["extracted"] == []


class TestExtractRegex:
    def test_extracts_single_match(self):
        from src.engine.tools.extract_regex import extract_regex
        from src.session.data import SessionData

        config = {"extract": [
            {"key": "order_id", "pattern": r"ORD-\d{8}"},
        ]}
        session = SessionData()
        session.nodes = [{"name": "input", "data": {"text": "我的订单 ORD-20240101 请查收"}}]

        result = extract_regex(config, session)
        assert result["extracted"] == ["order_id"]
        assert session.data_map["order_id"] == "ORD-20240101"

    def test_extracts_multiple_matches(self):
        from src.engine.tools.extract_regex import extract_regex
        from src.session.data import SessionData

        config = {"extract": [
            {"key": "phone", "pattern": r"1\d{10}"},
        ]}
        session = SessionData()
        session.nodes = [{"name": "input", "data": {"text": "13800138000 和 13900139000"}}]

        result = extract_regex(config, session)
        assert result["extracted"] == ["phone"]
        assert "13800138000" in session.data_map["phone"]
        assert "13900139000" in session.data_map["phone"]

    def test_no_match_skips(self):
        from src.engine.tools.extract_regex import extract_regex
        from src.session.data import SessionData

        config = {"extract": [{"key": "email", "pattern": r"[\w.]+@[\w.]+"}]}
        session = SessionData()
        session.nodes = [{"name": "input", "data": {"text": "no email here"}}]

        result = extract_regex(config, session)
        assert result["extracted"] == []

    def test_no_extract_fields(self):
        from src.engine.tools.extract_regex import extract_regex
        from src.session.data import SessionData

        result = extract_regex({"extract": []}, SessionData())
        assert result["extracted"] == []

    def test_invalid_regex_skipped(self):
        from src.engine.tools.extract_regex import extract_regex
        from src.session.data import SessionData

        config = {"extract": [
            {"key": "bad", "pattern": r"[[["},
        ]}
        session = SessionData()
        session.nodes = [{"name": "input", "data": {"text": "text"}}]

        result = extract_regex(config, session)
        assert result["extracted"] == []

