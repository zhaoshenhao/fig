import httpx2


class LLMClient:

    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        timeout: float = 30.0,
        provider_type: str = "openai",
    ):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._provider_type = provider_type
        self._client = httpx2.Client(timeout=self._timeout)

    def chat(self, model: str, messages: list[dict], **kwargs) -> dict:
        if self._provider_type == "anthropic":
            return self._chat_anthropic(model, messages, **kwargs)
        return self._chat_openai(model, messages, **kwargs)

    def stream_chat(self, model: str, messages: list[dict], **kwargs):
        """Stream chat completions, yielding text chunks.

        Currently supports OpenAI-compatible providers (OpenAI, DeepSeek, Ollama).
        Anthropic streaming not yet implemented.
        """
        if self._provider_type == "anthropic":
            yield from self._stream_anthropic(model, messages, **kwargs)
        else:
            yield from self._stream_openai(model, messages, **kwargs)

    def _stream_openai(self, model: str, messages: list[dict], **kwargs):
        import json as _json

        kwargs["stream"] = True
        response = self._client.post(
            f"{self._base_url}/chat/completions",
            headers=self._openai_headers(),
            json={"model": model, "messages": messages, **kwargs},
        )
        response.raise_for_status()
        for line in response.iter_lines():
            if not line.startswith("data: "):
                continue
            payload = line[6:]
            if payload == "[DONE]":
                break
            try:
                chunk = _json.loads(payload)
                delta = chunk["choices"][0].get("delta", {})
                content = delta.get("content", "")
                if content:
                    yield content
            except (_json.JSONDecodeError, KeyError, IndexError):
                continue

    def _stream_anthropic(self, model: str, messages: list[dict], **kwargs):
        import json as _json

        system_msg = ""
        user_messages = []
        for m in messages:
            if m["role"] == "system":
                system_msg = m["content"]
            else:
                user_messages.append(m)

        body = {
            "model": model,
            "max_tokens": kwargs.pop("max_tokens", 1024),
            "messages": user_messages,
            "stream": True,
            **kwargs,
        }
        if system_msg:
            body["system"] = system_msg

        response = self._client.post(
            f"{self._base_url}/messages",
            headers=self._anthropic_headers(),
            json=body,
        )
        response.raise_for_status()
        for line in response.iter_lines():
            if not line.startswith("data: "):
                continue
            payload = line[6:]
            try:
                event = _json.loads(payload)
                if event.get("type") == "content_block_delta":
                    delta = event.get("delta", {})
                    text = delta.get("text", "")
                    if text:
                        yield text
                elif event.get("type") == "message_stop":
                    break
            except (_json.JSONDecodeError, KeyError):
                continue

    def _chat_openai(self, model: str, messages: list[dict], **kwargs) -> dict:
        response = self._client.post(
            f"{self._base_url}/chat/completions",
            headers=self._openai_headers(),
            json={"model": model, "messages": messages, **kwargs},
        )
        response.raise_for_status()
        return response.json()

    def _chat_anthropic(self, model: str, messages: list[dict], **kwargs) -> dict:
        system_msg = ""
        user_messages = []
        for m in messages:
            if m["role"] == "system":
                system_msg = m["content"]
            else:
                user_messages.append(m)

        body = {
            "model": model,
            "max_tokens": kwargs.pop("max_tokens", 1024),
            "messages": user_messages,
            **kwargs,
        }
        if system_msg:
            body["system"] = system_msg

        response = self._client.post(
            f"{self._base_url}/messages",
            headers=self._anthropic_headers(),
            json=body,
        )
        response.raise_for_status()
        data = response.json()
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": data["content"][0]["text"],
                    }
                }
            ]
        }

    def embed(self, model: str, inputs: str | list[str]) -> list[list[float]]:
        if isinstance(inputs, str):
            inputs = [inputs]
        response = self._client.post(
            f"{self._base_url}/embeddings",
            headers=self._openai_headers(),
            json={"model": model, "input": inputs},
        )
        response.raise_for_status()
        data = response.json()
        return [item["embedding"] for item in data["data"]]

    def close(self) -> None:
        self._client.close()

    def _openai_headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _anthropic_headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
        }
