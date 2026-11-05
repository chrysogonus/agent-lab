import pytest
from helpers import answer, assert_trace_valid, ended, json_answer, make_tracer

from agent_lab.agents.steps import Outcome
from agent_lab.llm.base import ChatResponse, LLMError, Message
from agent_lab.llm.fake import FakeLLM, ScriptItem
from agent_lab.tracing.span import Span
from agent_lab.workflows.orchestrator import AGENT_ID, Config, OrchestratorWorkflow, build_graph


async def run(
    script: list[ScriptItem], delay: float = 0, config: Config | None = None
) -> tuple[Outcome, list[Span], FakeLLM]:
    llm = FakeLLM(script, delay=delay)
    tracer, events = make_tracer(AGENT_ID)
    config = config or Config(model=llm.model)
    workflow = OrchestratorWorkflow(llm=llm, config=config, tracer=tracer)
    outcome = await workflow.run("Porto weekend")
    return outcome, ended(events), llm


@pytest.mark.anyio
async def test_happy_path() -> None:
    plan = json_answer({"subtasks": ["getting there", "food"]})
    outcome, spans, llm = await run([plan, answer("part"), answer("part"), answer("note")])

    assert (outcome.status, outcome.answer) == ("completed", "note")
    assert_trace_valid(build_graph(), spans)
    assert all(r["reasoning"] is False for r in llm.requests)
    assert [s.name for s in spans if s.node_id == "worker" and s.kind == "step"] == [
        "worker 0",
        "worker 1",
    ]
    synth_input = llm.calls[3][-1]["content"]
    assert "getting there" in synth_input and "food" in synth_input


@pytest.mark.anyio
async def test_three_subtasks() -> None:
    plan = json_answer({"subtasks": ["train", "sights", "food"]})
    parts = [answer("part")] * 3
    outcome, spans, _ = await run([plan, *parts, answer("note")], delay=0.05)

    assert outcome.status == "completed"
    plan_span = next(s for s in spans if s.name == "plan")
    assert plan_span.output == {"subtasks": ["train", "sights", "food"]}
    workers = [s for s in spans if s.name.startswith("worker ")]
    assert {w.node_id for w in workers} == {"worker"}
    assert sorted(w.attributes["lab.worker.index"] for w in workers) == [0, 1, 2]
    assert {w.input for w in workers} == {"train", "sights", "food"}
    assert {w.parent_span_id for w in workers} == {spans[0].span_id}
    assert max(w.started_at for w in workers) < min(w.ended_at or 0 for w in workers)
    synth = next(s for s in spans if s.node_id == "synthesizer")
    assert synth.attributes["lab.came_from"] == ["worker"]
    assert_trace_valid(build_graph(), spans)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "content",
    [
        "I would rather not plan.",
        '{"subtasks": ["a", "b", "c", "d", "e"]}',
        '{"subtasks": []}',
        '{"subtasks": ["a", "   "]}',
        '{"subtasks": ["' + "x" * 201 + '"]}',
    ],
)
async def test_invalid_plan_ends_run(content: str) -> None:
    outcome, spans, llm = await run([answer(content)])

    assert (outcome.status, outcome.answer) == ("error", None)
    plan_span = next(s for s in spans if s.name == "plan")
    assert plan_span.error is not None and plan_span.error.startswith("invalid plan:")
    assert len(llm.calls) == 1
    assert not any(s.node_id == "worker" for s in spans)
    end = spans[-1]
    assert (end.node_id, end.error) == ("end", plan_span.error)
    assert end.attributes["lab.came_from"] == ["orchestrator"]
    assert_trace_valid(build_graph(), spans)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("limit", "rendered"),
    [
        (1, "into 1 to 1 independent"),
        (4, "into 2 to 4 independent"),
        (6, "into 2 to 6 independent"),
    ],
)
async def test_subtask_limit_renders_prompt_and_schema(limit: int, rendered: str) -> None:
    plan = json_answer({"subtasks": ["one"]})
    _, _, llm = await run(
        [plan, answer("part"), answer("note")], config=Config(model="m", max_subtasks=limit)
    )

    assert rendered in (llm.calls[0][0]["content"] or "")
    response_format = llm.requests[0]["response_format"]
    assert response_format is not None
    schema = response_format["json_schema"]["schema"]
    assert schema["properties"]["subtasks"]["maxItems"] == limit
    assert schema["title"] == "Plan"


@pytest.mark.anyio
@pytest.mark.parametrize("count", [1, 6])
async def test_one_and_six_workers(count: int) -> None:
    subtasks = [f"part {i}" for i in range(count)]
    script: list[ScriptItem] = [json_answer({"subtasks": subtasks})]
    script += [answer("done")] * count + [answer("note")]
    outcome, spans, _ = await run(script, config=Config(model="m", max_subtasks=count))

    assert (outcome.status, outcome.answer) == ("completed", "note")
    workers = [s for s in spans if s.node_id == "worker" and s.kind == "step"]
    assert sorted(s.attributes["lab.worker.index"] for s in workers) == list(range(count))
    assert_trace_valid(build_graph(), spans)


@pytest.mark.anyio
async def test_plan_above_limit_invalid() -> None:
    plan = json_answer({"subtasks": ["a", "b", "c"]})
    outcome, spans, _ = await run([plan], config=Config(model="m", max_subtasks=2))

    assert outcome.status == "error"
    assert not [s for s in spans if s.node_id == "worker"]


@pytest.mark.anyio
async def test_a_failing_worker_leaves_no_other_worker_running() -> None:
    """A run must not end while a sibling call is still out (FR-011)."""

    def fails_or_answers(messages: list[Message]) -> ChatResponse | Exception:
        if "first" in (messages[-1]["content"] or ""):
            return LLMError("HTTP 400: refused")
        return answer("part")

    llm = FakeLLM(
        [json_answer({"subtasks": ["first", "second"]}), fails_or_answers, fails_or_answers],
        delay=0.01,
    )
    tracer, events = make_tracer(AGENT_ID)
    workflow = OrchestratorWorkflow(llm=llm, config=Config(model=llm.model), tracer=tracer)

    with pytest.raises(LLMError):
        await workflow.run("A note")

    started = {s.span_id for e, s in events if e == "span_started"}
    ended = {s.span_id for e, s in events if e == "span_ended"}
    assert started == ended
