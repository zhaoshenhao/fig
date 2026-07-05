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
