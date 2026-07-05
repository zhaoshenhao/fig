from __future__ import annotations

import sys
from pathlib import Path

import pytest

_proj_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_proj_root))


class TestLLMClient:
    def test_chat_openai(self, mocker):
        mock_response = mocker.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {"message": {"content": "Hello!", "role": "assistant"}}
            ]
        }
        mock_response.raise_for_status = mocker.MagicMock()

        mock_client_ctx = mocker.MagicMock()
        mock_client_ctx.post.return_value = mock_response
        mock_client_ctx.__enter__.return_value = mock_client_ctx
        mock_client_ctx.__exit__.return_value = None

        mocker.patch("httpx2.Client").return_value = mock_client_ctx

        from src.llm.client import LLMClient

        client = LLMClient(
            base_url="https://api.example.com/v1",
            api_key="sk-test",
            provider_type="openai",
        )
        result = client.chat(
            "gpt-4",
            [
                {"role": "system", "content": "Be helpful."},
                {"role": "user", "content": "Hi!"},
            ],
        )

        assert result["choices"][0]["message"]["content"] == "Hello!"

    def test_chat_anthropic(self, mocker):
        mock_response = mocker.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "content": [{"type": "text", "text": "Anthropic says hi"}],
        }
        mock_response.raise_for_status = mocker.MagicMock()

        mock_client_ctx = mocker.MagicMock()
        mock_client_ctx.post.return_value = mock_response
        mock_client_ctx.__enter__.return_value = mock_client_ctx
        mock_client_ctx.__exit__.return_value = None

        mocker.patch("httpx2.Client").return_value = mock_client_ctx

        from src.llm.client import LLMClient

        client = LLMClient(
            base_url="https://api.anthropic.com/v1",
            api_key="sk-ant-test",
            provider_type="anthropic",
        )
        result = client.chat(
            "claude-sonnet-4-20250514",
            [
                {"role": "system", "content": "You are Claude."},
                {"role": "user", "content": "Hello"},
            ],
        )

        assert result["choices"][0]["message"]["content"] == "Anthropic says hi"

    def test_chat_anthropic_sends_system_header(self, mocker):

        mock_response = mocker.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "content": [{"type": "text", "text": "ok"}],
        }
        mock_response.raise_for_status = mocker.MagicMock()

        mock_client_ctx = mocker.MagicMock()
        mock_client_ctx.post.return_value = mock_response
        mock_client_ctx.__enter__.return_value = mock_client_ctx
        mock_client_ctx.__exit__.return_value = None

        mocker.patch("httpx2.Client").return_value = mock_client_ctx

        from src.llm.client import LLMClient

        client = LLMClient(
            base_url="https://api.anthropic.com/v1",
            api_key="sk-ant-test",
            provider_type="anthropic",
        )
        client.chat(
            "claude-v1",
            [
                {"role": "system", "content": "system prompt"},
                {"role": "user", "content": "question"},
            ],
        )

        call_args = mock_client_ctx.post.call_args
        assert "/messages" in call_args[0][0]
        body = call_args[1]["json"]
        assert body["system"] == "system prompt"
        assert "x-api-key" in call_args[1]["headers"]

    def test_embed_single_string(self, mocker):
        mock_response = mocker.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"embedding": [0.1, 0.2, 0.3], "index": 0}
            ]
        }
        mock_response.raise_for_status = mocker.MagicMock()

        mock_client_ctx = mocker.MagicMock()
        mock_client_ctx.post.return_value = mock_response
        mock_client_ctx.__enter__.return_value = mock_client_ctx
        mock_client_ctx.__exit__.return_value = None

        mocker.patch("httpx2.Client").return_value = mock_client_ctx

        from src.llm.client import LLMClient

        client = LLMClient(base_url="https://api.example.com/v1", api_key="k")
        vectors = client.embed("text-embed-3-small", "hello world")

        assert len(vectors) == 1
        assert vectors[0] == [0.1, 0.2, 0.3]

    def test_embed_list_of_strings(self, mocker):
        mock_response = mocker.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"embedding": [0.1, 0.2], "index": 0},
                {"embedding": [0.3, 0.4], "index": 1},
            ]
        }
        mock_response.raise_for_status = mocker.MagicMock()

        mock_client_ctx = mocker.MagicMock()
        mock_client_ctx.post.return_value = mock_response
        mock_client_ctx.__enter__.return_value = mock_client_ctx
        mock_client_ctx.__exit__.return_value = None

        mocker.patch("httpx2.Client").return_value = mock_client_ctx

        from src.llm.client import LLMClient

        client = LLMClient(base_url="https://api.example.com/v1")
        vectors = client.embed("model", ["a", "b"])

        assert len(vectors) == 2

    def test_chat_openai_raises_on_http_error(self, mocker):
        mock_response = mocker.MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = Exception("500 Server Error")

        mock_client_ctx = mocker.MagicMock()
        mock_client_ctx.post.return_value = mock_response
        mock_client_ctx.__enter__.return_value = mock_client_ctx
        mock_client_ctx.__exit__.return_value = None

        mocker.patch("httpx2.Client").return_value = mock_client_ctx

        from src.llm.client import LLMClient

        client = LLMClient(base_url="https://api.example.com/v1")
        with pytest.raises(Exception, match="500"):
            client.chat("model", [{"role": "user", "content": "hi"}])

    def test_no_api_key_header_omitted(self, mocker):
        mock_response = mocker.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        mock_response.raise_for_status = mocker.MagicMock()

        mock_client_ctx = mocker.MagicMock()
        mock_client_ctx.post.return_value = mock_response
        mock_client_ctx.__enter__.return_value = mock_client_ctx
        mock_client_ctx.__exit__.return_value = None

        mocker.patch("httpx2.Client").return_value = mock_client_ctx

        from src.llm.client import LLMClient

        client = LLMClient(base_url="https://api.example.com/v1", api_key="")
        client.chat("m", [{"role": "user", "content": "hi"}])

        headers = mock_client_ctx.post.call_args[1]["headers"]
        assert "Authorization" not in headers

    def test_base_url_trailing_slash_stripped(self, mocker):
        mock_response = mocker.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        mock_response.raise_for_status = mocker.MagicMock()

        mock_client_ctx = mocker.MagicMock()
        mock_client_ctx.post.return_value = mock_response
        mock_client_ctx.__enter__.return_value = mock_client_ctx
        mock_client_ctx.__exit__.return_value = None

        mocker.patch("httpx2.Client").return_value = mock_client_ctx

        from src.llm.client import LLMClient

        client = LLMClient(base_url="https://api.example.com/v1/")
        client.chat("m", [{"role": "user", "content": "hi"}])

        url = mock_client_ctx.post.call_args[0][0]
        assert url == "https://api.example.com/v1/chat/completions"
