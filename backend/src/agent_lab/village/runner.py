"""The village loop: ticks of four concurrent villager turns, applied together.

Every turn is an ordinary traced run of the villager's block agent; the village never calls the
model itself. One lock keeps ticks, Step, Reset and interval changes from overlapping.
"""

import asyncio
import copy
import time
from itertools import chain, count
from typing import Any

from pydantic import ValidationError

from agent_lab.blocks.model import LayoutError
from agent_lab.bus import Bus
from agent_lab.llm.models import Models, UnavailableModel
from agent_lab.runs import UnknownAgent, execute_run, new_run
from agent_lab.store import NameInUse, Store
from agent_lab.tracing.redact import redact
from agent_lab.village.turn import SPEECH_SHOWN, observation, parse_action, villager_agent
from agent_lab.village.world import (
    PLACES,
    ROWS,
    VILLAGERS,
    clock,
    label,
    label_cell,
    nearby,
    new_world,
    place_at,
    step_towards,
)

CHANNEL = "village"  # bus channel of the village stream
EVENTS_KEPT = 10
FAILED_TICKS_PAUSE = 3

Villager = dict[str, Any]


class StepConflict(Exception):
    """Step while the village runs or a tick is in progress."""


def _event(villager: Villager, tick: int, kind: str, text: str, **extra: Any) -> None:
    villager["events"] = [*villager["events"], {"tick": tick, "kind": kind, "text": text, **extra}][
        -EVENTS_KEPT:
    ]


class Village:
    def __init__(
        self,
        *,
        store: Store,
        models: Models,
        bus: Bus,
        secrets: tuple[str, ...] = (),
        idle_pause: float = 60.0,
    ) -> None:
        self.store, self.models, self.bus, self.secrets = store, models, bus, secrets
        self.world: dict[str, Any] = store.load_village() or new_world()
        self.world["running"] = False  # a restarted backend shows the world paused
        self.lock = asyncio.Lock()
        self.ticking = False
        self.task: asyncio.Task[None] | None = None
        self.idle_pause = idle_pause
        self.viewers = 0
        self.last_viewer_left = time.monotonic()

    # --- what the API and the stream show ---

    def state(self) -> dict[str, Any]:
        world = copy.deepcopy(self.world)
        day, hhmm, period = clock(world["tick"])
        for v in world["villagers"]:
            character = VILLAGERS[v["name"]]
            place = place_at(v["x"], v["y"])
            v |= {
                "title": character.title,
                "color": character.color,
                "initial": character.initial,
                "persona": character.persona,
                "place": place,
            }
            del v["inbox"]
        places = [
            {"key": key, "label": label(key), "x": label_cell(key)[0], "y": label_cell(key)[1]}
            for key in PLACES
        ]
        return {
            **world,
            "day": day,
            "time": hhmm,
            "period": period,
            "ticking": self.ticking,
            "map": {
                "width": len(ROWS[0]),
                "height": len(ROWS),
                "rows": list(ROWS),
                "places": places,
            },
        }

    def _publish(self) -> None:
        self.store.save_village(self.world)
        self.bus.publish(CHANNEL, {"type": "state", "state": self.state()})

    # --- villager agents ---

    def ensure_agents(self, *, recreate: bool = False) -> None:
        """Creates each villager's block agent; with `recreate` (Reset), also deleted ones.

        Without it a villager whose agent was deleted waits each tick until the owner resets.
        """
        for v in self.world["villagers"]:
            if v["agent_id"] and (not recreate or self.store.get_agent(v["agent_id"])):
                continue
            body = villager_agent(v["name"])
            fields = {k: body[k] for k in ("template_id", "description", "sample_prompt", "config")}
            title = body["name"]
            # The title, then "(village)", "(village 2)", … lazily, until one is free.
            names = chain(
                [title], (f"{title} (village{f' {n}' if n > 1 else ''})" for n in count(1))
            )
            for name in names:
                try:
                    v["agent_id"] = self.store.create_agent(name=name, **fields).agent_id
                    break
                except NameInUse:
                    continue
        self.store.save_village(self.world)

    # --- one tick ---

    async def _turn(
        self, v: Villager, prompt: str, tick: int
    ) -> tuple[str | None, dict[str, Any], str | None]:
        """(run id, action, reason it became wait) for one villager."""
        wait: dict[str, Any] = {"action": "wait"}
        try:
            run, config, spec, llm = new_run(
                prompt,
                v["agent_id"] or "",
                self.models,
                self.store,
                self.secrets,
                village_tick=tick,
                villager=v["name"],
            )
        except UnknownAgent:
            return None, wait, "turn failed: unknown agent"
        except (UnavailableModel, LayoutError, ValidationError) as exc:
            return None, wait, f"turn failed: {exc}"
        self.store.create_run(run)
        self.bus.publish(
            CHANNEL, {"type": "turn_started", "villager": v["name"], "run_id": run.run_id}
        )
        await execute_run(
            run=run,
            prompt=prompt,
            config=config,
            spec=spec,
            llm=llm,
            store=self.store,
            bus=self.bus,
            secrets=self.secrets,
        )
        done = self.store.get_run(run.run_id)
        if done is None or done.status != "completed":
            return run.run_id, wait, f"turn failed: run ended {done.status if done else 'missing'}"
        action, reason = parse_action(done.answer, self.world, v["name"])
        # Decoding JSON can undo redaction of the raw answer (e.g. "\u0073k-…"): redact again.
        return run.run_id, redact(action, self.secrets), redact(reason, self.secrets)

    async def tick(self) -> None:
        async with self.lock:
            self.ticking = True
            try:
                await self._tick()
            finally:
                self.ticking = False
            self._publish()  # after `ticking` is cleared, so the view does not stay "Ticking…"

    async def _tick(self) -> None:
        world = self.world
        tick, villagers = world["tick"], world["villagers"]
        self.bus.publish(CHANNEL, {"type": "tick_started", "tick": tick})
        prompts = [observation(world, v["name"]) for v in villagers]  # all from the same state
        turns = await asyncio.gather(
            *(self._turn(v, p, tick) for v, p in zip(villagers, prompts, strict=True))
        )

        speeches: list[tuple[Villager, dict[str, Any]]] = []
        for v, (_, action, reason) in zip(villagers, turns, strict=True):
            v["inbox"], v["speech"] = [], None  # what it heard was in this turn's observation
            v["last_action"] = {**action, **({"reason": reason} if reason else {})}
            if action["action"] == "move":
                if v["destination"] != action["place"]:
                    _event(v, tick, "set_off", f"You set off for the {label(action['place'])}.")
                v["destination"] = action["place"]
            elif action["action"] == "wait":  # a walk goes on until arrival (FR-009)
                _event(v, tick, "waited", f"You waited: {reason}." if reason else "You waited.")
            else:
                speeches.append((v, action))
        for v in villagers:  # moves first, so speech reaches whoever is nearby afterwards
            if v["destination"]:
                v["x"], v["y"] = step_towards(v["x"], v["y"], v["destination"])
                if place_at(v["x"], v["y"]) == v["destination"]:
                    _event(v, tick, "arrived", f"You arrived at the {label(v['destination'])}.")
                    v["destination"] = None
        for speaker, action in speeches:
            text, to = action["text"][:SPEECH_SHOWN], action["to"]
            speaker["speech"] = {"text": text, "to": to}
            said_to = f" to {to}" if to else ""
            _event(speaker, tick, "said", f'You said{said_to}: "{text}"', to=to)
            for hearer in villagers:
                if hearer is speaker or not nearby(
                    (speaker["x"], speaker["y"]), (hearer["x"], hearer["y"])
                ):
                    continue
                entry = {"from": speaker["name"], "to": to, "text": text, "tick": tick}
                hearer["inbox"].append(entry)
                heard_to = f" to {'you' if to == hearer['name'] else to}" if to else ""
                _event(
                    hearer,
                    tick,
                    "heard",
                    f'{speaker["name"]}{heard_to}: "{text}"',
                    **{"from": speaker["name"], "to": to},
                )
        for run_id, action, reason in turns:
            if run_id:
                self.store.set_village_action(
                    run_id, {**action, **({"reason": reason} if reason else {})}
                )

        all_failed = all(reason and reason.startswith("turn failed") for _, _, reason in turns)
        world["failed_ticks"] = world["failed_ticks"] + 1 if all_failed else 0
        world["tick"] = tick + 1

    # --- controls ---

    async def _loop(self) -> None:
        while self.world["running"]:
            started = time.monotonic()
            if self.viewers == 0 and started - self.last_viewer_left >= self.idle_pause:
                self.pause(f"no viewer for {self.idle_pause:g} s")
                break
            await self.tick()
            if self.world["failed_ticks"] >= FAILED_TICKS_PAUSE:
                self.pause(f"every turn failed {FAILED_TICKS_PAUSE} ticks in a row")
                break
            await asyncio.sleep(max(0.0, self.world["interval"] - (time.monotonic() - started)))

    def start(self) -> None:
        if self.world["running"]:
            return
        self.ensure_agents()
        self.world |= {"running": True, "paused_reason": None, "failed_ticks": 0}
        self._publish()
        if self.task is None or self.task.done():  # a loop that is still sleeping just continues
            self.task = asyncio.create_task(self._loop())

    def pause(self, reason: str = "owner") -> None:
        self.world |= {"running": False, "paused_reason": reason}
        self._publish()

    async def step(self) -> None:
        if self.world["running"] or self.lock.locked():
            raise StepConflict
        self.ensure_agents()
        await self.tick()

    async def set_interval(self, seconds: int) -> None:
        async with self.lock:
            self.world["interval"] = seconds
            self._publish()

    async def reset(self) -> None:
        async with self.lock:  # waits for a tick in progress
            agents = {v["name"]: v["agent_id"] for v in self.world["villagers"]}
            self.world = new_world()
            for v in self.world["villagers"]:
                v["agent_id"] = agents.get(v["name"])
            self.ensure_agents(recreate=True)
            self._publish()

    def viewer_joined(self) -> None:
        self.viewers += 1

    def viewer_left(self) -> None:
        self.viewers -= 1
        if self.viewers == 0:
            self.last_viewer_left = time.monotonic()
