"""The runner's part of M15: the day's happenings, boat trips and whispers
(specs/015-daily-happenings/plan.md). A mixin of `Village`; the rules live in `happenings.py`
and `boat.py`."""

from typing import Any

from agent_lab.store import Store
from agent_lab.village.boat import boat_step, start_trip
from agent_lab.village.happenings import (
    animal_next_to,
    day_happenings,
    happening_text,
    noticed,
    step,
    told_text,
)
from agent_lab.village.trade import carried_text
from agent_lab.village.work import mend_step
from agent_lab.village.world import clock, hhmm, label, listed

Villager = dict[str, Any]
Happening = dict[str, Any]


def _came(h: Happening) -> str:
    """The note when a happening starts."""
    text = h["details"]["text"]
    if h["kind"] == "letter":
        return f"The postman brought a letter for {h['concerns']}."
    if h["kind"] == "visitor":
        return f"{text} came to visit {h['concerns']}."
    if h["kind"] == "animal":
        return f"{text.capitalize()} wandered to the {label(h['place'])}."
    if h["kind"] == "repair":
        return f"{text.capitalize()} broke."
    return f"A peddler came to the square with {h['details']['goods']}."


def _passed(h: Happening) -> str:
    """The note when a happening's time is over with nobody dealing with it."""
    text = h["details"]["text"]
    if h["kind"] == "letter":
        return f"{h['concerns']}'s letter lay unread."
    if h["kind"] == "visitor":
        return f"{text} went home without seeing {h['concerns']}."
    if h["kind"] == "animal":
        return f"{text.capitalize()} found its own way home."
    if h["kind"] == "repair":
        return f"{text.capitalize()} stayed broken."
    return f"The peddler left the square; nobody traded for {h['details']['goods']}."


POSTMAN = 30  # minutes the postman is seen walking to the door before the letter is there


def happening_state(h: Happening, minute: int) -> dict[str, Any]:
    """A happening for the view: its words, where it is and what figure to draw, if any."""
    figure: str | None = None
    if h["kind"] == "letter":
        figure = "postman" if h["state"] == "coming" and h["start"] - POSTMAN <= minute else None
    elif h["kind"] == "visitor":
        figure = "visitor" if h["state"] in ("here", "dealt") and minute < h["end"] else None
    elif h["state"] == "here":
        figure = h["kind"]
    return {
        "kind": h["kind"],
        "label": happening_text(h),
        "cell": h["cell"],
        "state": h["state"],
        "by": h["by"],
        "concerns": h["concerns"],
        "start": hhmm(h["start"]),
        "end": hhmm(h["end"]),
        "figure": figure,
    }


class HappeningRuns:
    # What the happening runs use of the village, defined by `Village`.
    world: dict[str, Any]
    store: Store
    resetting: bool

    def _villager(self, name: str) -> Villager: ...
    def _event(self, v: Villager, kind: str, text: str, **extra: Any) -> None: ...
    def _note(self, text: str) -> None: ...
    def _trigger(self, v: Villager, reason: str) -> None: ...
    def _remember(self, v: Villager, kind: str, text: str, about: list[str]) -> None: ...
    def _publish(self) -> None: ...
    def _aim(self, v: Villager, goal: dict[str, Any]) -> None: ...
    def _end_intention(self, v: Villager, why: str, *, ask: bool = True) -> None: ...
    def _say(self, v: Villager, text: str, to: str | None) -> None: ...

    # --- the day's happenings ---

    def _open_happenings(self, day: int) -> None:
        self.world["happenings"] = day_happenings(day)

    def _tell(self, v: Villager, text: str) -> None:
        if not v["asleep"]:
            self._event(v, "happening", text)
            self._trigger(v, "happening")

    def _happenings(self) -> None:
        """One step: happenings come, are seen, are dealt with or pass; broken things mend."""
        for change in step(self.world):
            h: Happening = change["happening"]
            if change["change"] == "here":
                self._note(_came(h))
                told = told_text(h)
                if told and h["concerns"]:
                    self._tell(self._villager(h["concerns"]), told)
            elif change["change"] == "passed":
                self._note(_passed(h))
            else:
                self._dealt(h, change["by"])
        for name, h in mend_step(self.world):
            self._dealt(h, name)
        for v in self.world["villagers"]:
            for h in noticed(self.world, v):
                h["seen_by"].append(v["name"])
                self._tell(v, f"You see: {happening_text(h)}")

    def _dealt(self, h: Happening, by: str) -> None:
        """The note, event and memories of a happening dealt with."""
        v, text = self._villager(by), h["details"]["text"]
        if h["kind"] == "letter":
            self._tell(v, f"You read your letter: {text}")
            self._remember(v, "happening", f"A letter came for you: {text}", [])
            self._note(f"{by} got a letter: {text}")
        elif h["kind"] == "visitor":
            self._remember(v, "happening", f"{h['details']['name']}, visited you.", [])
            self._note(f"{by} spent time with {text}.")
        elif h["kind"] == "animal":
            owner = self._villager(h["concerns"])
            self._remember(v, "happening", f"You led {text} home.", [owner["name"]])
            if owner is not v:
                own = h["details"]["own"]
                self._remember(owner, "happening", f"{by} brought {own} home.", [by])
                self._tell(owner, f"{by} brought {own} home.")
            self._note(f"{by} led {text} home.")
        elif h["kind"] == "repair":
            self._remember(v, "happening", f"You mended {text}.", [])
            self._event(v, "happening", f"You mended {text}.")
            self._note(f"{by} mended {text}.")

    def _lead(self, v: Villager) -> None:
        animal = animal_next_to(self.world, v["name"])
        if animal:
            animal["leader"] = v["name"]
            self._note(f"{v['name']} set out to take {animal['details']['text']} home.")

    def _trade_curiosity(self, v: Villager, goods: str, paid: str) -> None:
        """A basket for the peddler's curiosity: kept, not carried."""
        peddler = next(h for h in self.world["happenings"] if h["kind"] == "peddler")
        day = clock(self.world["tick"])[0]
        v["basket"] = None
        v["keepsakes"] = [*v["keepsakes"], {"name": goods, "day": day}]
        peddler |= {"state": "dealt", "by": v["name"]}
        text = f"traded a {carried_text(paid)} for {goods} from the peddler"
        self._event(v, "traded", f"You {text}.")
        self._remember(v, "keepsake", f"You {text}.", [])
        self._note(f"{v['name']} {text}.")

    # --- boat trips ---

    def _row(self, v: Villager, action: dict[str, Any]) -> None:
        """Take the boat out from the pier, or join it when asked."""
        name, boat = v["name"], self.world["boat"]
        if boat and boat["state"] == "boarding" and boat["invited"] == name:
            boat |= {"rowers": [*boat["rowers"], name], "invited": None}
            self._event(v, "rowed", f"You got into the boat with {boat['rowers'][0]}.")
            return
        invited: str | None = action.get("with")
        start_trip(self.world, name, invited, action.get("until"))
        self._event(v, "rowed", "You take the boat out on the lake.")
        if invited:
            other = self._villager(invited)
            text = f'{name} asks you to come out in the boat ({{"action": "row"}} to come along).'
            self._event(other, "invited", text, **{"from": name})
            self._trigger(other, "invited")

    def _boat(self) -> None:
        """One step of the boat: out from the pier, round the lake, back."""
        for change in boat_step(self.world):
            rowers: list[str] = change["rowers"]
            if change["change"] == "out":
                self._note(f"{listed(rowers)} rowed out on the lake.")
                for name in rowers:
                    self._villager(name)["goal"] = None
                continue
            self._back(rowers)

    def _back(self, rowers: list[str]) -> None:
        self._note(f"{listed(rowers)} came back to the pier.")
        for name in rowers:
            v = self._villager(name)
            others = [n for n in rowers if n != name]
            company = f"with {listed(others)}" if others else "on your own"
            self._remember(v, "boat", f"A boat trip on the lake {company}.", others)
            self._event(v, "rowed", "You came back to the pier.")
            v["working"] = None
            if v["intention"] and v["intention"]["kind"] == "row":
                self._end_intention(v, "the boat is back at the pier")
