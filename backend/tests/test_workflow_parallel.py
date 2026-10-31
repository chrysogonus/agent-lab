import pytest
from helpers import answer, assert_trace_valid, ended, make_tracer, taken_edges

from agent_lab.agents.steps import Outcome
from agent_lab.llm.base import ChatResponse, LLMError, Message
from agent_lab.llm.fake import FakeLLM, ScriptItem
from agent_lab.tracing.span import Span
from agent_lab.workflows.parallel import AGENT_ID, Config, ParallelWorkflow, build_graph

ASPECTS = list(Config(model="m").aspects)


def aspect_of(messages: list[Message]) -> str:
    return next(a for a in ASPECTS if f"for {a} only" in messages[0]["content"])


def review(messages: list[Message]) -> ChatResponse:
    """Branches run concurrently, so each answers for the aspect it was asked about."""
    return answer(f"{aspect_of(messages)} review")


async def run(
    script: list[ScriptItem], delay: float = 0, config: Config | None = None
) -> tuple[Outcome, list[Span], FakeLLM]:
    llm = FakeLLM(script, delay=delay)
    tracer, events = make_tracer(AGENT_ID)
    config = config or Config(model=llm.model)
    workflow = ParallelWorkflow(llm=llm, config=config, tracer=tracer)
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


def tone_fails(messages: list[Message]) -> ChatResponse | Exception:
    return LLMError("HTTP 500: boom") if aspect_of(messages) == "tone" else review(messages)


@pytest.mark.anyio
async def test_one_branch_fails() -> None:
    outcome, spans, llm = await run([tone_fails, tone_fails, tone_fails, answer("merged")])

    assert (outcome.status, outcome.answer) == ("completed", "merged")
    tone = next(s for s in spans if s.node_id == "tone")
    assert tone.error == "LLMError: HTTP 500: boom"
    merge = next(s for s in spans if s.node_id == "merge")
    assert set(merge.attributes["lab.came_from"]) == {"clarity", "claims"}
    merge_input = llm.calls[3][-1]["content"]
    assert "clarity review" in merge_input and "tone review" not in merge_input
    # The failure stays on the branch; the run around it is fine.
    assert spans[0].error is None
    assert_trace_valid(build_graph(Config(model="m")), spans)


@pytest.mark.anyio
async def test_all_branches_fail() -> None:
    outcome, spans, _ = await run([LLMError("down")] * 3)

    assert (outcome.status, outcome.answer) == ("error", None)
    assert not any(s.node_id == "merge" for s in spans)
    end = spans[-1]
    assert end.error == "all 3 reviews failed"
    assert set(end.attributes["lab.came_from"]) == set(ASPECTS)
    assert_trace_valid(build_graph(Config(model="m")), spans)


def echo_aspect(messages: list[Message]) -> ChatResponse:
    """Answers with the aspect name from a custom review prompt `Review for <name>.`."""
    return answer((messages[0]["content"] or "").removeprefix("Review for ").rstrip("."))


def aspects_config(*names: str) -> Config:
    return Config(
        model="m",
        aspects={n: f"focus on {n}" for n in names},
        review_prompt="Review for {aspect}.",
    )


@pytest.mark.anyio
@pytest.mark.parametrize("names", [("solo",), ("a", "b", "c", "d", "e", "f")])
async def test_one_and_six_aspects(names: tuple[str, ...]) -> None:
    config = aspects_config(*names)
    outcome, spans, llm = await run([*[echo_aspect] * len(names), answer("merged")], 0.02, config)

    assert (outcome.status, outcome.answer) == ("completed", "merged")
    graph = build_graph(config)
    assert graph.node_ids() == {"start", *names, "merge", "end"}
    reviews = [s for s in spans if s.node_id in names]
    assert sorted(s.node_id for s in reviews) == sorted(names)
    assert max(s.started_at for s in reviews) < min(s.ended_at or 0 for s in reviews)
    merge = next(s for s in spans if s.node_id == "merge")
    assert sorted(merge.attributes["lab.came_from"]) == sorted(names)
    assert all(f"{n} review:\n{n}" in (llm.calls[-1][-1]["content"] or "") for n in names)
    assert_trace_valid(graph, spans)


@pytest.mark.anyio
async def test_replaced_aspect() -> None:
    base = Config(model="m")
    aspects = {k: v for k, v in base.aspects.items() if k != "tone"} | {"length": "Is it short?"}
    config = base.model_copy(update={"aspects": aspects})
    outcome, spans, _ = await run(
        [review_any, review_any, review_any, answer("merged")], config=config
    )

    assert outcome.status == "completed"
    assert {s.node_id for s in spans} == {"start", "clarity", "claims", "length", "merge", "end"}
    assert_trace_valid(build_graph(config), spans)


def review_any(messages: list[Message]) -> ChatResponse:
    return answer("a review")


@pytest.mark.anyio
async def test_review_prompt_with_braces() -> None:
    config = Config(model="m", review_prompt='Review {aspect}. Answer like {"ok": true}.')
    outcome, _, llm = await run(
        [review_any, review_any, review_any, answer("merged")], config=config
    )

    assert outcome.status == "completed"
    systems = sorted(call[0]["content"] or "" for call in llm.calls[:3])
    assert systems[0] == 'Review claims. Answer like {"ok": true}.'
