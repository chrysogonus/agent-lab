"""The judge: a yes-or-no question about an answer, as its own traced run (M17, FR-005)."""

from pathlib import Path

import pytest
from helpers import answer, assert_trace_valid, fake_models, json_answer

from agent_lab.bus import Bus
from agent_lab.evaluation.judge import run_judge
from agent_lab.evaluation.model import CheckResult, Judge
from agent_lab.llm.base import LLMError
from agent_lab.llm.fake import FakeLLM, ScriptItem
from agent_lab.llm.models import ModelRef
from agent_lab.store import Store

pytestmark = pytest.mark.anyio

CHECK = Judge(kind="judge", question="Does it give a temperature for Berlin?")
MODEL = ModelRef(provider="local", model="fake-model")


async def judged(store: Store, script: list[ScriptItem], text: str = "11 degrees") -> CheckResult:
    return await run_judge(
        CHECK,
        text,
        model=MODEL,
        eval_id="eval-1",
        store=store,
        models=fake_models(FakeLLM(script)),
        bus=Bus(),
    )


async def test_the_judges_yes_passes_and_its_no_fails(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    assert (await judged(store, [json_answer({"answer": "yes"})])).result == "pass"
    no = await judged(store, [json_answer({"answer": "no"})])
    assert no.result == "fail"
    assert no.reason == "the judge answered no"


@pytest.mark.parametrize(
    "script",
    [
        [json_answer({"answer": "maybe"})],
        [answer("I think so")],
        [LLMError("HTTP 400: refused")],
    ],
)
async def test_anything_but_yes_or_no_is_an_error_not_a_pass(
    tmp_path: Path, script: list[ScriptItem]
) -> None:
    result = await judged(Store(tmp_path / "lab.db"), script)
    assert result.result == "error"
    assert result.reason


async def test_an_empty_answer_fails_without_asking(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    result = await judged(store, [], text="")  # an exhausted script would raise if it asked
    assert result.result == "fail"
    assert result.judge_run_id is None


async def test_the_judges_call_is_a_traced_run_of_its_own(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    result = await judged(store, [json_answer({"answer": "yes"})])
    assert result.judge_run_id is not None

    run = store.get_run(result.judge_run_id)
    assert run is not None
    assert run.agent_id == "judge"
    assert run.eval_id == "eval-1"
    assert run.status == "completed"
    assert run.totals is not None
    assert run.totals.llm_calls == 1
    assert_trace_valid(run.graph, store.get_spans(run.run_id))
    assert store.list_runs() == []  # evaluation runs stay out of the run list
