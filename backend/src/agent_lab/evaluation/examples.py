"""The example cases each template ships with: read-only, with stable ids (FR-009).

Their checks ask for stable facts, not wording, since SC-007 runs them on a real model too.
"""

from typing import Any

from agent_lab.evaluation.model import Case


def _case(template_id: str, number: int, name: str, prompt: str, *checks: dict[str, Any]) -> Case:
    return Case.model_validate(
        {
            "case_id": f"example-{template_id}-{number}",
            "agent_id": template_id,
            "read_only": True,
            "name": name,
            "prompt": prompt,
            "checks": checks,
        }
    )


COMPLETES = {"kind": "end_state", "state": "completed"}
ANSWERS = {"kind": "matches", "pattern": r"\S"}


def _calls(tool: str) -> dict[str, str]:
    return {"kind": "tool_called", "tool": tool}


def _contains(text: str) -> dict[str, str]:
    return {"kind": "contains", "text": text}


def _at_most(calls: int) -> dict[str, Any]:
    return {"kind": "max_model_calls", "limit": calls}


EXAMPLES: dict[str, list[Case]] = {
    "react": [
        _case(
            "react",
            1,
            "Multiplies with the calculator",
            "What is 17 times 23?",
            _contains("391"),
            _calls("calculator"),
            COMPLETES,
        ),
        _case(
            "react",
            2,
            "Looks up the weather",
            "What is the weather in Berlin right now?",
            _calls("get_weather"),
            {"kind": "tool_not_called", "tool": "calculator"},
            COMPLETES,
        ),
    ],
    "chain": [
        _case(
            "chain",
            1,
            "Writes copy for a bottle",
            "A reusable water bottle that tracks how much you drink",
            COMPLETES,
            _at_most(3),
            ANSWERS,
        ),
        _case(
            "chain",
            2,
            "Writes copy for a bicycle",
            "A folding bicycle for city commuters",
            COMPLETES,
            _at_most(3),
            ANSWERS,
        ),
    ],
    "routing": [
        _case(
            "routing",
            1,
            "Routes arithmetic to the calculator",
            "What is 2**10 minus 24?",
            _contains("1000"),
            _calls("calculator"),
            COMPLETES,
        ),
        _case(
            "routing",
            2,
            "Routes weather to the weather tool",
            "What is the weather in Oslo?",
            _calls("get_weather"),
            {"kind": "tool_not_called", "tool": "calculator"},
            COMPLETES,
        ),
    ],
    "parallel": [
        _case(
            "parallel",
            1,
            "Reviews a boastful text",
            "Our new app is the best in the world, free forever, no catch, trust us!!!",
            COMPLETES,
            _at_most(4),
            ANSWERS,
        ),
        _case(
            "parallel",
            2,
            "Reviews a plain text",
            "Our shop opens at nine on weekdays and sells second-hand bicycles.",
            COMPLETES,
            _at_most(4),
            ANSWERS,
        ),
    ],
    "orchestrator": [
        _case(
            "orchestrator",
            1,
            "Plans a trip note",
            "A weekend trip note for Porto in autumn",
            COMPLETES,
            ANSWERS,
        ),
        _case(
            "orchestrator",
            2,
            "Plans a moving checklist",
            "A checklist for moving to a new flat",
            COMPLETES,
            ANSWERS,
        ),
    ],
    "evaluator": [
        _case(
            "evaluator",
            1,
            "Names the charger",
            "A solar-powered phone charger called SunSip",
            COMPLETES,
            _contains("SunSip"),
        ),
        _case(
            "evaluator",
            2,
            "Names the toothbrush",
            "A bamboo toothbrush called BrushRoot",
            COMPLETES,
            _contains("BrushRoot"),
        ),
    ],
}


def example(case_id: str) -> Case | None:
    return next((c for cases in EXAMPLES.values() for c in cases if c.case_id == case_id), None)
