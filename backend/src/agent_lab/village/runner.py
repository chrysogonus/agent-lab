"""The village loop: 10-minute steps that move the clock and the walkers, and decisions that
each villager takes on its own when something happens (specs/007-village-life/research.md).

Every decision is an ordinary traced run of the villager's block agent; the village never calls
the model itself. Steps hold one lock; decisions apply on the event loop without awaiting in
between, so they need none.
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
from agent_lab.village.memory import (
    LEARNINGS_KEPT,
    parse_reflection,
    reflection_agent,
    reflection_prompt,
    remember,
    unreflected,
)
from agent_lab.village.turn import (
    SPEECH_SHOWN,
    awake_neighbours,
    belief_text,
    cell,
    goal_text,
    heard_places,
    observation,
    parse_action,
    partners,
    villager_agent,
)
from agent_lab.village.world import (
    HEIGHT,
    HOMES,
    PLACES,
    ROWS,
    VERSION,
    VILLAGERS,
    WIDTH,
    adjacent,
    awake_at,
    clock,
    door,
    hhmm,
    label,
    label_cell,
    minute_of_day,
    new_world,
    place_at,
    place_cells,
    sees,
    step_towards,
    upgrade,
    usual_place,
)

CHANNEL = "village"  # bus channel of the village stream
EVENTS_KEPT = 10
LOG_KEPT = 8
FAILED_TICKS_PAUSE = 3
IDLE_STEPS = 3  # an idle villager decides again after 30 village minutes
SILENT_STEPS = 3  # a conversation without a line for this long ends
CONVERSATION_LINES = 10
NIGHT_STEP = 0.2  # seconds per step while everyone sleeps
STEP_GAP = 0.25  # seconds between moves in a Step
FRESH_START = "the village moved to a bigger map and started fresh"

Villager = dict[str, Any]


class StepConflict(Exception):
    """Step while the village runs or a step is in progress."""


class Village:
    def __init__(
        self,
        *,
        store: Store,
        models: Models,
        bus: Bus,
        secrets: tuple[str, ...] = (),
        idle_pause: float = 60.0,
        move_gap: float | None = None,
    ) -> None:
        self.store, self.models, self.bus, self.secrets = store, models, bus, secrets
        self.world = self._load()
        self.world["running"] = False  # a restarted backend shows the world paused
        self.lock = asyncio.Lock()
        self.ticking = False
        self.task: asyncio.Task[None] | None = None
        self.decisions: dict[str, asyncio.Task[None]] = {}
        self.reflections: dict[str, asyncio.Task[None]] = {}  # never count as decisions
        self.outcomes: list[bool] = []  # decisions finished since the last step: succeeded?
        self.in_step = False  # inside Step: its own decisions may start while paused
        self.resetting = False
        self.idle_pause = idle_pause
        self.move_gap = move_gap
        self.viewers = 0
        self.last_viewer_left = time.monotonic()

    def _load(self) -> dict[str, Any]:
        stored = self.store.load_village()
        if stored and stored.get("version") == VERSION:
            return stored
        if stored and stored.get("version") == 2:  # an M7 world keeps going, memory empty
            world = upgrade(stored)
            self.store.save_village(world)
            return world
        world = new_world()
        if stored:  # an M6 world: start fresh, but keep (and update) the villagers' agents
            world["paused_reason"] = FRESH_START
            agents = {v["name"]: v.get("agent_id") for v in stored.get("villagers", [])}
            for v in world["villagers"]:
                agent = self.store.get_agent(agents.get(v["name"]) or "")
                if agent is None:
                    continue
                body = villager_agent(v["name"])
                model = {"model": agent.config["model"]} if "model" in agent.config else {}
                self.store.update_agent(
                    agent.agent_id,
                    name=agent.name,
                    description=body["description"],
                    sample_prompt=body["sample_prompt"],
                    config={**body["config"], **model},
                )
                v["agent_id"] = agent.agent_id
            self.store.save_village(world)
        return world

    # --- what the API and the stream show ---

    def _villager(self, name: str) -> Villager:
        return next(v for v in self.world["villagers"] if v["name"] == name)

    def _state_of(self, v: Villager) -> str:
        if v["asleep"]:
            return "asleep"
        if v["bedtime"]:
            return "bedtime"
        if v["name"] in self.decisions:
            return "deciding"
        if partners(self.world, v["name"]):
            return "talking"
        return "walking" if v["goal"] else "idle"

    def state(self) -> dict[str, Any]:
        world = copy.deepcopy(self.world)
        day, hhmm_now, period = clock(world["tick"])
        for v in world["villagers"]:
            name = v["name"]
            character = VILLAGERS[name]
            goal = v["goal"]
            v |= {
                "title": character.title,
                "color": character.color,
                "initial": character.initial,
                "persona": character.persona,
                "place": place_at(v["x"], v["y"]),
                "destination": goal["place"] if goal and goal["kind"] == "place" else None,
                "state": self._state_of(self._villager(name)),
                "wake": hhmm(character.wake),
                "bed": hhmm(character.bed),
                "goal": goal_text(goal),
                "talking_with": partners(self.world, name),
                "beliefs": [
                    {
                        "villager": o,
                        "text": belief_text(self.world, name, o),
                        "view": v["views"][o]["text"] if o in v["views"] else None,
                    }
                    for o in VILLAGERS
                    if o != name
                ],
                "learnings": [
                    {"day": clock(item["tick"])[0], "text": item["text"]} for item in v["learnings"]
                ],
                "views": [
                    {"villager": o, "text": view["text"], "day": clock(view["tick"])[0]}
                    for o, view in v["views"].items()
                ],
                "memories": [
                    {
                        "day": clock(m["tick"])[0],
                        "time": clock(m["tick"])[1],
                        "kind": m["kind"],
                        "text": m["text"],
                    }
                    for m in reversed(v["memories"])
                ],
            }
            for internal in ("inbox", "triggers", "neighbours", "last_decided"):
                del v[internal]
        for internal in ("conversations", "talked_out", "version", "reflection_agent_id"):
            del world[internal]
        return {
            **world,
            "day": day,
            "time": hhmm_now,
            "period": period,
            "ticking": self.ticking,
            "log": [{**line, "time": clock(line["tick"])[1]} for line in world["log"]],
            "map": {
                "width": WIDTH,
                "height": HEIGHT,
                "rows": list(ROWS),
                "places": [
                    {"key": k, "label": label(k), "x": label_cell(k)[0], "y": label_cell(k)[1]}
                    for k in PLACES
                ],
                "homes": [
                    {"villager": n, "letter": letter, "door": list(door(n))}
                    for n, letter in HOMES.items()
                ],
            },
        }

    def _publish(self) -> None:
        self.store.save_village(self.world)
        self.bus.publish(CHANNEL, {"type": "state", "state": self.state()})

    # --- villager agents ---

    def ensure_agents(self, *, recreate: bool = False) -> None:
        """Creates each villager's block agent and the shared reflection agent; with `recreate`
        (Reset), also deleted ones.

        Without it a villager whose agent was deleted waits until the owner resets.
        """

        def missing(agent_id: str | None) -> bool:
            return not agent_id or (recreate and self.store.get_agent(agent_id) is None)

        for v in self.world["villagers"]:
            if missing(v["agent_id"]):
                v["agent_id"] = self._create_agent(villager_agent(v["name"]))
        if missing(self.world["reflection_agent_id"]):
            self.world["reflection_agent_id"] = self._create_agent(reflection_agent())
        self.store.save_village(self.world)

    def _create_agent(self, body: dict[str, Any]) -> str:
        fields = {k: body[k] for k in ("template_id", "description", "sample_prompt", "config")}
        title = body["name"]
        # The title, then "(village)", "(village 2)", … lazily, until one is free.
        names = chain([title], (f"{title} (village{f' {n}' if n > 1 else ''})" for n in count(1)))
        for name in names:
            try:
                return self.store.create_agent(name=name, **fields).agent_id
            except NameInUse:
                continue
        raise AssertionError("unreachable: the names never run out")

    # --- world changes ---

    def _event(self, v: Villager, kind: str, text: str, **extra: Any) -> None:
        entry = {"tick": self.world["tick"], "kind": kind, "text": text, **extra}
        v["events"] = [*v["events"], entry][-EVENTS_KEPT:]

    def _trigger(self, v: Villager, reason: str) -> None:
        if reason not in v["triggers"]:
            v["triggers"].append(reason)

    def _end_conversations(self, name: str, reason: str) -> None:
        for c in [c for c in self.world["conversations"] if name in (c["a"], c["b"])]:
            self._end_conversation(c, reason)

    def _end_conversation(self, c: dict[str, Any], reason: str) -> None:
        self.world["conversations"].remove(c)
        transcript = " / ".join(c.get("transcript", []))
        for me, other in ((c["a"], c["b"]), (c["b"], c["a"])):
            v = self._villager(me)
            self._event(v, "ended", f"Your conversation with {other} ended: {reason}.", to=other)
            self._trigger(v, "conversation ended")
            self._remember(v, "conversation", f"Talked with {other}: {transcript}", [other])

    def _remember(self, v: Villager, kind: str, text: str, about: list[str]) -> None:
        remember(v, self.world["tick"], kind, text, about, place_at(v["x"], v["y"]))

    def _fall_asleep(self, v: Villager) -> None:
        v |= {"asleep": True, "bedtime": False, "goal": None, "triggers": [], "neighbours": []}
        self._event(v, "slept", "You went to bed.")
        if unreflected(v["memories"]) and not self.resetting:
            self._start_reflection(v["name"])

    def _schedule(self, v: Villager, minute: int) -> None:
        """Wakes a villager at its wake-up time and sends it home to bed at its bedtime."""
        name = v["name"]
        awake = awake_at(name, minute)
        if v["asleep"]:
            if awake:
                v |= {"asleep": False, "beliefs": {}}  # a new day: yesterday's sightings are old
                self._event(v, "woke", "You woke up at home.")
                self._trigger(v, "woke")
            return
        if not awake and not v["bedtime"]:
            v |= {"bedtime": True, "goal": {"kind": "home"}, "triggers": []}
            self._end_conversations(name, f"{name} went home to bed")
            self._event(v, "bedtime", "It is your bedtime; you head home.")
        if v["bedtime"] and cell(v) == door(name):
            self._fall_asleep(v)

    def _walks(self, v: Villager) -> bool:
        if v["asleep"] or not v["goal"]:
            return False
        if v["bedtime"]:
            return True
        return v["name"] not in self.decisions and not partners(self.world, v["name"])

    def _targets(self, v: Villager) -> list[tuple[int, int]]:
        goal = v["goal"]
        if goal["kind"] == "place":
            return place_cells(goal["place"])
        if goal["kind"] == "home":
            return [door(v["name"])]
        return [(x, y) for x, y in goal["target"]]

    def _walk(self, v: Villager) -> None:
        targets = self._targets(v)
        v["x"], v["y"] = step_towards(v["x"], v["y"], targets)
        goal = v["goal"]
        if goal["kind"] == "find" or cell(v) not in targets:
            return  # finds end in _look: found next to them, or missed at the target
        if v["bedtime"]:
            self._fall_asleep(v)
            return
        v["goal"] = None
        where = f"the {label(goal['place'])}" if goal["kind"] == "place" else "your home"
        self._event(v, "arrived", f"You arrived at {where}.")
        self._trigger(v, "arrived")

    def _look(self) -> None:
        """Sightings, new neighbours and searches, after anything moved."""
        tick = self.world["tick"]
        awake = [v for v in self.world["villagers"] if not v["asleep"]]
        for v in awake:
            for o in awake:
                if o is not v and sees(cell(v), cell(o)):
                    v["beliefs"][o["name"]] = {
                        "where": place_at(o["x"], o["y"]),
                        "cell": [o["x"], o["y"]],
                        "tick": tick,
                        "source": "seen",
                    }
            now = sorted(o["name"] for o in awake if o is not v and adjacent(cell(v), cell(o)))
            for name in now:
                if name not in v["neighbours"]:
                    self._event(v, "met", f"{VILLAGERS[name].title} is next to you.", to=name)
                    self._trigger(v, "met")
                    day = clock(tick)[0]
                    if not any(
                        m["kind"] == "met" and m["about"] == [name] and clock(m["tick"])[0] == day
                        for m in v["memories"]
                    ):  # the first meeting of the day
                        self._remember(v, "met", f"You met {VILLAGERS[name].title}.", [name])
            v["neighbours"] = now
        for v in awake:
            goal = v["goal"]
            if not goal or goal["kind"] != "find":
                continue
            other = self._villager(goal["villager"])
            if not other["asleep"] and adjacent(cell(v), cell(other)):
                v["goal"] = None
                self._event(v, "found", f"You found {other['name']}.", to=other["name"])
                self._trigger(v, "found")
                self._remember(v, "found", f"You found {other['name']}.", [other["name"]])
            elif not other["asleep"] and sees(cell(v), cell(other)):
                goal["target"] = [[other["x"], other["y"]]]
            elif cell(v) in self._targets(v):
                why = (
                    f"{other['name']} is asleep at home"
                    if other["asleep"] and cell(v) == door(other["name"])
                    else f"{other['name']} is not here"
                )
                v["goal"] = None
                self._event(v, "missed", f"You did not find {other['name']}: {why}.")
                self._trigger(v, "missed")
                self._remember(
                    v, "missed", f"You did not find {other['name']}: {why}.", [other["name"]]
                )

    def _upkeep(self) -> None:
        """Ends conversations whose villagers are apart or silent; forgets talked-out pairs."""
        tick = self.world["tick"]
        for c in list(self.world["conversations"]):
            a, b = self._villager(c["a"]), self._villager(c["b"])
            if not adjacent(cell(a), cell(b)):
                self._end_conversation(c, "you walked apart")
            elif tick - c["last_tick"] >= SILENT_STEPS:
                self._end_conversation(c, "it fell silent")
        self.world["talked_out"] = [
            pair
            for pair in self.world["talked_out"]
            if adjacent(cell(self._villager(pair[0])), cell(self._villager(pair[1])))
        ]

    # --- decisions ---

    def _due(self, v: Villager) -> bool:
        if v["asleep"] or v["bedtime"] or v["name"] in self.decisions:
            return False
        idle = v["goal"] is None and self.world["tick"] - v["last_decided"] >= IDLE_STEPS
        return bool(v["triggers"]) or idle

    def _start_decisions(self, *, force: bool = False) -> None:
        if self.resetting or not (self.world["running"] or force):
            return
        for v in self.world["villagers"]:
            if self._due(v):
                self.decisions[v["name"]] = asyncio.create_task(self._decide(v["name"]))

    async def _run(
        self, agent_id: str | None, name: str, prompt: str, tick: int
    ) -> tuple[str | None, str | None, str | None]:
        """(run id, answer, why it failed) for one run of a village agent for `name`."""
        try:
            run, config, spec, llm = new_run(
                prompt,
                agent_id or "",
                self.models,
                self.store,
                self.secrets,
                village_tick=tick,
                villager=name,
            )
        except UnknownAgent:
            return None, None, "turn failed: unknown agent"
        except (UnavailableModel, LayoutError, ValidationError) as exc:
            return None, None, f"turn failed: {exc}"
        self.store.create_run(run)
        self.bus.publish(
            CHANNEL, {"type": "decision_started", "villager": name, "run_id": run.run_id}
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
            return run.run_id, None, f"turn failed: run ended {done.status if done else 'missing'}"
        return run.run_id, done.answer, None

    async def _turn(
        self, v: Villager, prompt: str, tick: int
    ) -> tuple[str | None, dict[str, Any], str | None]:
        """(run id, action, reason it became wait) for one decision."""
        run_id, answer, failed = await self._run(v["agent_id"], v["name"], prompt, tick)
        if failed:
            return run_id, {"action": "wait"}, failed
        # Parsed against the world as it is now, when the answer is applied.
        action, reason = parse_action(answer, self.world, v["name"])
        # Decoding JSON can undo redaction of the raw answer (e.g. "\u0073k-…"): redact again.
        return run_id, redact(action, self.secrets), redact(reason, self.secrets)

    def _start_reflection(self, name: str) -> None:
        previous = self.reflections.get(name)  # one villager's reflections never overlap
        self.reflections[name] = asyncio.create_task(self._reflect(name, previous))

    async def _reflect(self, name: str, previous: asyncio.Task[None] | None) -> None:
        if previous:
            await asyncio.gather(previous, return_exceptions=True)
        tick = self.world["tick"]
        prompt = reflection_prompt(self._villager(name), tick)
        try:
            run_id, answer, failed = await self._run(
                self.world["reflection_agent_id"], name, prompt, tick
            )
        finally:
            if self.reflections.get(name) is asyncio.current_task():
                del self.reflections[name]
        if self.resetting:
            return
        result, reason = (None, failed) if failed else parse_reflection(answer, name)
        result, reason = redact(result, self.secrets), redact(reason, self.secrets)
        v = self._villager(name)
        if result:
            for text in result["learnings"]:
                v["learnings"] = [*v["learnings"], {"tick": tick, "text": text}][-LEARNINGS_KEPT:]
            for other, text in result["views"].items():
                v["views"][other] = {"tick": tick, "text": text}
            text = f"You looked back on your day: {' '.join(result['learnings']) or 'nothing new'}"
            self._remember(v, "reflection", text, list(result["views"]))
            self._event(v, "reflected", text)
        action = {"action": "reflect", **(result or {"reason": reason})}
        if run_id:
            self.store.set_village_action(run_id, action)
        self._publish()

    async def _decide(self, name: str) -> None:
        v = self._villager(name)
        tick = self.world["tick"]
        prompt = observation(self.world, name)
        v |= {"triggers": [], "inbox": [], "last_decided": tick}  # all of it is in the prompt
        try:
            run_id, action, reason = await self._turn(v, prompt, tick)
        finally:
            self.decisions.pop(name, None)
        self.outcomes.append(not (reason and reason.startswith("turn failed")))
        if self.resetting:
            return
        v = self._villager(name)
        if v["asleep"] or v["bedtime"]:
            action, reason = {"action": "wait"}, reason or "it was already your bedtime"
        self._apply(v, action, reason)
        if run_id:
            self.store.set_village_action(
                run_id, {**action, **({"reason": reason} if reason else {})}
            )
        self._start_decisions()  # e.g. whoever was just spoken to
        self._publish()

    def _apply(self, v: Villager, action: dict[str, Any], reason: str | None) -> None:
        name = v["name"]
        v["last_action"] = {**action, **({"reason": reason} if reason else {})}
        kind = action["action"]
        if kind == "wait":
            self._event(v, "waited", f"You waited: {reason}." if reason else "You waited.")
        elif kind == "move":
            self._end_conversations(name, f"{name} walked away")
            if action["place"] == "home":
                v["goal"] = {"kind": "home"}
                self._event(v, "set_off", "You set off for home.")
            else:
                v["goal"] = {"kind": "place", "place": action["place"]}
                self._event(v, "set_off", f"You set off for the {label(action['place'])}.")
        elif kind == "find":
            other = action["villager"]
            self._end_conversations(name, f"{name} walked away")
            v["goal"] = {"kind": "find", "villager": other, "target": self._find_target(v, other)}
            self._event(v, "set_off", f"You set off to find {other}.", to=other)
            self._look()  # already in sight: aim at them now
        elif kind == "say":
            self._say(v, action["text"], action["to"])
        else:  # goodbye
            if action["text"] and awake_neighbours(self.world, name):
                self._say(v, action["text"], None)
            self._end_conversations(name, f"{name} said goodbye")
            if not action["text"]:
                self._event(v, "said", "You said goodbye.")

    def _find_target(self, v: Villager, other: str) -> list[list[int]]:
        belief = v["beliefs"].get(other)
        where = belief["where"] if belief else usual_place(other, minute_of_day(self.world["tick"]))
        if belief and belief["source"] == "seen":
            return [belief["cell"]]
        if where == "home":
            return [list(door(other))]
        if where is None:
            return [belief["cell"]] if belief else [list(door(other))]
        return [[x, y] for x, y in place_cells(where)]

    def _say(self, v: Villager, text: str, to: str | None) -> None:
        name, tick = v["name"], self.world["tick"]
        text = text[:SPEECH_SHOWN]
        hearers = [to] if to else awake_neighbours(self.world, name)
        hearers = [h for h in hearers if sorted([name, h]) not in self.world["talked_out"]]
        v["speech"] = {"text": text, "to": to, "tick": tick}
        said_to = f" to {to}" if to else ""
        self._event(v, "said", f'You said{said_to}: "{text}"', to=to)
        self.world["log"] = [
            *self.world["log"],
            {"tick": tick, "from": name, "to": to, "text": text},
        ][-LOG_KEPT:]
        for h in hearers:
            hearer = self._villager(h)
            hearer["inbox"].append({"from": name, "to": to, "text": text, "tick": tick})
            heard_to = f" to {'you' if to == h else to}" if to else ""
            self._event(hearer, "heard", f'{name}{heard_to}: "{text}"', **{"from": name, "to": to})
            self._trigger(hearer, "spoken to")
            for other, where in heard_places(text, name, h).items():
                hearer["beliefs"][other] = {
                    "where": where,
                    "cell": list(door(other)) if where == "home" else list(label_cell(where)),
                    "tick": tick,
                    "source": "heard",
                    "from": name,
                }
            self._add_line(name, h, text)

    def _add_line(self, a: str, b: str, text: str) -> None:
        conversation: dict[str, Any] | None = next(
            (c for c in self.world["conversations"] if {c["a"], c["b"]} == {a, b}), None
        )
        if conversation is None:
            conversation = {
                "a": a,
                "b": b,
                "lines": 0,
                "last_tick": self.world["tick"],
                "transcript": [],
            }
            self.world["conversations"].append(conversation)
        conversation["lines"] += 1
        conversation["transcript"].append(f"{a}: {text}")
        conversation["last_tick"] = self.world["tick"]
        if conversation["lines"] >= CONVERSATION_LINES:
            self._end_conversation(conversation, "you talked a long time")
            self.world["talked_out"].append(sorted([a, b]))

    async def _settle(self) -> None:
        """Waits until no decision or reflection is in flight."""
        while self.decisions or self.reflections:
            tasks = [*self.decisions.values(), *self.reflections.values()]
            await asyncio.gather(*tasks, return_exceptions=True)

    # --- one step ---

    async def _step(self) -> None:
        async with self.lock:
            self.ticking = True
            try:
                await self._advance()
            finally:
                self.ticking = False
            self._publish()  # after `ticking` is cleared, so the view does not stay "Ticking…"

    async def _advance(self) -> None:
        world = self.world
        for v in world["villagers"]:  # a line stays on the map for about one step
            if v["speech"] and v["speech"]["tick"] < world["tick"]:
                v["speech"] = None
        world["tick"] += 1
        minute = minute_of_day(world["tick"])
        for v in world["villagers"]:
            self._schedule(v, minute)
        names = list(VILLAGERS)
        walkers = sorted(
            (v for v in world["villagers"] if self._walks(v)),
            key=lambda v: (names.index(v["name"]) - world["tick"]) % len(names),
        )
        gap = self.move_gap
        if gap is None:
            gap = STEP_GAP if self.in_step else world["interval"] / (len(walkers) + 1)
        for i, v in enumerate(walkers):  # one at a time, so the view shows them walk in turn
            if i and gap:
                await asyncio.sleep(gap)
            if self._walks(v):  # a decision may have stopped it meanwhile
                self._walk(v)
                self._look()
                self._publish()
        self._look()
        self._upkeep()
        if self.outcomes:
            all_failed = not any(self.outcomes)
            world["failed_ticks"] = world["failed_ticks"] + 1 if all_failed else 0
            self.outcomes = []
        self._start_decisions(force=self.in_step)

    # --- controls ---

    async def _loop(self) -> None:
        while self.world["running"]:
            started = time.monotonic()
            if self.viewers == 0 and started - self.last_viewer_left >= self.idle_pause:
                self.pause(f"no viewer for {self.idle_pause:g} s")
                break
            await self._step()
            if self.world["failed_ticks"] >= FAILED_TICKS_PAUSE:
                self.pause(f"every decision failed {FAILED_TICKS_PAUSE} steps in a row")
                break
            asleep = all(v["asleep"] for v in self.world["villagers"])
            wait = NIGHT_STEP if asleep else self.world["interval"]
            await asyncio.sleep(max(0.0, wait - (time.monotonic() - started)))

    def start(self) -> None:
        if self.world["running"]:
            return
        self.ensure_agents()
        self.world |= {"running": True, "paused_reason": None, "failed_ticks": 0}
        self._publish()
        self._start_decisions()  # whoever is due since the last pause
        if self.task is None or self.task.done():  # a loop that is still sleeping just continues
            self.task = asyncio.create_task(self._loop())

    def pause(self, reason: str = "owner") -> None:
        self.world |= {"running": False, "paused_reason": reason}
        self._publish()

    async def step(self) -> None:
        """One step and the decisions it starts; decisions those trigger wait for the next."""
        if self.world["running"] or self.lock.locked() or self.in_step:
            raise StepConflict
        self.ensure_agents()
        self.in_step = True
        try:
            await self._step()
            await self._settle()
        finally:
            self.in_step = False
        self._publish()

    async def set_interval(self, seconds: int) -> None:
        async with self.lock:
            self.world["interval"] = seconds
            self._publish()

    async def reset(self) -> None:
        async with self.lock:  # waits for a step in progress
            self.resetting = True
            try:
                await self._settle()  # decisions in flight finish; their results are dropped
            finally:
                self.resetting = False
            agents = {v["name"]: v["agent_id"] for v in self.world["villagers"]}
            reflection_agent_id = self.world["reflection_agent_id"]
            self.world = new_world() | {"reflection_agent_id": reflection_agent_id}
            self.outcomes = []
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
