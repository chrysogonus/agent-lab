"""The span record every traced step produces (core contract 1)."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class SpanKind(StrEnum):
    LLM = "llm"
    TOOL = "tool"
    ROUTE = "route"
    RETRIEVE = "retrieve"
    RERANK = "rerank"
    MEMORY = "memory"
    STEP = "step"


class Span(BaseModel):
    trace_id: str
    span_id: str
    parent_span_id: str | None
    run_id: str
    agent_id: str
    node_id: str
    config_version: str
    kind: SpanKind
    name: str
    input: Any = None
    output: Any = None
    error: str | None = None
    started_at: float  # epoch seconds
    ended_at: float | None = None  # None while the span is running
    tokens_in: int | None = None
    tokens_out: int | None = None
    model: str | None = None
    # OpenTelemetry GenAI semantic-convention keys, e.g. "gen_ai.request.model".
    attributes: dict[str, Any] = Field(default_factory=dict)
