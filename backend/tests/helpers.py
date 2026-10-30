"""Shared builders for scripted runs."""

from agent_lab.agents.react import ReActAgent, ReActConfig, config_version
from agent_lab.llm.base import ChatResponse, ToolCall
from agent_lab.llm.fake import FakeLLM
from agent_lab.tools.calculator import CALCULATOR
from agent_lab.tools.weather import WEATHER
from agent_lab.tracing.span import Span
from agent_lab.tracing.tracer import Tracer

TOOLS = [CALCULATOR, WEATHER]


def tool_call(name: str, arguments: str, call_id: str = "c1") -> ChatResponse:
    return ChatResponse(
        tool_calls=[ToolCall(id=call_id, name=name, arguments=arguments)],
        tokens_in=10,
        tokens_out=5,
    )


def answer(text: str) -> ChatResponse:
    return ChatResponse(content=text, tokens_in=20, tokens_out=3)


def make_agent(llm: FakeLLM, max_iterations: int = 6) -> tuple[ReActAgent, list[tuple[str, Span]]]:
    events: list[tuple[str, Span]] = []
    config = ReActConfig(
        model=llm.model, tools=[t.name for t in TOOLS], max_iterations=max_iterations
    )
    tracer = Tracer(
        run_id="run-1",
        agent_id="react",
        config_version=config_version(config),
        sink=lambda event, span: events.append((event, span)),
    )
    return ReActAgent(llm=llm, tools=TOOLS, config=config, tracer=tracer), events


def ended(events: list[tuple[str, Span]]) -> list[Span]:
    """Final state of every span, in start order."""
    final = {s.span_id: s for e, s in events if e == "span_ended"}
    order = [s.span_id for e, s in events if e == "span_started"]
    return [final[i] for i in order]
