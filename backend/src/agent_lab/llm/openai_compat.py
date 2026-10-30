"""Thin client for OpenAI-compatible `POST /chat/completions` (Ollama, OpenAI, vLLM, ...)."""

from typing import Any

import httpx

from agent_lab.llm.base import ChatResponse, LLMError, Message, ToolCall


class OpenAICompatClient:
    provider = "openai_compat"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str = "",
        http: httpx.AsyncClient | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.model = model
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._http = http or httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def chat(self, messages: list[Message], tools: list[dict[str, Any]]) -> ChatResponse:
        body: dict[str, Any] = {"model": self.model, "messages": messages, "stream": False}
        if tools:
            body["tools"] = tools
        try:
            response = await self._http.post(self._url, json=body, headers=self._headers)
        except httpx.HTTPError as exc:
            raise LLMError(f"request failed: {exc!r}") from exc
        if response.status_code != 200:
            raise LLMError(f"HTTP {response.status_code}: {response.text[:500]}")
        try:
            return _parse(response.json())
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"unexpected response shape: {exc!r}") from exc


def _parse(data: dict[str, Any]) -> ChatResponse:
    message = data["choices"][0]["message"]
    usage = data.get("usage") or {}
    return ChatResponse(
        content=message.get("content"),
        # Ollama names it "reasoning"; vLLM and DeepSeek use "reasoning_content".
        reasoning=message.get("reasoning") or message.get("reasoning_content"),
        tool_calls=[
            ToolCall(
                id=call["id"],
                name=call["function"]["name"],
                arguments=call["function"].get("arguments") or "{}",
            )
            for call in message.get("tool_calls") or []
        ],
        tokens_in=usage.get("prompt_tokens"),
        tokens_out=usage.get("completion_tokens"),
        model=data.get("model"),
    )
