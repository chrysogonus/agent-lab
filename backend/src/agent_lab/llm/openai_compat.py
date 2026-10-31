"""Thin client for OpenAI-compatible `POST /chat/completions` (vLLM, Ollama, OpenAI, ...)."""

from typing import Any, cast

import httpx

from agent_lab.llm.base import ChatResponse, LLMError, Message, ToolCall

# Thinking off on the local server: Ollama reads reasoning_effort; vLLM passes
# chat_template_kwargs to the Qwen template.
LOCAL_REASONING_OFF: dict[str, Any] = {
    "reasoning_effort": "none",
    "chat_template_kwargs": {"enable_thinking": False},
}


class OpenAICompatClient:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str = "",
        http: httpx.AsyncClient | None = None,
        timeout: float = 120.0,
        provider: str = "local",
        reasoning_off: dict[str, Any] | None = None,
        strict_schema: bool = False,
    ) -> None:
        self.provider = provider
        self.model = model
        # Body fields that turn thinking off; each provider has its own (research.md §5).
        self._reasoning_off = LOCAL_REASONING_OFF if reasoning_off is None else reasoning_off
        self._strict_schema = strict_schema  # OpenAI's strict mode needs a stricter schema
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._http = http or httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]],
        *,
        response_format: dict[str, Any] | None = None,
        reasoning: bool | None = None,
    ) -> ChatResponse:
        body: dict[str, Any] = {"model": self.model, "messages": messages, "stream": False}
        if tools:
            body["tools"] = tools
        if response_format is not None:
            body["response_format"] = (
                _strict_format(response_format) if self._strict_schema else response_format
            )
        if reasoning is False:
            body |= self._reasoning_off
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


def _strict_format(response_format: dict[str, Any]) -> dict[str, Any]:
    """The same request with a schema OpenAI's strict mode accepts (research.md §6)."""
    json_schema: dict[str, Any] = response_format.get("json_schema") or {}
    if response_format.get("type") != "json_schema" or "schema" not in json_schema:
        return response_format
    schema = _strict(json_schema["schema"])
    return {**response_format, "json_schema": {**json_schema, "schema": schema}}


def _strict(schema: Any) -> Any:
    """Close every object and require all its properties; drop the string length bounds.

    The answer is still validated against the full pydantic model, bounds included.
    """
    if isinstance(schema, list):
        return [_strict(v) for v in cast(list[Any], schema)]
    if not isinstance(schema, dict):
        return schema
    mapping = cast(dict[str, Any], schema)
    out = {k: _strict(v) for k, v in mapping.items() if k not in ("minLength", "maxLength")}
    if out.get("type") == "object":
        out["additionalProperties"] = False
        out["required"] = list(out.get("properties") or {})
    return out


def _parse(data: dict[str, Any]) -> ChatResponse:
    message: dict[str, Any] = data["choices"][0]["message"]
    usage: dict[str, Any] = data.get("usage") or {}
    calls: list[dict[str, Any]] = message.get("tool_calls") or []
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
            for call in calls
        ],
        tokens_in=usage.get("prompt_tokens"),
        tokens_out=usage.get("completion_tokens"),
        model=data.get("model"),
    )
