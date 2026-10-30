import pytest
from helpers import answer, assert_trace_valid, ended, make_tracer, taken_edges

from agent_lab.agents.steps import Outcome
from agent_lab.llm.base import ChatResponse, Message
from agent_lab.llm.fake import FakeLLM, ScriptItem
from agent_lab.tracing.span import Span
from agent_lab.workflows.parallel import AGENT_ID, Config, ParallelWorkflow, build_graph

ASPECTS = list(Config(model="m").aspects)


def aspect_of(messages: list[Message]) -> str:
    return next(a for a in ASPECTS if f"for {a} only" in messages[0]["content"])


def review(messages: list[Message]) -> ChatResponse:
    """Branches run concurrently, so each answers for the aspect it was asked about."""
    return answer(f"{aspect_of(messages)} review")


async def run(script: list[ScriptItem], delay: float = 0) -> tuple[Outcome, list[Span], FakeLLM]:
    llm = FakeLLM(script, delay=delay)
    tracer, events = make_tracer(AGENT_ID)
    workflow = ParallelWorkflow(llm=llm, config=Config(model=llm.model), tracer=tracer)
    outcome = await workflow.run("Best app ever!!!")
    return outcome, ended(events), llm


@pytest.mark.anyio
async def test_happy_path() -> None:
    outcome, spans, llm = await run([review, review, review, answer("merged")])

    assert (outcome.status, outcome.answer) == ("completed", "merged")
    assert_trace_valid(build_graph(Config(model="m")), spans)
    assert all(r["reasoning"] is False for r in llm.requests)
    merge_input = llm.calls[3][-1]["content"]
    assert all(f"{a} review" in merge_input for a in ASPECTS)
    assert {s.node_id for s in spans} == {"start", *ASPECTS, "merge", "end"}
    assert ("merge", "end") in taken_edges(spans)


@pytest.mark.anyio
async def test_branches_overlap_and_join() -> None:
    outcome, spans, _ = await run([review, review, review, answer("merged")], delay=0.05)

    assert outcome.status == "completed"
    branches = [s for s in spans if s.node_id in ASPECTS]
    assert len(branches) == 3
    sections = next(s for s in spans if s.name == "sections")
    assert {b.parent_span_id for b in branches} == {sections.span_id}
    # Every branch starts before any ends: they ran at the same time.
    assert max(b.started_at for b in branches) < min(b.ended_at or 0 for b in branches)
    root = spans[0]
    branch_total = sum((b.ended_at or 0) - b.started_at for b in branches)
    assert (root.ended_at or 0) - root.started_at < branch_total  # SC-003
    merge = next(s for s in spans if s.node_id == "merge")
    assert set(merge.attributes["lab.came_from"]) == set(ASPECTS)
    assert taken_edges(spans) == {
        *(("start", a) for a in ASPECTS),
        *((a, "merge") for a in ASPECTS),
        ("merge", "end"),
    }
