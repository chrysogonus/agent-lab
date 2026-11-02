"""The town hall meeting's runs (M12): Hilde's proposals, the votes, her decision and the work
plan. A mixin of `Village`, so every name stays where the runner and its tests look for it."""

import asyncio
from collections.abc import Coroutine
from typing import Any

from agent_lab.store import Store
from agent_lab.tracing.redact import redact
from agent_lab.village.build import buildable, entry, new_project, task_text
from agent_lab.village.meeting import (
    HILDE_WAITED,
    MEETING_CALL,
    MEETING_CLOSES,
    MEETING_OPENS,
    decision_prompt,
    meeting_day,
    meeting_text,
    parse_decision,
    parse_proposals,
    parse_tasks,
    parse_vote,
    proposal_prompt,
    tally,
    vote_prompt,
    work_plan_prompt,
)
from agent_lab.village.world import clock, listed, minute_of_day, place_at

Villager = dict[str, Any]


class MeetingRuns:
    # What the meeting runs use of the village, defined by `Village`.
    world: dict[str, Any]
    store: Store
    secrets: tuple[str, ...]
    meetings: dict[str, asyncio.Task[None]]
    resetting: bool

    def _villager(self, name: str) -> Villager: ...
    def _event(self, v: Villager, kind: str, text: str, **extra: Any) -> None: ...
    def _note(self, text: str) -> None: ...
    def _trigger(self, v: Villager, reason: str) -> None: ...
    def _remember(self, v: Villager, kind: str, text: str, about: list[str]) -> None: ...
    def _publish(self) -> None: ...
    async def _run(
        self, agent_id: str | None, name: str | None, prompt: str, tick: int
    ) -> tuple[str | None, str | None, str | None]: ...

    @staticmethod
    def _meeting_state(meeting: dict[str, Any] | None) -> dict[str, Any] | None:
        """The latest meeting with project names, and the votes as a list."""
        if meeting is None:
            return None

        def name(key: str | None) -> str | None:
            return entry(key).name if key else None

        decision = meeting["decision"]
        return {
            **meeting,
            "proposals": [{**p, "name": name(p["key"])} for p in meeting["proposals"]],
            "votes": [
                {"villager": who, **vote, "name": name(vote["key"])}
                for who, vote in meeting["votes"].items()
            ],
            "decision": decision and {**decision, "name": name(decision["key"])},
        }

    def _meeting(self) -> None:
        """Every third day: Hilde's proposals once she is up, votes from whoever comes to the
        town hall between 17:00 and 17:30, then her decision."""
        tick = self.world["tick"]
        day, minute = clock(tick)[0], minute_of_day(tick)
        if not meeting_day(day) or self.resetting:
            return
        meeting = self.world["meeting"]
        if meeting is None or meeting["day"] != day:
            hilde = self._villager("Hilde")
            if not (hilde["asleep"] or hilde["bedtime"]) and minute < MEETING_CLOSES:
                self._open_meeting(day)
            return
        if meeting["outcome"]:
            return
        if minute >= MEETING_CALL and not meeting.get("called"):
            self._call_to_meeting(meeting)
        if MEETING_OPENS <= minute <= HILDE_WAITED:  # everyone who comes before she decides
            for v in self.world["villagers"]:
                name = v["name"]
                here = place_at(v["x"], v["y"]) == "town_hall"
                if here and not (v["asleep"] or v["bedtime"]) and name not in meeting["present"]:
                    meeting["present"].append(name)
                    self._note(f"{name} came to the town hall meeting.")
            for name in meeting["present"]:  # also when the proposals came late
                key = f"vote:{name}"
                if (
                    name != "Hilde"
                    and not meeting.get("deciding")  # the votes Hilde sees are the ones counted
                    and meeting["kind"] == "vote"
                    and meeting["proposals"]
                    and name not in meeting["votes"]
                    and key not in self.meetings
                ):
                    self._start_meeting_run(key, self._vote(name, meeting))
        if minute < MEETING_CLOSES or self.meetings:
            return
        if "Hilde" not in meeting["present"]:
            if minute >= HILDE_WAITED:  # she may still be on her way until then
                self._end_meeting(meeting, "called off: Hilde did not come")
        elif meeting["kind"] == "vote":
            if meeting["present"] == ["Hilde"]:
                self._note("Nobody but Hilde came to the town hall meeting.")
            meeting["deciding"] = True
            self._start_meeting_run("decide", self._decide_meeting(meeting))
        elif self.world["project"] is None:  # finished since the morning: nothing to review
            self._end_meeting(meeting, "reviewed")
        else:
            self._start_meeting_run("tasks", self._assign(meeting))

    def _call_to_meeting(self, meeting: dict[str, Any]) -> None:
        """At 16:30 everyone up and away is called to the town hall, with the action to take:
        on the real model villagers stayed in their talks or came too late without it."""
        meeting["called"] = True
        why = "vote" if meeting["kind"] == "vote" else "hear how the building goes"
        how = (
            '({"action": "move", "place": "town hall"}; if you are talking, '
            '{"action": "goodbye", "place": "town hall"}).'
        )
        for v in self.world["villagers"]:
            if v["asleep"] or v["bedtime"] or place_at(v["x"], v["y"]) == "town_hall":
                continue
            hilde = v["name"] == "Hilde"
            whose, goal = ("Your", "chair it") if hilde else ("The", why)
            text = f"{whose} town hall meeting starts at 17:00: go to the town hall now to {goal}"
            text += f" {how}"
            self._event(v, "meeting", text)
            self._trigger(v, "meeting")

    def _open_meeting(self, day: int) -> None:
        meeting: dict[str, Any] = {
            "day": day,
            "kind": "review" if self.world["project"] else "vote",
            "proposals": [],
            "votes": {},
            "present": [],
            "decision": None,
            "outcome": None,
        }
        self.world["meeting"] = meeting
        if self.world["project"]:
            return
        if not buildable(self.world):
            self._end_meeting(meeting, "nothing left to build")
            return
        self._start_meeting_run("propose", self._propose(meeting))

    def _end_meeting(self, meeting: dict[str, Any], outcome: str) -> None:
        meeting["outcome"] = outcome
        text = meeting_text(self.world, "Lina")  # what everyone but Hilde is told
        for v in self.world["villagers"]:
            if not v["asleep"]:
                self._event(v, "meeting", text)
        self._note(text)

    def _start_meeting_run(self, key: str, run: Coroutine[Any, Any, None]) -> None:
        """A meeting run in `self.meetings` under what it is for, until it has ended."""

        async def tracked() -> None:
            try:
                await run
            finally:
                if self.meetings.get(key) is asyncio.current_task():
                    del self.meetings[key]

        self.meetings[key] = asyncio.create_task(tracked())

    async def _meeting_call(
        self, name: str, prompt: str
    ) -> tuple[str | None, str | None, str | None]:
        return await self._run(self.world["meeting_agent_id"], name, prompt, self.world["tick"])

    def _asked_again(self, run_id: str | None, action: str, why: str | None) -> None:
        """Proposals and work plans matter for days: an unusable one is asked for once more."""
        if run_id:
            self.store.set_village_action(
                run_id, {"action": action, "reason": f"{why}; asked again"}
            )

    def _still(self, meeting: dict[str, Any]) -> bool:
        """A meeting run's result counts only for the meeting it was asked for, on its day."""
        today = clock(self.world["tick"])[0]
        return not self.resetting and self.world["meeting"] is meeting and meeting["day"] == today

    async def _propose(self, meeting: dict[str, Any], again: bool = True) -> None:
        run_id, answer, failed = await self._meeting_call("Hilde", proposal_prompt(self.world))
        if not self._still(meeting):
            return
        found, why = (None, failed) if failed else parse_proposals(answer, self.world)
        found, why = redact(found, self.secrets), redact(why, self.secrets)
        if not found and again:
            self._asked_again(run_id, "propose", why)
            await self._propose(meeting, again=False)
            return
        action: dict[str, Any] = {"action": "propose"}
        if found:
            meeting["proposals"] = [{**p, "run_id": run_id} for p in found]
            listed_text = "; ".join(f"{entry(p['key']).name} ({p['reason']})" for p in found)
            self._event(
                self._villager("Hilde"),
                "proposed",
                f"You proposed for the town hall meeting: {listed_text}.",
            )
            self._note(f"Hilde proposed for the town hall meeting (proposals only): {listed_text}.")
            action["proposals"] = [f"{entry(p['key']).name}: {p['reason']}" for p in found]
        else:
            self._end_meeting(meeting, "called off: Hilde had no proposals")
            action["reason"] = why
        if run_id:
            self.store.set_village_action(run_id, action)
        self._publish()

    async def _vote(self, name: str, meeting: dict[str, Any]) -> None:
        run_id, answer, failed = await self._meeting_call(name, vote_prompt(self.world, name))
        if not self._still(meeting):
            return
        vote, why = (None, failed) if failed else parse_vote(answer, meeting["proposals"])
        vote, why = redact(vote, self.secrets), redact(why, self.secrets)
        if vote:
            project = entry(vote["key"]).name
            meeting["votes"][name] = {**vote, "run_id": run_id}
            self._event(self._villager(name), "meeting", f"You voted for {project}.")
            self._note(f"{name} voted for {project} (their claim): {vote['reason']}")
            action = {"action": "vote", "project": project, "reason": vote["reason"]}
        else:
            meeting["votes"][name] = {"key": None, "reason": why, "run_id": run_id}
            action = {"action": "vote", "reason": why}
        if run_id:
            self.store.set_village_action(run_id, action)
        self._publish()

    async def _decide_meeting(self, meeting: dict[str, Any]) -> None:
        run_id, answer, failed = await self._meeting_call("Hilde", decision_prompt(self.world))
        if not self._still(meeting):
            return
        decision, why = parse_decision(
            None if failed else answer, meeting["proposals"], meeting["votes"]
        )
        why = failed or why
        decision, why = redact(decision, self.secrets), redact(why, self.secrets)
        if decision:
            self._decided(meeting, {**decision, "run_id": run_id})
            action = {"action": "decide", "project": entry(decision["key"]).name}
            action |= {k: decision[k] for k in ("reason", "against", "by")}
        else:
            self._end_meeting(meeting, "no decision")
            action = {"action": "decide", "reason": why}
        if run_id:
            self.store.set_village_action(run_id, action)
        self._publish()

    def _decided(self, meeting: dict[str, Any], decision: dict[str, Any]) -> None:
        day = clock(self.world["tick"])[0]
        meeting |= {"decision": decision, "outcome": "decided"}
        self.world["project"] = new_project(decision["key"], day)
        project = entry(decision["key"]).name
        text = f"At the town hall meeting Hilde chose {project}: {decision['reason']}"
        if decision["against"]:
            counts = tally(meeting["votes"])
            wanted = [entry(k).name for k, n in counts.items() if n == max(counts.values())]
            text += f" She went against the vote (most wanted {listed(wanted)})."
        for v in self.world["villagers"]:
            if not v["asleep"]:
                self._event(v, "meeting", text)
        for name in meeting["present"]:
            mine = meeting["votes"].get(name, {}).get("key")
            others = [n for n in meeting["present"] if n != name]
            memory = f"The town hall meeting: Hilde chose {project}."
            memory += f" I voted for {entry(mine).name}." if mine else ""
            self._remember(self._villager(name), "meeting", memory, others)
        self._note(text)
        self._start_meeting_run("tasks", self._assign(meeting))

    async def _assign(self, meeting: dict[str, Any], again: bool = True) -> None:
        """Hilde hands out the work of the project: after a decision, or at a review meeting."""
        if self.world["project"] is None:  # finished meanwhile (a second ask comes later)
            if meeting["kind"] == "review" and self._still(meeting):
                self._end_meeting(meeting, "reviewed")
            return
        run_id, answer, failed = await self._meeting_call("Hilde", work_plan_prompt(self.world))
        project = self.world["project"]
        if not self._still(meeting) or project is None:
            return
        tasks, why = (None, failed) if failed else parse_tasks(answer)
        tasks, why = redact(tasks, self.secrets), redact(why, self.secrets)
        if not tasks and again:
            self._asked_again(run_id, "assign", why)
            await self._assign(meeting, again=False)
            return
        action: dict[str, Any] = {"action": "assign"}
        if tasks:
            project["tasks"] = tasks
            shares: dict[str, list[str]] = {}
            for task in tasks:
                for name in task["villagers"]:
                    shares.setdefault(name, []).append(task_text(task))
            for name, share in shares.items():
                v = self._villager(name)
                said = "You took on:" if name == "Hilde" else "Hilde asked you to"
                self._event(v, "task", f"{said} {'; '.join(share)}.")
                if not v["asleep"]:
                    self._trigger(v, "task")
            handed = "; ".join(f"{task_text(t)}: {', '.join(t['villagers'])}" for t in tasks)
            self._note(f"Hilde handed out the work (intentions, not events): {handed}.")
            action["tasks"] = [
                f"{t['task']}{' ' + t['goods'] if t['goods'] else ''}: {', '.join(t['villagers'])}"
                for t in tasks
            ]
        else:
            action["reason"] = why
        if meeting["kind"] == "review":
            self._end_meeting(meeting, "reviewed")
        if run_id:
            self.store.set_village_action(run_id, action)
        self._publish()
