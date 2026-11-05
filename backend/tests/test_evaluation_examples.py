"""Every template comes with examples that pass on the scripted model (M17, FR-009)."""

from pathlib import Path

import pytest
from helpers import answer, fake_models, json_answer, lab_tools, tool_call
from test_templates import review, work

from agent_lab.agents.registry import AGENTS, config_tools
from agent_lab.bus import Bus
from agent_lab.evaluation.checks import run_check
from agent_lab.evaluation.examples import EXAMPLES
from agent_lab.evaluation.model import Judge
from agent_lab.evaluation.results import attempt_outcome
from agent_lab.llm.fake import FakeLLM, ScriptItem
from agent_lab.runs import execute_run, new_run
from agent_lab.store import Store

OUTLINE = answer("- light\n- folds\n- cheap")
ROUGH = answer("a first draft")
POLISHED = answer("the finished copy")
SUBTASKS = json_answer({"subtasks": ["getting there", "food"]})
APPROVED = json_answer({"approved": True, "feedback": ""})

SCRIPTS: dict[str, list[ScriptItem]] = {
    "example-react-1": [
        tool_call("calculator", '{"expression": "17*23"}'),
        answer("17 times 23 is 391."),
    ],
    "example-react-2": [
        tool_call("get_weather", '{"city": "Berlin"}'),
        answer("It is 11 degrees and raining in Berlin."),
    ],
    "example-chain-1": [OUTLINE, ROUGH, POLISHED],
    "example-chain-2": [OUTLINE, ROUGH, POLISHED],
    "example-routing-1": [
        json_answer({"label": "math"}),
        tool_call("calculator", '{"expression": "2**10 - 24"}'),
        answer("That makes 1000."),
    ],
    "example-routing-2": [
        json_answer({"label": "weather"}),
        tool_call("get_weather", '{"city": "Oslo"}'),
        answer("Oslo is cold today."),
    ],
    "example-parallel-1": [review, review, review, answer("Merged advice.")],
    "example-parallel-2": [review, review, review, answer("Merged advice.")],
    "example-orchestrator-1": [SUBTASKS, work, work, answer("The whole note.")],
    "example-orchestrator-2": [SUBTASKS, work, work, answer("The whole note.")],
    "example-evaluator-1": [answer("SunSip charges your phone."), APPROVED],
    "example-evaluator-2": [answer("BrushRoot cleans your teeth."), APPROVED],
}


def test_every_template_has_at_least_two_examples_with_their_own_ids() -> None:
    assert set(EXAMPLES) == set(AGENTS)
    ids = [case.case_id for cases in EXAMPLES.values() for case in cases]
    assert len(ids) == len(set(ids))
    for template_id, cases in EXAMPLES.items():
        assert len(cases) >= 2, template_id
        assert all(c.read_only and c.agent_id == template_id for c in cases)
        assert not any(isinstance(check, Judge) for c in cases for check in c.checks)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("template_id", "number"), [(t, n) for t in EXAMPLES for n in range(len(EXAMPLES[t]))]
)
async def test_an_example_passes_on_its_scripted_run(
    tmp_path: Path, template_id: str, number: int
) -> None:
    case = EXAMPLES[template_id][number]
    store = Store(tmp_path / "lab.db")
    models = fake_models(FakeLLM(list(SCRIPTS[case.case_id])))
    run, config, spec, llm = new_run(case.prompt, template_id, models, store)
    store.create_run(run)
    await execute_run(
        run=run,
        prompt=case.prompt,
        config=config,
        spec=spec,
        llm=llm,
        store=store,
        bus=Bus(),
        tools=lab_tools(*config_tools(config)) if config_tools(config) else {},
    )

    done = store.get_run(run.run_id)
    assert done is not None
    spans = store.get_spans(run.run_id)
    results = [run_check(c, done, spans) for c in case.checks if not isinstance(c, Judge)]
    assert attempt_outcome(done, results) == ("pass", None), results
