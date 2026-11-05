"""Passing failures: which ones, how long to wait, and how attempts show (M17, FR-013, FR-014)."""

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from helpers import answer, fake_models, json_answer, lab_tools

from agent_lab.agents.registry import config_tools
from agent_lab.bus import Bus
from agent_lab.harness.budget import DEFAULT_BUDGET, Budget, Harness
from agent_lab.harness.guard import RunGuard
from agent_lab.harness.live import LiveRuns
from agent_lab.llm.anthropic import AnthropicClient
from agent_lab.llm.base import ChatResponse, LLMClient, LLMError, PassingLLMError
from agent_lab.llm.fake import FakeLLM, ScriptItem
from agent_lab.llm.openai_compat import OpenAICompatClient
from agent_lab.runs import execute_run, new_run
from agent_lab.store import Run, Store
from agent_lab.tracing.span import Span

Handler = Callable[[httpx.Request], httpx.Response]


def openai_client(handler: Handler) -> LLMClient:
    return OpenAICompatClient(
        base_url="http://llm.test/v1",
        model="m",
        api_key="k",
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def anthropic_client(handler: Handler) -> LLMClient:
    return AnthropicClient(
        base_url="http://llm.test/v1",
        model="claude-haiku-5-5",
        api_key="k",
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


CLIENTS = [openai_client, anthropic_client]
MESSAGES = [{"role": "user", "content": "hi"}]


async def failure_of(make: Callable[[Handler], LLMClient], handler: Handler) -> LLMError:
    with pytest.raises(LLMError) as caught:
        await make(handler).chat(MESSAGES, [])
    return caught.value


@pytest.mark.anyio
@pytest.mark.parametrize("make", CLIENTS)
@pytest.mark.parametrize("code", [408, 429, 500, 502, 503, 504, 529])
async def test_a_busy_provider_is_a_passing_failure(
    make: Callable[[Handler], LLMClient], code: int
) -> None:
    error = await failure_of(make, lambda _: httpx.Response(code, text="busy"))
    assert isinstance(error, PassingLLMError)
    assert str(error) == f"HTTP {code}: busy"  # the same text a plain failure would have


@pytest.mark.anyio
@pytest.mark.parametrize("make", CLIENTS)
@pytest.mark.parametrize("code", [400, 401, 403, 404, 422])
async def test_a_failure_waiting_cannot_fix_is_not_passing(
    make: Callable[[Handler], LLMClient], code: int
) -> None:
    error = await failure_of(make, lambda _: httpx.Response(code, text="refused"))
    assert not isinstance(error, PassingLLMError)
    assert str(error) == f"HTTP {code}: refused"


@pytest.mark.anyio
@pytest.mark.parametrize("make", CLIENTS)
async def test_running_out_of_quota_will_not_pass_by_waiting(
    make: Callable[[Handler], LLMClient],
) -> None:
    body = '{"error": {"code": "insufficient_quota", "message": "pay up"}}'
    error = await failure_of(make, lambda _: httpx.Response(429, text=body))
    assert not isinstance(error, PassingLLMError)


@pytest.mark.anyio
@pytest.mark.parametrize("make", CLIENTS)
@pytest.mark.parametrize(
    "failure",
    [httpx.ReadTimeout("slow"), httpx.ConnectError("refused"), httpx.RemoteProtocolError("gone")],
)
async def test_a_timeout_or_a_lost_connection_is_passing(
    make: Callable[[Handler], LLMClient], failure: httpx.TransportError
) -> None:
    def fails(_: httpx.Request) -> httpx.Response:
        raise failure

    assert isinstance(await failure_of(make, fails), PassingLLMError)


@pytest.mark.anyio
async def test_an_unreadable_answer_is_not_passing() -> None:
    error = await failure_of(openai_client, lambda _: httpx.Response(200, text="not json"))
    assert not isinstance(error, PassingLLMError)


@pytest.mark.anyio
async def test_a_declined_request_is_not_passing() -> None:
    declined: dict[str, Any] = {
        "stop_reason": "refusal",
        "content": [],
        "model": "claude-haiku-5-5",
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }
    error = await failure_of(anthropic_client, lambda _: httpx.Response(200, json=declined))
    assert not isinstance(error, PassingLLMError)


@pytest.mark.anyio
@pytest.mark.parametrize("make", CLIENTS)
@pytest.mark.parametrize(
    ("headers", "hint"),
    [
        ({"retry-after": "7"}, 7.0),
        ({"retry-after-ms": "1500"}, 1.5),
        ({"retry-after-ms": "1500", "retry-after": "7"}, 1.5),
        ({"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"}, None),
        ({}, None),
    ],
)
async def test_the_providers_wait_hint_is_read(
    make: Callable[[Handler], LLMClient], headers: dict[str, str], hint: float | None
) -> None:
    error = await failure_of(make, lambda _: httpx.Response(429, text="busy", headers=headers))
    assert isinstance(error, PassingLLMError)
    assert error.wait_hint == hint


BUSY = PassingLLMError("HTTP 429: rate limited")


def budget(**limits: Any) -> Budget:
    return DEFAULT_BUDGET.model_copy(update=limits)


class Waits:
    """Records each retry wait instead of sleeping through it."""

    def __init__(self) -> None:
        self.seconds: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.seconds.append(seconds)


async def run_it(
    store: Store,
    script: list[ScriptItem],
    *,
    agent_id: str = "react",
    harness: Harness | None = None,
    waits: Waits | None = None,
    guarded: bool = True,
) -> tuple[Run, list[Span], FakeLLM]:
    llm = FakeLLM(script)
    run, config, spec, client = new_run("Do it", agent_id, fake_models(llm), store)
    store.create_run(run)
    guard = RunGuard(harness or Harness(), sleep=waits or Waits()) if guarded else None
    await execute_run(
        run=run,
        prompt="Do it",
        config=config,
        spec=spec,
        llm=client,
        store=store,
        bus=Bus(),
        tools=lab_tools(*config_tools(config)) if config_tools(config) else {},
        guard=guard,
    )
    done = store.get_run(run.run_id)
    assert done is not None
    return done, store.get_spans(run.run_id), llm


def attempts(spans: list[Span]) -> list[Span]:
    return [s for s in spans if s.kind == "llm"]


@pytest.mark.anyio
async def test_a_provider_busy_twice_then_answering_completes(tmp_path: Path) -> None:
    waits = Waits()
    done, spans, _ = await run_it(
        Store(tmp_path / "lab.db"), [BUSY, BUSY, answer("done")], waits=waits
    )
    assert done.status == "completed"
    assert done.answer == "done"
    assert waits.seconds == [2, 8]  # each wait longer than the last
    tried = attempts(spans)
    assert len(tried) == 3  # every attempt visible in the trace
    assert [s.error for s in tried] == ["HTTP 429: rate limited", "HTTP 429: rate limited", None]
    assert tried[0].attributes["lab.retry.wait_s"] == 2
    assert tried[0].attributes["lab.retry.reason"] == "HTTP 429: rate limited"
    assert tried[1].attributes["lab.retry.attempt"] == 2
    assert tried[2].attributes["lab.retry.attempt"] == 3
    assert "lab.retry.wait_s" not in tried[2].attributes
    assert done.totals is not None
    assert done.totals.llm_calls == 3


@pytest.mark.anyio
async def test_a_clean_call_carries_nothing_about_retries(tmp_path: Path) -> None:
    _, spans, _ = await run_it(Store(tmp_path / "lab.db"), [answer("done")])
    assert not any(k.startswith("lab.retry") for k in attempts(spans)[0].attributes)


@pytest.mark.anyio
async def test_a_refused_request_ends_the_run_at_once(tmp_path: Path) -> None:
    waits = Waits()
    done, spans, llm = await run_it(
        Store(tmp_path / "lab.db"), [LLMError("HTTP 400: invalid"), answer("no")], waits=waits
    )
    assert done.status == "error"
    assert len(llm.calls) == 1
    assert waits.seconds == []
    assert attempts(spans)[0].error == "LLMError: HTTP 400: invalid"


@pytest.mark.anyio
async def test_a_provider_busy_every_time_ends_after_three_attempts(tmp_path: Path) -> None:
    done, spans, llm = await run_it(Store(tmp_path / "lab.db"), [BUSY] * 5)
    assert done.status == "error"
    assert len(llm.calls) == 3
    assert "HTTP 429: rate limited" in (attempts(spans)[-1].error or "")


@pytest.mark.anyio
@pytest.mark.parametrize(("hint", "wait"), [(7.0, 7.0), (0.5, 0.5), (100.0, 30.0)])
async def test_the_providers_hint_replaces_the_wait_up_to_a_limit(
    tmp_path: Path, hint: float, wait: float
) -> None:
    waits = Waits()
    await run_it(
        Store(tmp_path / "lab.db"),
        [PassingLLMError("HTTP 429: busy", wait_hint=hint), answer("done")],
        waits=waits,
    )
    assert waits.seconds == [wait]


@pytest.mark.anyio
async def test_a_wait_past_the_time_budget_ends_the_run_instead(tmp_path: Path) -> None:
    waits = Waits()
    done, _, llm = await run_it(
        Store(tmp_path / "lab.db"),
        [PassingLLMError("HTTP 429: busy", wait_hint=20.0), answer("too late")],
        harness=Harness(budget=budget(seconds=5)),
        waits=waits,
    )
    assert done.status == "over_budget"
    assert done.stop_reason == "time: 5 s of 5 s"
    assert waits.seconds == []  # it did not wait
    assert len(llm.calls) == 1


@pytest.mark.anyio
async def test_every_attempt_counts_against_the_budget(tmp_path: Path) -> None:
    done, _, llm = await run_it(
        Store(tmp_path / "lab.db"),
        [BUSY, BUSY, answer("too late")],
        harness=Harness(budget=budget(model_calls=2)),
    )
    assert done.status == "over_budget"
    assert done.stop_reason == "model calls: 2 of 2"
    assert len(llm.calls) == 2


@pytest.mark.anyio
async def test_a_decision_is_retried_too(tmp_path: Path) -> None:
    done, _, _ = await run_it(
        Store(tmp_path / "lab.db"),
        [BUSY, json_answer({"label": "general"}), answer("Paris")],
        agent_id="routing",
    )
    assert done.status == "completed"
    assert done.answer == "Paris"


@pytest.mark.anyio
async def test_without_a_guard_nothing_is_retried(tmp_path: Path) -> None:
    done, _, llm = await run_it(Store(tmp_path / "lab.db"), [BUSY, answer("no")], guarded=False)
    assert done.status == "error"
    assert len(llm.calls) == 1


@pytest.mark.anyio
async def test_stop_ends_a_retry_wait(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    llm = FakeLLM([BUSY, answer("too late")])
    run, config, spec, client = new_run("Do it", "react", fake_models(llm), store)
    store.create_run(run)

    async def forever(_seconds: float) -> None:
        await asyncio.Event().wait()

    guard = RunGuard(Harness(), sleep=forever)
    task = asyncio.create_task(
        execute_run(
            run=run,
            prompt="Do it",
            config=config,
            spec=spec,
            llm=client,
            store=store,
            bus=Bus(),
            tools=lab_tools(*config_tools(config)),
            guard=guard,
        )
    )
    live = LiveRuns()
    live.add(run.run_id, task, guard)
    await asyncio.sleep(0.02)
    assert live.stop(run.run_id) is True
    await asyncio.wait_for(task, 2)
    done = store.get_run(run.run_id)
    assert done is not None
    assert done.status == "stopped"
    assert len(llm.calls) == 1


@pytest.mark.anyio
async def test_a_retried_attempts_tokens_count_only_if_reported(tmp_path: Path) -> None:
    done, _, _ = await run_it(
        Store(tmp_path / "lab.db"),
        [BUSY, ChatResponse(content="done", tokens_in=5, tokens_out=5)],
        harness=Harness(budget=budget(tokens=11)),
    )
    assert done.status == "completed"
