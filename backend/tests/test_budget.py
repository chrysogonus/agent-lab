"""Budgets: what one may hold, and what a run does when it reaches one (M17, FR-010, FR-011)."""

import asyncio
from pathlib import Path
from typing import Any

import pytest
from helpers import (
    answer,
    branches_block,
    fake_models,
    json_answer,
    lab_tools,
    model_block,
    tool_call,
)
from pydantic import ValidationError

from agent_lab.agents.registry import config_tools
from agent_lab.bus import Bus
from agent_lab.harness.budget import DEFAULT_BUDGET, MAX_BUDGET, Budget, Harness, OverBudget
from agent_lab.harness.guard import RunGuard
from agent_lab.llm.base import ChatResponse, ToolCall
from agent_lab.llm.fake import FakeLLM, ScriptItem
from agent_lab.runs import execute_run, new_run
from agent_lab.store import Run, Store
from agent_lab.tracing.span import Span

FOUR = {"model_calls": 1, "tokens": 1, "tool_calls": 1, "seconds": 1}


@pytest.mark.parametrize(
    "bad",
    [
        {**FOUR, "model_calls": 0},
        {**FOUR, "model_calls": 201},
        {**FOUR, "tokens": 2_000_001},
        {**FOUR, "tool_calls": 201},
        {**FOUR, "seconds": 3_601},
        {**FOUR, "extra": 1},
        {"model_calls": 1, "tokens": 1, "tool_calls": 1},
    ],
)
def test_a_budget_outside_the_limits_is_refused(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Budget.model_validate(bad)


def test_the_most_a_budget_may_be_is_allowed() -> None:
    biggest = {"model_calls": 200, "tokens": 2_000_000, "tool_calls": 200, "seconds": 3_600}
    assert Budget.model_validate(biggest) == MAX_BUDGET


def test_the_default_budget_is_within_the_limits() -> None:
    assert Budget.model_validate(DEFAULT_BUDGET.model_dump()) == DEFAULT_BUDGET
    assert DEFAULT_BUDGET.model_calls == 30
    assert DEFAULT_BUDGET.tokens == 200_000


@pytest.mark.parametrize(
    ("what", "used", "limit", "reason"),
    [
        ("model calls", 3, 3, "model calls: 3 of 3"),
        ("tokens", 205_120, 200_000, "tokens: 205,120 of 200,000"),
        ("tool calls", 30, 30, "tool calls: 30 of 30"),
    ],
)
def test_the_reason_says_which_limit_and_how_much(
    what: str, used: int, limit: int, reason: str
) -> None:
    assert OverBudget.of(what, used, limit).reason == reason


def budget(**limits: Any) -> Budget:
    return DEFAULT_BUDGET.model_copy(update=limits)  # a test's fraction of a second is allowed here


def over_and_over() -> list[ScriptItem]:
    return [tool_call("calculator", '{"expression": "1+1"}')] * 20


async def run_it(
    store: Store, llm: FakeLLM, agent_id: str, harness: Harness | None
) -> tuple[Run, list[Span]]:
    run, config, spec, client = new_run("Do it", agent_id, fake_models(llm), store)
    store.create_run(run)
    tools = lab_tools(*config_tools(config)) if config_tools(config) else {}
    await execute_run(
        run=run,
        prompt="Do it",
        config=config,
        spec=spec,
        llm=client,
        store=store,
        bus=Bus(),
        tools=tools,
        guard=RunGuard(harness) if harness else None,
    )
    done = store.get_run(run.run_id)
    assert done is not None
    return done, store.get_spans(run.run_id)


def llm_spans(spans: list[Span]) -> list[Span]:
    return [s for s in spans if s.kind == "llm"]


def tool_spans(spans: list[Span]) -> list[Span]:
    return [s for s in spans if s.kind == "tool"]


@pytest.mark.anyio
async def test_a_run_stops_before_the_call_past_its_limit(tmp_path: Path) -> None:
    llm = FakeLLM(over_and_over())
    done, spans = await run_it(
        Store(tmp_path / "lab.db"), llm, "react", Harness(budget=budget(model_calls=3))
    )
    assert done.status == "over_budget"
    assert done.stop_reason == "model calls: 3 of 3"
    assert len(llm.calls) == 3
    assert len(llm_spans(spans)) == 3
    assert all(s.ended_at is not None for s in spans)  # the trace up to that point is kept


@pytest.mark.anyio
async def test_reaching_the_limit_on_the_last_call_is_no_failure(tmp_path: Path) -> None:
    script: list[ScriptItem] = [tool_call("calculator", '{"expression": "1"}'), answer("done")]
    done, _ = await run_it(
        Store(tmp_path / "lab.db"), FakeLLM(script), "react", Harness(budget=budget(model_calls=2))
    )
    assert done.status == "completed"
    assert done.answer == "done"
    assert done.stop_reason is None


@pytest.mark.anyio
async def test_a_call_going_past_the_token_limit_starts_no_further_step(tmp_path: Path) -> None:
    llm = FakeLLM(over_and_over())  # helpers.tool_call: 10 in, 5 out
    done, spans = await run_it(
        Store(tmp_path / "lab.db"), llm, "react", Harness(budget=budget(tokens=14))
    )
    assert done.status == "over_budget"
    assert done.stop_reason == "tokens: 15 of 14"
    assert len(llm.calls) == 1
    assert tool_spans(spans) == []  # the tool call it asked for never went out


@pytest.mark.anyio
async def test_using_exactly_the_tokens_allows_no_further_call(tmp_path: Path) -> None:
    llm = FakeLLM(over_and_over())
    done, _ = await run_it(
        Store(tmp_path / "lab.db"), llm, "react", Harness(budget=budget(tokens=15))
    )
    assert done.status == "over_budget"
    assert done.stop_reason == "tokens: 15 of 15"
    assert len(llm.calls) == 1  # the tool call ran, the second model call did not


@pytest.mark.anyio
async def test_an_answer_past_the_token_limit_ends_over_budget_and_keeps_the_answer(
    tmp_path: Path,
) -> None:
    done, _ = await run_it(
        Store(tmp_path / "lab.db"),
        FakeLLM([answer("all done")]),  # helpers.answer: 20 in, 3 out
        "react",
        Harness(budget=budget(tokens=10)),
    )
    assert done.status == "over_budget"
    assert done.answer == "all done"


@pytest.mark.anyio
async def test_tokens_a_provider_does_not_report_count_as_none(tmp_path: Path) -> None:
    done, _ = await run_it(
        Store(tmp_path / "lab.db"),
        FakeLLM([ChatResponse(content="done")]),
        "react",
        Harness(budget=budget(tokens=1)),
    )
    assert done.status == "completed"


@pytest.mark.anyio
async def test_the_tool_call_past_the_limit_never_goes_out(tmp_path: Path) -> None:
    calls = [
        ToolCall(id=str(i), name="calculator", arguments='{"expression": "1"}') for i in range(3)
    ]
    llm = FakeLLM([ChatResponse(tool_calls=calls, tokens_in=1, tokens_out=1), answer("done")])
    done, spans = await run_it(
        Store(tmp_path / "lab.db"), llm, "react", Harness(budget=budget(tool_calls=2))
    )
    assert done.status == "over_budget"
    assert done.stop_reason == "tool calls: 2 of 2"
    assert len(tool_spans(spans)) == 2


@pytest.mark.anyio
async def test_the_time_budget_abandons_a_slow_call(tmp_path: Path) -> None:
    llm = FakeLLM([answer("too late")], delay=30)
    done, spans = await run_it(
        Store(tmp_path / "lab.db"), llm, "react", Harness(budget=budget(seconds=0.05))
    )
    assert done.status == "over_budget"
    assert done.stop_reason == "time: 0.05 s of 0.05 s"
    assert all(s.ended_at is not None for s in spans)


@pytest.mark.anyio
async def test_a_timeout_from_inside_the_agent_is_not_the_time_budget(tmp_path: Path) -> None:
    done, _ = await run_it(
        Store(tmp_path / "lab.db"),
        FakeLLM([TimeoutError("the model timed out")]),
        "react",
        Harness(budget=budget()),
    )
    assert done.status == "error"
    assert done.stop_reason is None


@pytest.mark.anyio
async def test_no_budget_runs_as_before(tmp_path: Path) -> None:
    llm = FakeLLM(over_and_over())
    done, _ = await run_it(Store(tmp_path / "lab.db"), llm, "react", Harness())
    assert done.status == "max_iterations"
    assert len(llm.calls) == 6


@pytest.mark.anyio
async def test_no_guard_runs_as_before(tmp_path: Path) -> None:
    llm = FakeLLM(over_and_over())
    done, _ = await run_it(Store(tmp_path / "lab.db"), llm, "react", None)
    assert done.status == "max_iterations"


SUBTASKS = json_answer({"subtasks": ["one", "two"]})
FIRST_CALLS: dict[str, ScriptItem] = {
    "react": tool_call("calculator", '{"expression": "1"}'),
    "chain": answer("- a\n- b\n- c"),
    "routing": json_answer({"label": "general"}),
    "parallel": answer("a review"),
    "orchestrator": SUBTASKS,
    "evaluator": answer("a draft"),
}


@pytest.mark.anyio
@pytest.mark.parametrize("template_id", list(FIRST_CALLS))
async def test_no_template_passes_its_limit(tmp_path: Path, template_id: str) -> None:
    llm = FakeLLM([FIRST_CALLS[template_id]] * 10)
    done, spans = await run_it(
        Store(tmp_path / "lab.db"), llm, template_id, Harness(budget=budget(model_calls=1))
    )
    assert done.status == "over_budget"
    assert done.stop_reason == "model calls: 1 of 1"
    assert len(llm.calls) == 1
    assert len(llm_spans(spans)) == 1


@pytest.mark.anyio
async def test_calls_under_way_finish_and_the_extra_branch_never_starts(tmp_path: Path) -> None:
    llm = FakeLLM([answer("a review")] * 3, delay=0.02)
    done, spans = await run_it(
        Store(tmp_path / "lab.db"), llm, "parallel", Harness(budget=budget(model_calls=2))
    )
    assert done.status == "over_budget"
    assert len(llm.calls) == 2  # three branches, and the third was refused before it went out
    finished = llm_spans(spans)
    assert len(finished) == 2
    assert all(s.output is not None for s in finished)  # they finished, and were not abandoned


@pytest.mark.anyio
async def test_a_block_agents_parallel_branches_share_one_budget(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    fan = branches_block("fan", {n: [model_block(f"{n}-call")] for n in ("a", "b", "c")})
    agent = store.create_agent(
        template_id="blocks",
        name="Fan out",
        description="",
        sample_prompt="hi",
        config={"blocks": [fan]},
    )
    llm = FakeLLM([answer("part")] * 3, delay=0.02)
    done, spans = await run_it(store, llm, agent.agent_id, Harness(budget=budget(model_calls=2)))
    assert done.status == "over_budget"
    assert len(llm.calls) == 2
    assert all(s.ended_at is not None for s in spans)


@pytest.mark.anyio
async def test_the_clock_can_be_paused_longer_than_the_whole_budget(tmp_path: Path) -> None:
    guard = RunGuard(Harness(budget=budget(seconds=0.05)))
    async with asyncio.timeout(0.05) as scope:
        guard.bind_clock(scope)
        guard.pause_clock()
        await asyncio.sleep(0.1)
        guard.resume_clock()
    assert not scope.expired()


@pytest.mark.anyio
async def test_a_resumed_clock_still_ends_the_run(tmp_path: Path) -> None:
    guard = RunGuard(Harness(budget=budget(seconds=0.05)))
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.05) as scope:
            guard.bind_clock(scope)
            guard.pause_clock()
            await asyncio.sleep(0.01)
            guard.resume_clock()
            await asyncio.sleep(5)


@pytest.mark.anyio
async def test_the_clock_stays_paused_until_the_last_wait_ends(tmp_path: Path) -> None:
    guard = RunGuard(Harness(budget=budget(seconds=0.05)))
    async with asyncio.timeout(0.05) as scope:
        guard.bind_clock(scope)
        guard.pause_clock()
        guard.pause_clock()  # two parallel branches are waiting
        guard.resume_clock()  # one answered: the other still is
        await asyncio.sleep(0.1)
        guard.resume_clock()
    assert not scope.expired()
