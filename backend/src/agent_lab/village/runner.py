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
from agent_lab.village.chronicle import (
    CHRONICLE_KEPT,
    chronicle_prompt,
    chronicler_agent,
    parse_entry,
)
from agent_lab.village.memory import (
    LEARNINGS_KEPT,
    parse_reflection,
    reflection_agent,
    reflection_prompt,
    remember,
    unreflected,
)
from agent_lab.village.plan import (
    REVISIONS,
    entry_text,
    marks,
    parse_plan,
    plan_prompt,
    planner_agent,
)
from agent_lab.village.seasons import (
    dark,
    date,
    end_day,
    festival_in,
    neglected,
    sky,
    snow_cover,
    weather,
)
from agent_lab.village.turn import (
    OLD_RULES,
    RULES,
    SAID_KEPT,
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
    FESTIVAL_EVENING,
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
PLAN_TALK_LINES = 4  # a conversation this long ends with both revising their plans
NIGHT_STEP = 0.2  # seconds per step while everyone sleeps
STEP_GAP = 0.1  # seconds between moves in a Step
CELLS_PER_STEP = 3  # how far a villager walks in 10 village minutes
RECORD_ITEMS = 120  # happenings kept for the chronicle of one day
RECORD_TEXT = 300
FRESH_START = "the village moved to a bigger map and started fresh"
FESTIVAL_BEGINS = (
    "The harvest festival has begun on the square; the whole village is expected there"
)

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
        self._refresh_rules()
        self.lock = asyncio.Lock()
        self.ticking = False
        self.task: asyncio.Task[None] | None = None
        self.decisions: dict[str, asyncio.Task[None]] = {}
        self.reflections: dict[str, asyncio.Task[None]] = {}  # never count as decisions
        self.chronicle: asyncio.Task[None] | None = None  # nor does the chronicle
        self.plans: dict[str, asyncio.Task[None]] = {}  # nor do plans
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
        if stored and stored.get("version") in (2, 3, 4):  # an M7 to M10 world keeps going
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

    def _refresh_rules(self) -> None:
        """Villager agents still holding an earlier rules text verbatim get the current one;
        the owner's edits to the rules are left alone."""
        for v in self.world["villagers"]:
            agent = self.store.get_agent(v["agent_id"] or "")
            if agent is None:
                continue
            blocks: list[dict[str, Any]] = agent.config.get("blocks") or []
            system: str = blocks[0].get("system", "") if blocks else ""
            old = next((rules for rules in OLD_RULES if rules in system), None)
            if old is None:
                continue
            first = {**blocks[0], "system": system.replace(old, RULES)}
            self.store.update_agent(
                agent.agent_id,
                name=agent.name,
                description=agent.description,
                sample_prompt=agent.sample_prompt,
                config={**agent.config, "blocks": [first, *blocks[1:]]},
            )

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
                "work": character.work,
                "state": self._state_of(self._villager(name)),
                "wake": hhmm(character.wake),
                "bed": hhmm(character.bed),
                "goal": goal_text(goal),
                "plan": self._plan_state(v["plan"], day, minute_of_day(world["tick"])),
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
            for internal in ("inbox", "triggers", "neighbours", "last_decided", "said"):
                del v[internal]
        internals = ("conversations", "talked_out", "version", "reflection_agent_id")
        internals += ("tended", "day_record", "festival", "chronicler_agent_id")
        internals += ("harvest", "planner_agent_id")
        for internal in internals:
            del world[internal]
        year, season, day_of_season = date(day)
        minute = minute_of_day(world["tick"])
        growth = world["growth"]
        return {
            **world,
            "day": day,
            "time": hhmm_now,
            "period": period,
            "calendar": {
                "year": year,
                "season": season,
                "day_of_season": day_of_season,
                "festival_in": festival_in(day),
            },
            "weather": weather(day),
            "snow_cover": snow_cover(day),
            "sky": sky(day, minute),
            "dark": dark(day, minute),
            "growth": {
                "fields": {"stage": growth["fields"]["stage"], "neglected": neglected(growth)},
                "flower_garden": {"stage": growth["flower_garden"]["stage"]},
            },
            "chronicle": world["chronicle"][::-1],
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

    @staticmethod
    def _plan_state(plan: dict[str, Any] | None, day: int, minute: int) -> dict[str, Any] | None:
        """Today's plan with its current and next entry marked; yesterday's plan is none."""
        if not plan or plan["day"] != day:
            return None
        current, following = marks(plan["entries"], minute)
        entries = [
            {
                "time": hhmm(e["minute"]),
                "place": e["place"] if e["place"] in (None, "home") else label(e["place"]),
                "villager": e["villager"],
                "purpose": e["purpose"],
            }
            for e in plan["entries"]
        ]
        return {
            "entries": entries,
            "current": current,
            "next": following,
            "revisions": plan["revisions"],
        }

    def _publish(self) -> None:
        self.store.save_village(self.world)
        self.bus.publish(CHANNEL, {"type": "state", "state": self.state()})

    # --- villager agents ---

    def ensure_agents(self, *, recreate: bool = False) -> None:
        """Creates each villager's block agent and the shared reflection, chronicler and planner
        agents; with `recreate`
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
        if missing(self.world["chronicler_agent_id"]):
            self.world["chronicler_agent_id"] = self._create_agent(chronicler_agent())
        if missing(self.world["planner_agent_id"]):
            self.world["planner_agent_id"] = self._create_agent(planner_agent())
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

    def _note(self, text: str) -> None:
        """A happening for tonight's chronicle, while the villagers' day is on."""
        record = self.world["day_record"]
        if record is not None and len(record["items"]) < RECORD_ITEMS:
            record["items"].append({"tick": self.world["tick"], "text": text[:RECORD_TEXT]})

    def _trigger(self, v: Villager, reason: str) -> None:
        if reason not in v["triggers"]:
            v["triggers"].append(reason)

    def _end_conversations(self, name: str, reason: str) -> None:
        """Ends `name`'s conversations because of what `name` did."""
        for c in [c for c in self.world["conversations"] if name in (c["a"], c["b"])]:
            self._end_conversation(c, reason, by=name)

    def _end_conversation(self, c: dict[str, Any], reason: str, by: str | None = None) -> None:
        """Both remember it; the one who ended it (`by`) has no reason to decide again."""
        self.world["conversations"].remove(c)
        transcript = " / ".join(c.get("transcript", []))
        self._note(f"{c['a']} and {c['b']} talked; what they said (their claims): {transcript}")
        day = clock(self.world["tick"])[0]
        for me, other in ((c["a"], c["b"]), (c["b"], c["a"])):
            v = self._villager(me)
            self._event(v, "ended", f"Your conversation with {other} ended: {reason}.", to=other)
            if me != by:
                self._trigger(v, "conversation ended")
            self._remember(v, "conversation", f"Talked with {other}: {transcript}", [other])
            plan = v["plan"]
            if (
                c["lines"] >= PLAN_TALK_LINES
                and not (v["asleep"] or v["bedtime"] or self.resetting)
                and plan
                and plan["day"] == day
                and plan["revisions"] < REVISIONS
            ):
                plan["revisions"] += 1  # counted when it starts: two revision runs a day at most
                self._start_plan(me, transcript)

    def _remember(self, v: Villager, kind: str, text: str, about: list[str]) -> None:
        remember(v, self.world["tick"], kind, text, about, place_at(v["x"], v["y"]))

    def _fall_asleep(self, v: Villager) -> None:
        v |= {"asleep": True, "bedtime": False, "goal": None, "triggers": [], "neighbours": []}
        self._event(v, "slept", "You went to bed.")
        if unreflected(v["memories"]) and not self.resetting:
            self._start_reflection(v["name"])
        record = self.world["day_record"]
        if record and all(x["asleep"] for x in self.world["villagers"]) and not self.resetting:
            self.world["day_record"] = None  # the next waking opens the next day's record
            self.chronicle = asyncio.create_task(self._chronicle(record, self.chronicle))

    def _schedule(self, v: Villager, minute: int) -> None:
        """Wakes a villager at its wake-up time and sends it home to bed at its bedtime."""
        name = v["name"]
        awake = awake_at(name, minute)
        if v["asleep"]:
            if awake:
                v |= {"asleep": False, "beliefs": {}}  # a new day: yesterday's sightings are old
                if self.world["day_record"] is None:  # the first to wake opens the day's record
                    day = clock(self.world["tick"])[0]
                    self.world["day_record"] = {"day": day, "items": []}
                    for news in end_day(self.world, day - 1) if day > 1 else []:
                        self._note(f"Overnight: {news}")  # yesterday's work shows by morning
                self._event(v, "woke", "You woke up at home.")
                self._trigger(v, "woke")
                if not self.resetting:
                    self._start_plan(name)
            return
        if not awake and not v["bedtime"]:
            v |= {"bedtime": True, "goal": {"kind": "home"}, "triggers": []}
            self._remember_festival(v)  # the evening is over for this villager
            self._end_conversations(name, f"{name} went home to bed")
            self._event(v, "bedtime", "It is your bedtime; you head home.")
        if v["bedtime"] and cell(v) == door(name):
            self._fall_asleep(v)

    def _festival_guests(self) -> None:
        """Who came to the square on the festival evening."""
        tick = self.world["tick"]
        day = clock(tick)[0]
        if festival_in(day) != 0 or minute_of_day(tick) < FESTIVAL_EVENING:
            return
        festival: dict[str, Any] | None = self.world["festival"]
        if festival is None or festival["day"] != day:
            festival = {"day": day, "present": []}
            self.world["festival"] = festival
            for v in self.world["villagers"]:  # everyone awake hears it begin and may set off
                if not v["asleep"] and not v["bedtime"]:
                    self._event(v, "festival", f"{FESTIVAL_BEGINS}.")
                    self._trigger(v, "festival")
        present: list[str] = festival["present"]
        for v in self.world["villagers"]:
            if (
                not v["asleep"]
                and place_at(v["x"], v["y"]) == "square"
                and v["name"] not in present
            ):
                present.append(v["name"])
                self._note(f"{v['name']} joined the harvest festival on the square.")

    def _remember_festival(self, v: Villager) -> None:
        festival = self.world["festival"]
        if not festival or festival["day"] != clock(self.world["tick"])[0]:
            return
        if v["name"] in festival["present"]:
            others = [n for n in festival["present"] if n != v["name"]]
            company = f"with {' and '.join(others)}" if others else "on your own"
            self._remember(v, "festival", f"The harvest festival on the square {company}.", others)

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
                        if v["name"] < name:  # once for the pair
                            self._note(f"{v['name']} and {name} met.")
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
                self._note(f"{v['name']} found {other['name']}.")
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
                self._note(f"{v['name']} looked for {other['name']} in vain: {why}.")

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
        self, agent_id: str | None, name: str | None, prompt: str, tick: int
    ) -> tuple[str | None, str | None, str | None]:
        """(run id, answer, why it failed) for one run of a village agent for `name` (None: the
        whole village, as the chronicle)."""
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

    def _start_plan(self, name: str, revise: str | None = None) -> None:
        previous = self.plans.get(name)  # one villager's plans never overlap
        self.plans[name] = asyncio.create_task(self._plan(name, revise, previous))

    async def _plan(
        self, name: str, revise: str | None, previous: asyncio.Task[None] | None
    ) -> None:
        """A plan for the day on waking, or a revision (`revise`: the conversation just had)."""
        if previous:
            await asyncio.gather(previous, return_exceptions=True)
        tick = self.world["tick"]
        day = clock(tick)[0]
        v = self._villager(name)
        revision = v["plan"]["revisions"] if revise is not None and v["plan"] else 0
        prompt = plan_prompt(self.world, name, revise)
        try:
            run_id, answer, failed = await self._run(
                self.world["planner_agent_id"], name, prompt, tick
            )
        finally:
            if self.plans.get(name) is asyncio.current_task():
                del self.plans[name]
        if self.resetting:
            return
        entries, reason = (None, failed) if failed else parse_plan(answer, name)
        # Decoding JSON can undo redaction of the raw answer: redact again.
        entries, reason = redact(entries, self.secrets), redact(reason, self.secrets)
        v = self._villager(name)
        if entries and (v["asleep"] or clock(self.world["tick"])[0] != day):
            entries, reason = None, "the day it was for is over"  # one plan a villager a day
        if entries:
            v["plan"] = {"day": day, "entries": entries, "revisions": revision}
            text = "; ".join(entry_text(e) for e in entries)
            if revise is None:
                self._event(v, "planned", "You planned your day.")
                self._note(f"{name}'s plan for the day: {text}")
            else:
                self._event(v, "planned", "You changed your plan.")
                self._note(f"{name} changed the plan for the day: {text}")
        action: dict[str, Any] = {"action": "plan", "revision": revision}
        action |= {"entries": [entry_text(e) for e in entries]} if entries else {"reason": reason}
        if run_id:
            self.store.set_village_action(run_id, action)
        self._publish()

    async def _chronicle(self, record: dict[str, Any], previous: asyncio.Task[None] | None) -> None:
        """Tonight's chronicle entry, for the day the record began even past midnight."""
        if previous:  # a late chronicle never overtakes the one before
            await asyncio.gather(previous, return_exceptions=True)
        tick, day = self.world["tick"], record["day"]
        prompt = chronicle_prompt(self.world, record)
        run_id, answer, failed = await self._run(
            self.world["chronicler_agent_id"], None, prompt, tick
        )
        if self.resetting:
            return
        entry, reason = (None, failed) if failed else parse_entry(answer)
        entry, reason = redact(entry, self.secrets), redact(reason, self.secrets)
        if entry:
            year, season, day_of_season = date(day)
            kept = {"day": day, "year": year, "season": season, "day_of_season": day_of_season}
            kept |= {"weather": weather(day), **entry, "run_id": run_id}
            self.world["chronicle"] = [*self.world["chronicle"], kept][-CHRONICLE_KEPT:]
        if run_id:
            action = {"action": "chronicle", "day": day}
            self.store.set_village_action(run_id, action | (entry or {"reason": reason}))
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
            self._set_off(v, action["place"])
        elif kind == "find":
            self._seek(v, action["villager"])
        elif kind == "say":
            self._say(v, action["text"], action["to"])
        else:  # goodbye, then perhaps on its way
            if action["text"] and awake_neighbours(self.world, name):
                self._say(v, action["text"], None)
            self._end_conversations(name, f"{name} said goodbye")
            if not action["text"]:
                self._event(v, "said", "You said goodbye.")
            if action.get("ignored"):
                self._event(v, "waited", f"You said goodbye but stayed: {action['ignored']}.")
            elif action.get("place"):
                self._set_off(v, action["place"])
            elif action.get("villager"):
                self._seek(v, action["villager"])

    def _set_off(self, v: Villager, place: str) -> None:
        if place == "home":
            v["goal"] = {"kind": "home"}
            self._event(v, "set_off", "You set off for home.")
        else:
            v["goal"] = {"kind": "place", "place": place}
            self._event(v, "set_off", f"You set off for the {label(place)}.")
            self._note(f"{v['name']} set off for the {label(place)}.")

    def _seek(self, v: Villager, other: str) -> None:
        v["goal"] = {"kind": "find", "villager": other, "target": self._find_target(v, other)}
        self._event(v, "set_off", f"You set off to find {other}.", to=other)
        self._look()  # already in sight: aim at them now

    def _find_target(self, v: Villager, other: str) -> list[list[int]]:
        belief = v["beliefs"].get(other)
        where = belief["where"] if belief else usual_place(other, self.world["tick"])
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
        v["said"] = [*v["said"], text][-SAID_KEPT:]
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
            heard = f'{name} said{heard_to}: "{text}"'
            self._event(hearer, "heard", heard, **{"from": name, "to": to})
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
        """Waits until no decision, reflection, plan or chronicle is in flight."""
        while (
            self.decisions
            or self.reflections
            or self.plans
            or (self.chronicle and not self.chronicle.done())
        ):
            tasks = [*self.decisions.values(), *self.reflections.values(), *self.plans.values()]
            tasks += [self.chronicle] if self.chronicle else []
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
        # Every villager owns fixed slots in the step (round by round, in villager order), so a
        # walker moves every interval / CELLS_PER_STEP seconds whoever else walks, and the view
        # can glide it there without pausing, also across steps.
        villagers = world["villagers"]
        gap = self.move_gap
        if gap is None:
            moves = CELLS_PER_STEP * len(villagers)
            gap = STEP_GAP if self.in_step else world["interval"] / moves
        slots = [v for _ in range(CELLS_PER_STEP) for v in villagers]
        for i, v in enumerate(slots):
            if not any(self._walks(w) or w["name"] in self.decisions for w in villagers):
                break  # nobody walks or may start to: the rest of the step stays still
            if i and gap:
                await asyncio.sleep(gap)  # an empty slot keeps its time, so the rhythm holds
            if self._walks(v):  # someone may have spoken to it meanwhile
                self._walk(v)
                self._look()
                self._publish()
        self._look()
        self._upkeep()
        tended = world["tended"]
        for place in {place_at(v["x"], v["y"]) for v in villagers if not v["asleep"]} & set(tended):
            tended[place] += 1  # steps with an awake villager on the fields or the garden
        self._festival_guests()
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
            shared = ("reflection_agent_id", "chronicler_agent_id", "planner_agent_id")
            agent_ids = {k: self.world[k] for k in shared}
            self.world = new_world() | agent_ids
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
