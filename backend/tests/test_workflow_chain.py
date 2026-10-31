import pytest
from helpers import answer, assert_trace_valid, ended, make_tracer, taken_edges

from agent_lab.agents.steps import Outcome
from agent_lab.llm.fake import FakeLLM, ScriptItem
from agent_lab.tracing.span import Span
from agent_lab.workflows.chain import AGENT_ID, ChainStep, ChainWorkflow, Config, build_graph

OUTLINE = "- tracks every sip\n- glows when you should drink\n- keeps water cold"


async def run(
    script: list[ScriptItem], config: Config | None = None
) -> tuple[Outcome, list[Span], FakeLLM]:
    llm = FakeLLM(script)
    tracer, events = make_tracer(AGENT_ID)
    config = config or Config(model=llm.model)
    workflow = ChainWorkflow(llm=llm, config=config, tracer=tracer)
    outcome = await workflow.run("smart bottle")
    return outcome, ended(events), llm


@pytest.mark.anyio
async def test_happy_path() -> None:
    outcome, spans, llm = await run([answer(OUTLINE), answer("draft"), answer("final blurb")])

    assert (outcome.status, outcome.answer) == ("completed", "final blurb")
    assert_trace_valid(build_graph(Config(model="m")), spans)
    assert {s.agent_id for s in spans} == {AGENT_ID}
    assert all(r["reasoning"] is False for r in llm.requests)
    gate = next(s for s in spans if s.name == "gate")
    assert gate.output == {"passed": True, "reason": "3 bullet lines"}
    assert OUTLINE in llm.calls[1][-1]["content"]  # the outline feeds the draft
    assert llm.calls[2][-1]["content"] == "draft"
    assert taken_edges(spans) == {
        ("start", "outline"),
        ("outline", "gate"),
        ("gate", "draft"),
        ("draft", "polish"),
        ("polish", "end"),
    }


@pytest.mark.anyio
async def test_gate_fails_stops_chain() -> None:
    outcome, spans, llm = await run([answer("- only one\n- and two\njust prose")])

    assert (outcome.status, outcome.answer) == ("error", None)
    gate = next(s for s in spans if s.name == "gate")
    assert gate.error == "outline has 2 bullet lines, needs at least 3"
    assert gate.output == {"passed": False, "reason": gate.error}
    assert len(llm.calls) == 1  # no draft or polish
    assert {s.node_id for s in spans} == {"start", "outline", "gate", "end"}
    assert spans[-1].error == f"gate failed: {gate.error}"
    assert taken_edges(spans) == {("start", "outline"), ("outline", "gate"), ("gate", "end")}
    assert_trace_valid(build_graph(Config(model="m")), spans)


def steps(*names: str, include_input: bool = False) -> list[ChainStep]:
    return [ChainStep(name=n, prompt=f"Do {n}.", include_input=include_input) for n in names]


@pytest.mark.anyio
async def test_single_step_with_gate() -> None:
    config = Config(model="m", steps=steps("outline"))
    outcome, spans, _ = await run([answer(OUTLINE)], config)

    assert (outcome.status, outcome.answer) == ("completed", OUTLINE)
    assert taken_edges(spans) == {("start", "outline"), ("outline", "gate"), ("gate", "end")}
    assert_trace_valid(build_graph(config), spans)


@pytest.mark.anyio
async def test_six_steps_gate_off() -> None:
    names = ("a", "b", "c", "d", "e", "f")
    config = Config(model="m", steps=steps(*names), gate=False)
    outcome, spans, llm = await run([answer(n.upper()) for n in names], config)

    assert (outcome.status, outcome.answer) == ("completed", "F")
    assert len(llm.calls) == 6
    graph = build_graph(config)
    assert "gate" not in graph.node_ids()
    assert_trace_valid(graph, spans)
    assert taken_edges(spans) == {
        ("start", "a"),
        ("a", "b"),
        ("b", "c"),
        ("c", "d"),
        ("d", "e"),
        ("e", "f"),
        ("f", "end"),
    }


@pytest.mark.anyio
async def test_include_input_message() -> None:
    config = Config(
        model="m",
        steps=[*steps("notes"), *steps("draft-it", include_input=True), *steps("tidy")],
        input_label="Topic",
        gate=False,
    )
    _, _, llm = await run([answer("N"), answer("D"), answer("T")], config)

    assert llm.calls[1][-1]["content"] == "Topic: smart bottle\n\nNotes:\nN"
    assert llm.calls[2][-1]["content"] == "D"


@pytest.mark.anyio
@pytest.mark.parametrize(("minimum", "status"), [(1, "completed"), (10, "error")])
async def test_gate_min_bullets(minimum: int, status: str) -> None:
    config = Config(model="m", gate_min_bullets=minimum)
    script: list[ScriptItem] = [answer(OUTLINE), answer("draft"), answer("polished")]
    outcome, _, _ = await run(script, config)
    assert outcome.status == status


@pytest.mark.anyio
async def test_added_step_runs_last() -> None:
    config = Config(model="m")
    config = config.model_copy(update={"steps": [*config.steps, *steps("german")]})
    script: list[ScriptItem] = [
        answer(OUTLINE),
        answer("draft"),
        answer("polished"),
        answer("deutsch"),
    ]
    outcome, spans, llm = await run(script, config)

    assert (outcome.status, outcome.answer) == ("completed", "deutsch")
    assert llm.calls[3][-1]["content"] == "polished"
    assert ("german", "end") in taken_edges(spans)
    assert_trace_valid(build_graph(config), spans)
