"""The six templates keep their M2 behavior: same requests, graphs, edges and end states (SC-006).

Run with UPDATE_GOLDEN=1 to rewrite golden/templates.json from the current code.
"""

import json
import os
from pathlib import Path
from typing import Any

import pytest
from helpers import answer, ended, json_answer, lab_tools, make_tracer, taken_edges, tool_call

from agent_lab.agents.registry import AGENTS, validate_config
from agent_lab.agents.steps import config_version
from agent_lab.llm.base import ChatResponse, Message
from agent_lab.llm.fake import FakeLLM, ScriptItem
from agent_lab.llm.models import ModelRef

GOLDEN = Path(__file__).parent / "golden" / "templates.json"
CONCURRENT = {"parallel", "orchestrator"}  # their requests arrive in no fixed order


def review(messages: list[Message]) -> ChatResponse:
    system = messages[0]["content"] or ""
    return answer(next(f"{a} review" for a in ("clarity", "tone", "claims") if a in system))


def work(messages: list[Message]) -> ChatResponse:
    return answer(f"part for: {(messages[-1]['content'] or '').splitlines()[-1]}")


CASES: dict[str, tuple[str, str, list[ScriptItem]]] = {
    "react": (
        "react",
        "17*23?",
        [tool_call("calculator", '{"expression": "17*23"}'), answer("391")],
    ),
    "chain": (
        "chain",
        "A bottle",
        [answer("- a\n- b\n- c"), answer("draft"), answer("polished")],
    ),
    "chain-gate-fails": ("chain", "A bottle", [answer("- a\n- b")]),
    "routing-math": (
        "routing",
        "2**10?",
        [
            json_answer({"label": "math"}),
            tool_call("calculator", '{"expression": "2**10"}'),
            answer("1024"),
        ],
    ),
    "routing-weather": (
        "routing",
        "Weather in Oslo?",
        [
            json_answer({"label": "weather"}),
            tool_call("get_weather", '{"city": "Oslo"}'),
            answer("Cold"),
        ],
    ),
    "routing-general": (
        "routing",
        "Capital of France?",
        [json_answer({"label": "general"}), answer("Paris")],
    ),
    "routing-invalid": (
        "routing",
        "Who won?",
        [json_answer({"label": "sports"}), answer("No idea")],
    ),
    "parallel": ("parallel", "Best app!!!", [review, review, review, answer("merged")]),
    "orchestrator": (
        "orchestrator",
        "Porto trip",
        [json_answer({"subtasks": ["getting there", "food"]}), work, work, answer("note")],
    ),
    "evaluator": (
        "evaluator",
        "SunSip charger",
        [
            answer("Charge it"),
            json_answer({"approved": False, "feedback": "Mention SunSip."}),
            answer("SunSip charges you"),
            json_answer({"approved": True, "feedback": ""}),
        ],
    ),
}


async def run_template(case: str) -> dict[str, Any]:
    template_id, prompt, script = CASES[case]
    spec = AGENTS[template_id]
    llm = FakeLLM(list(script))
    config = validate_config(template_id, {}, ModelRef(provider="local", model=llm.model))
    tracer, events = make_tracer(template_id)
    result = await spec.create(llm, config, tracer, lab_tools()).run(prompt)
    requests = [
        json.loads(json.dumps({"messages": m, **r}))
        for m, r in zip(llm.calls, llm.requests, strict=True)
    ]
    if template_id in CONCURRENT:
        requests.sort(key=lambda r: json.dumps(r, sort_keys=True))
    return {
        "config_version": config_version(config),
        "graph": spec.graph(config).model_dump(),
        "requests": requests,
        "taken_edges": sorted(taken_edges(ended(events))),
        "status": result.status,
        "answer": result.answer,
    }


@pytest.mark.anyio
async def test_templates_match_m2() -> None:
    actual = {case: await run_template(case) for case in CASES}
    actual = json.loads(json.dumps(actual))  # tuples -> lists, as stored
    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(json.dumps(actual, indent=1, sort_keys=True) + "\n")
    golden = json.loads(GOLDEN.read_text())
    for case in CASES:
        want = {k: v for k, v in golden[case].items() if k != "config_version"}
        got = {k: v for k, v in actual[case].items() if k != "config_version"}
        assert got == want, case


@pytest.mark.anyio
async def test_config_versions() -> None:
    """Configs that kept their shape keep their version; re-expressed ones change it once."""
    golden = json.loads(GOLDEN.read_text())
    for case, same in [
        ("react", True),
        ("parallel", True),
        ("evaluator", True),
        ("chain", False),
        ("routing-math", False),
        ("orchestrator", False),
    ]:
        actual = (await run_template(case))["config_version"]
        assert (actual == golden[case]["config_version"]) is same, case


# M3 versions of the template configs on model "fake-model" (FR-009).
M3_VERSIONS = {
    "react": "68228ed54396",
    "chain": "00c06dfc8c05",
    "routing": "a0e74f7c0e02",
    "parallel": "126b8e7e0cff",
    "orchestrator": "a44081d7e009",
    "evaluator": "5c409451dd19",
}


@pytest.mark.parametrize("template_id", M3_VERSIONS)
def test_local_keeps_m3_version_openai_changes_it(template_id: str) -> None:
    model = AGENTS[template_id].config_model
    assert config_version(model(model="fake-model")) == M3_VERSIONS[template_id]
    assert config_version(model(model="fake-model", provider="local")) == M3_VERSIONS[template_id]
    assert config_version(model(model="fake-model", provider="openai")) != M3_VERSIONS[template_id]
