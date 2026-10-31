"""The configured models: Local and OpenAI from the environment, one client per model."""

from dataclasses import dataclass
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from agent_lab.config import Settings
from agent_lab.llm.base import LLMClient
from agent_lab.llm.openai_compat import OpenAICompatClient

LABELS = {"local": "Local", "openai": "OpenAI"}


class ModelRef(BaseModel):
    """A model is identified by provider and id together: the same id may exist on both."""

    model_config = ConfigDict(frozen=True)

    provider: Literal["local", "openai"]
    model: str = Field(min_length=1, max_length=200)

    def __str__(self) -> str:
        return f"{self.provider}/{self.model}"


@dataclass(frozen=True)
class ModelEntry:
    ref: ModelRef
    external: bool  # not on this machine: prompts and tool results leave it
    unavailable: str | None  # why it cannot be used, e.g. "no API key"
    client: LLMClient


class UnavailableModel(Exception):
    """A model that is not configured or cannot be used; the message names it."""


class Models:
    def __init__(self, entries: list[ModelEntry], default: ModelRef) -> None:
        self.entries = entries
        self.default = default
        try:
            self.client(default)
        except UnavailableModel as exc:
            raise ValueError(str(exc)) from None

    def get(self, ref: ModelRef) -> ModelEntry | None:
        return next((e for e in self.entries if e.ref == ref), None)

    def client(self, ref: ModelRef) -> LLMClient:
        entry = self.get(ref)
        if entry is None:
            raise UnavailableModel(f"model {ref} is not configured")
        if entry.unavailable:
            raise UnavailableModel(f"model {ref} is not available: {entry.unavailable}")
        return entry.client


def parse_ref(text: str) -> ModelRef:
    """`provider/model`, split at the first `/` (model ids may contain `/`)."""
    provider, _, model = text.partition("/")
    if provider not in LABELS or not model:
        raise ValueError(f"{text!r} is not provider/model with provider local or openai")
    return ModelRef.model_validate({"provider": provider, "model": model})


def models_from_settings(s: Settings) -> Models:
    """Raises ValueError naming DEFAULT_MODEL when the default cannot be used."""
    local_http = httpx.AsyncClient(timeout=120.0)
    entries = [
        ModelEntry(
            ref=ModelRef(provider="local", model=model),
            external=False,
            unavailable=None,
            client=OpenAICompatClient(
                base_url=s.llm_base_url, model=model, api_key=s.llm_api_key, http=local_http
            ),
        )
        for model in dict.fromkeys((s.llm_model, *s.llm_models))
    ]
    if s.openai_models:
        openai_http = httpx.AsyncClient(timeout=120.0)
        # shortcut: one thinking-off value per provider; per-model values when mixed models need it
        off = {"reasoning_effort": s.openai_reasoning_off} if s.openai_reasoning_off else {}
        entries += [
            ModelEntry(
                ref=ModelRef(provider="openai", model=model),
                external=True,
                unavailable=None if s.openai_api_key else "no API key",
                client=OpenAICompatClient(
                    base_url=s.openai_base_url,
                    model=model,
                    api_key=s.openai_api_key,
                    http=openai_http,
                    provider="openai",
                    reasoning_off=off,
                    strict_schema=True,
                ),
            )
            for model in dict.fromkeys(s.openai_models)
        ]
    try:
        return Models(entries, parse_ref(s.default_model or f"local/{s.llm_model}"))
    except ValueError as exc:
        raise ValueError(f"DEFAULT_MODEL: {exc}") from None
