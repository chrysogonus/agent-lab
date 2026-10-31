"""The six templates as block layouts: "Open as blocks" (research.md §7).

The layouts keep each agent's prompts and settings and the template's node ids; requests are
not byte-identical, but on the same script a converted agent reaches the same status, answer,
call counts and taken edges.
"""

from typing import Any

from pydantic import BaseModel

from agent_lab.agents.config_fields import BLOCK_RESERVED
from agent_lab.workflows import orchestrator

Blocks = list[dict[str, Any]]


class Names:
    """Hands out block names: a wanted name, or `<name>-<n>` when it is taken or reserved."""

    def __init__(self, fixed: set[str]) -> None:
        self.taken = set(fixed)  # names the conversion itself adds

    def __call__(self, wanted: str) -> str:
        name, n = wanted, 2
        while name in self.taken or name in BLOCK_RESERVED:
            name, n = f"{wanted}-{n}", n + 1
        self.taken.add(name)
        return name


def model(name: str, system: str, message: str = "{previous}", **fields: Any) -> dict[str, Any]:
    return {"kind": "model", "name": name, "system": system, "message": message, **fields}


def _chain(c: dict[str, Any]) -> Blocks:
    name = Names(set())
    blocks: Blocks = []
    previous = ""
    for i, step in enumerate(c["steps"]):
        own = name(step["name"])
        message = "{previous}"
        if i and step["include_input"]:
            message = f"{c['input_label']}: {{input}}\n\n{previous.capitalize()}:\n{{previous}}"
        blocks.append(model(own, step["prompt"], message))
        if i == 0 and c["gate"] and len(c["steps"]) > 1:
            blocks.append(
                {
                    "kind": "check",
                    "name": "gate",
                    "rule": "min_bullets",
                    "value": c["gate_min_bullets"],
                }
            )
        previous = step["name"]  # the message labels the step as the template does
    return blocks


def _routing(c: dict[str, Any]) -> Blocks:
    name = Names({"router"})
    routes: list[dict[str, Any]] = []
    route_names: dict[str, str] = {}
    for route in c["routes"]:
        own = name(route["name"])
        route_names[route["name"]] = own
        tools = [route["tool"]] if route["tool"] else []
        handler = model(own, route["prompt"], tools=tools, max_iterations=2)  # tool, then answer
        routes.append({"name": own, "description": route["description"], "blocks": [handler]})
    router = {"kind": "router", "name": "router", "prompt": c["router_prompt"], "routes": routes}
    return [{**router, "fallback": route_names[c["fallback"]]}]


def _parallel(c: dict[str, Any]) -> Blocks:
    aspects: dict[str, str] = c["aspects"]
    name = Names({"merge"} | ({"reviews"} if "reviews" not in aspects else set()))
    branches: Blocks = []
    for aspect, focus in aspects.items():
        own = name(aspect)
        system = c["review_prompt"].replace("{aspect}", aspect).replace("{focus}", focus)
        branches.append({"name": own, "blocks": [model(own, system)]})
    group = name("reviews")
    return [
        {"kind": "parallel", "name": group, "mode": "branches", "branches": branches},
        model("merge", c["merge_prompt"], f"Text:\n{{input}}\n\n{{{group}}}"),
    ]


def _orchestrator(config: orchestrator.Config, c: dict[str, Any]) -> Blocks:
    worker = model("worker", c["worker_prompt"], "Request: {input}\n\nSubtask: {item}")
    group = {
        "kind": "parallel",
        "name": "orchestrator",
        "mode": "per_item",
        "planner": orchestrator.orchestrator_system(config),  # the subtask range filled in
        "max_items": c["max_subtasks"],
        "body": [worker],
    }
    return [
        group,
        model("synthesizer", c["synthesizer_prompt"], "Request: {input}\n\n{orchestrator}"),
    ]


def to_blocks(template_id: str, config: BaseModel) -> dict[str, Any]:
    """`{reasoning, blocks}` for a template or template-based agent's validated config."""
    c = config.model_dump()
    if template_id == "react":
        blocks = [
            model(
                "llm",
                c["system_prompt"],
                tools=c["tools"],
                max_iterations=c["max_iterations"],
            )
        ]
    elif template_id == "chain":
        blocks = _chain(c)
    elif template_id == "routing":
        blocks = _routing(c)
    elif template_id == "parallel":
        blocks = _parallel(c)
    elif template_id == "orchestrator":
        assert isinstance(config, orchestrator.Config)
        blocks = _orchestrator(config, c)
    elif template_id == "evaluator":
        generator = model("generator", c["generator_prompt"], "{input}\n\n{feedback}")
        blocks = [
            {
                "kind": "loop",
                "name": "evaluator",
                "body": [generator],
                "exit": "judge",
                "judge": c["evaluator_prompt"],
                "max_rounds": c["max_rounds"],
            }
        ]
    else:
        raise ValueError(f"not a template: {template_id!r}")
    return {"reasoning": c["reasoning"], "blocks": blocks}
