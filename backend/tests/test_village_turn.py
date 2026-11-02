"""Observations, actions, beliefs and the villager agents (FR-009, FR-010, FR-014 to FR-016)."""

import json
from typing import Any

import pytest

from agent_lab.blocks.model import BlocksConfig, layout_errors
from agent_lab.village.seasons import WEATHER_TEXT, date, weather
from agent_lab.village.turn import (
    SPEECH_SHOWN,
    belief_text,
    heard_places,
    observation,
    parse_action,
    seen_text,
    villager_agent,
)
from agent_lab.village.world import VILLAGERS, door, label_cell, new_world, place_cells, steps_to

MARKET = label_cell("market")


def world_with(tick: int = 30, **changes: Any) -> dict[str, Any]:
    """Everyone awake at its door unless changed; tick 30 is 09:30."""
    world = new_world()
    world["tick"] = tick
    for v in world["villagers"]:
        v["asleep"] = False
        v.update(changes.get(v["name"], {}))
    return world


def at(x: int, y: int) -> dict[str, int]:
    return {"x": x, "y": y}


def test_observation() -> None:
    mx, my = MARKET
    world = world_with(
        Hilde=at(mx, my),
        Jonas={
            **at(mx + 1, my),
            "inbox": [
                {"from": "Hilde", "to": "Jonas", "text": "Fish for the festival?", "tick": 29},
                {"from": "Hilde", "to": None, "text": "Hello all!", "tick": 29},
            ],
            "events": [{"tick": 28, "kind": "arrived", "text": "You arrived at the market."}],
            "beliefs": {
                "Greta": {"where": "fields", "cell": [2, 15], "tick": 25, "source": "seen"},
                "Lina": {
                    "where": "square",
                    "cell": [12, 7],
                    "tick": 27,
                    "source": "heard",
                    "from": "Hilde",
                },
            },
        },
        Lina=at(mx + 4, my + 1),
        Greta={"asleep": True},
    )
    world["conversations"] = [{"a": "Hilde", "b": "Jonas", "lines": 2, "last_tick": 29}]
    text = observation(world, "Jonas")
    weather_line = WEATHER_TEXT[weather(1)]
    assert text.startswith(
        "What you know for sure:\n"
        f"Day 1 (day 1 of spring, year 1), 09:30, morning. {weather_line}; "
        "this is the real weather.\n"
    )
    assert "\nYou are at the market." in text
    assert "You get up at 05:00 and go to bed at 21:00." in text
    assert "At this hour you are usually at the pier." in text
    assert "Next to you: Mayor Hilde." in text
    assert "In sight: Lina the flower girl (3 steps away)." in text
    assert "You are talking with Hilde (2 lines so far)." in text
    assert '- Hilde to you: "Fish for the festival?"' in text and '- Hilde: "Hello all!"' in text
    assert "- Greta: at the fields (seen 08:40)" in text
    assert "- Lina: usually at the flower garden around now (their routine)" in text
    assert "Heard about where others are:\n- Lina: at the square (Hilde said at 09:00)" in text
    assert "- Hilde: usually at the town hall around now (their routine)" in text
    places = text.split("Places: ")[1].split("\n")[0]
    assert f"town hall {steps_to(mx + 1, my, place_cells('town_hall'))} steps" in places
    assert "market" not in places and "your home" in places
    assert "- 09:10 You arrived at the market." in text
    assert text.endswith("What do you do? Answer with one JSON object.")


def test_observation_when_alone_and_walking() -> None:
    world = world_with(Hilde={"goal": {"kind": "find", "villager": "Lina", "target": [[1, 1]]}})
    text = observation(world, "Hilde")
    assert "You are at your home's door." in text and "You are looking for Lina." in text
    assert "Next to you: nobody." in text and "You are not talking with anyone." in text


def test_belief_from_routine_outside_waking_hours() -> None:
    world = world_with(tick=0)
    assert belief_text(world, "Jonas", "Hilde") == "at home asleep at this hour (their routine)"


@pytest.mark.parametrize(
    ("answer", "action"),
    [
        ('{"action": "move", "place": "market"}', {"action": "move", "place": "market"}),
        (
            '{"action": "move", "place": "the Flower Garden"}',
            {"action": "move", "place": "flower_garden"},
        ),
        ('{"action": "move", "place": "town hall"}', {"action": "move", "place": "town_hall"}),
        ('{"action": "find", "villager": "lina"}', {"action": "find", "villager": "Lina"}),
        (
            '{"action": "find", "villager": "Lina the flower girl"}',
            {"action": "find", "villager": "Lina"},
        ),
        (
            '{"action": "say", "text": "Hi", "to": "Jonas the fisher"}',
            {"action": "say", "text": "Hi", "to": "Jonas"},
        ),
        (
            '{"action": "say", "text": " Hi! ", "to": "jonas"}',
            {"action": "say", "text": "Hi!", "to": "Jonas"},
        ),
        ('{"action": "say", "text": "Hi all"}', {"action": "say", "text": "Hi all", "to": None}),
        ('{"action": "goodbye", "text": "Bye!"}', {"action": "goodbye", "text": "Bye!"}),
        ('{"action": "goodbye"}', {"action": "goodbye", "text": None}),
        (
            '{"action": "goodbye", "text": "Bye!", "place": "pier"}',
            {"action": "goodbye", "text": "Bye!", "place": "pier"},
        ),
        (
            '{"action": "goodbye", "villager": "lina"}',
            {"action": "goodbye", "text": None, "villager": "Lina"},
        ),
        (
            '{"action": "goodbye", "place": "harbour"}',
            {"action": "goodbye", "text": None, "ignored": "unknown place 'harbour'"},
        ),
        ('{"action": "wait"}', {"action": "wait"}),
    ],
)
def test_valid_actions(answer: str, action: dict[str, Any]) -> None:
    hx, hy = door("Hilde")
    world = world_with(Jonas=at(hx + 1, hy))  # next to Hilde
    assert parse_action(answer, world, "Hilde") == (action, None)


def test_move_home() -> None:
    world = world_with(Hilde=at(*MARKET))
    assert parse_action('{"action": "move", "place": "home"}', world, "Hilde") == (
        {"action": "move", "place": "home"},
        None,
    )


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        (None, "no answer"),
        ("I will go fishing.", "the answer is not JSON"),
        ('{"action": "dance"}', "not a valid action"),
        ('{"action": "move"}', "not a valid action"),
        ('{"action": "move", "place": "harbour"}', "unknown place 'harbour'"),
        ('{"action": "move", "place": "home"}', "already at your home"),
        ('{"action": "find", "villager": "Bob"}', "unknown villager 'Bob'"),
        ('{"action": "find", "villager": "Jonas"}', "Jonas is already next to you"),
        ('{"action": "say", "text": "   "}', "nothing to say"),
        ('{"action": "say", "text": "Hi", "to": "Bob"}', "unknown villager 'Bob'"),
        ('{"action": "say", "text": "Hi", "to": "Mayor Hilde"}', "unknown villager 'Mayor Hilde'"),
        ('{"action": "say", "text": "Hi", "to": "Jonas and Lina"}', "unknown villager"),
        ('{"action": "say", "text": "Hi", "to": "Lina"}', "Lina is not next to you"),
    ],
)
def test_invalid_answers_become_wait(answer: str | None, reason: str) -> None:
    hx, hy = door("Hilde")
    world = world_with(Jonas=at(hx + 1, hy))
    action, why = parse_action(answer, world, "Hilde")
    assert action == {"action": "wait"}
    assert why is not None and why.startswith(reason)


def test_speech_needs_an_awake_neighbour() -> None:
    hx, hy = door("Hilde")
    say = '{"action": "say", "text": "Hi"}'
    assert parse_action(say, world_with(), "Hilde") == ({"action": "wait"}, "nobody is next to you")
    asleep = world_with(Jonas={**at(hx + 1, hy), "asleep": True})
    assert parse_action(say, asleep, "Hilde")[1] == "nobody is next to you"
    tired = world_with(Jonas=at(hx + 1, hy))
    tired["talked_out"] = [["Hilde", "Jonas"]]
    assert parse_action(say, tired, "Hilde")[1] == (
        "you have talked a long time with Jonas; say goodbye or go on"
    )


def test_heard_places() -> None:
    assert heard_places("Lina is at the square. See you!", "Hilde", "Jonas") == {"Lina": "square"}
    assert heard_places("Greta went home.", "Hilde", "Jonas") == {"Greta": "home"}
    assert heard_places("Lina and Greta are at the market.", "Hilde", "Jonas") == {}
    assert heard_places("Jonas, meet me at the pier.", "Hilde", "Jonas") == {}  # the hearer


@pytest.mark.parametrize("name", list(VILLAGERS))
def test_villager_agents_are_valid_block_agents(name: str) -> None:
    body = villager_agent(name)
    config = BlocksConfig.model_validate({"model": "m", **body["config"]})
    assert layout_errors(config) == []
    decide, check = config.blocks
    assert decide.kind == "model" and decide.system.startswith(VILLAGERS[name].persona)
    assert VILLAGERS[name].home in decide.system and "go to bed at" in decide.system
    for example in ('{"action": "wait"}', '{"action": "find", "villager": "Lina"}'):
        assert example in decide.system and json.loads(example)
    assert "right next to you" in decide.system
    assert check.kind == "check" and check.rule == "valid_json"
    assert body["name"] == VILLAGERS[name].title


def test_each_agent_has_only_its_own_persona() -> None:
    systems = {n: villager_agent(n)["config"]["blocks"][0]["system"] for n in VILLAGERS}
    for name, system in systems.items():
        assert all(VILLAGERS[other].persona not in system for other in VILLAGERS if other != name)


def test_observation_lists_only_the_last_ten_events() -> None:
    events = [{"tick": t, "kind": "waited", "text": f"Event {t}."} for t in range(10)]
    text = observation(world_with(Lina={"events": events}), "Lina")
    assert text.count("Event ") == 10 and "Event 0." in text


def test_moving_or_finding_while_talking_needs_a_goodbye_first() -> None:
    hx, hy = door("Hilde")
    world = world_with(Jonas=at(hx + 1, hy))
    world["conversations"] = [{"a": "Jonas", "b": "Hilde", "lines": 1, "last_tick": 30}]
    for answer in (
        '{"action": "move", "place": "market"}',
        '{"action": "find", "villager": "Lina"}',
    ):
        assert parse_action(answer, world, "Hilde") == (
            {"action": "wait"},
            "you are talking with Jonas; say goodbye first",
        )
    rules = villager_agent("Hilde")["config"]["blocks"][0]["system"]
    assert '"place": "market"} to end a conversation and leave' in rules
    assert "say goodbye before you walk off" in rules


@pytest.mark.parametrize("day", [3, 10, 17, 21, 24, 30])
def test_the_observation_names_date_season_and_weather(day: int) -> None:
    world = new_world()
    world["tick"] = (day - 1) * 144 + 30  # 09:30
    for v in world["villagers"]:
        v["asleep"] = False
    year, season, day_of_season = date(day)
    first = observation(world, "Greta").split("\n")[1]
    expected = f"Day {day} (day {day_of_season} of {season}, year {year}), 09:30, morning."
    assert first == f"{expected} {WEATHER_TEXT[weather(day)]}; this is the real weather."


def test_villagers_are_told_how_the_places_they_work_at_or_see_are_doing() -> None:
    world = new_world()
    world["tick"] = 30
    world["growth"]["fields"] |= {"stage": "sprouting", "untended": 2}
    world["growth"]["flower_garden"]["stage"] = "wilting"
    for v in world["villagers"]:
        v["asleep"] = False
    fields_line = "The fields are sprouting; nobody has tended them for 2 days."
    garden_line = "The flower garden is wilting."
    assert fields_line in observation(world, "Greta")  # her work, wherever she is
    assert garden_line in observation(world, "Lina")
    hilde = next(v for v in world["villagers"] if v["name"] == "Hilde")
    hilde |= dict(zip(("x", "y"), label_cell("town_hall"), strict=True))
    far = observation(world, "Hilde")
    assert fields_line not in far and garden_line not in far
    hilde |= dict(zip(("x", "y"), place_cells("fields")[0], strict=True))
    assert fields_line in observation(world, "Hilde")  # standing on them


def _at(day: int, hour: int, minute: int = 0) -> int:
    return (day - 1) * 144 + (hour * 60 + minute - 270) // 10


def test_the_festival_is_counted_down_announced_and_expected_on_the_square() -> None:
    world = new_world()
    for v in world["villagers"]:
        v["asleep"] = False
    lines: list[str] = []
    for day in (15, 20):
        world["tick"] = _at(day, 9)
        lines.append(observation(world, "Jonas"))
    assert "The harvest festival is on the square in 6 days." in lines[0]
    assert "The harvest festival is on the square in 1 day." in lines[1]
    world["tick"] = _at(21, 9)
    assert "Today is the harvest festival, this evening on the square." in observation(
        world, "Jonas"
    )
    world["tick"] = _at(21, 18, 30)
    evening = observation(world, "Jonas")
    assert "The harvest festival is on now on the square; the whole village is expected" in evening
    assert "At this hour you are usually at the square." in evening
    world["tick"] = _at(20, 18, 30)
    assert "At this hour you are usually at the pier." in observation(world, "Jonas")
    world["tick"] = _at(10, 9)
    assert "harvest festival" not in observation(world, "Jonas")


def test_facts_come_before_what_others_claim() -> None:
    mx, my = MARKET
    world = world_with(
        Hilde=at(mx, my),
        Jonas={
            **at(mx + 1, my),
            "inbox": [{"from": "Hilde", "to": "Jonas", "text": "Storm today!", "tick": 29}],
            "events": [
                {"tick": 29, "kind": "heard", "text": 'Hilde said to you: "Storm today!"'},
            ],
            "beliefs": {
                "Lina": {
                    "where": "pier",
                    "cell": [12, 17],
                    "tick": 27,
                    "source": "heard",
                    "from": "Hilde",
                },
            },
        },
    )
    text = observation(world, "Jonas")
    parts = [
        "What you know for sure:",
        "Places: ",
        "Where the others are, as far as you know:",
        "What others told you (claims; they may be wrong):",
        "Said to you since your last turn:",
        "Heard about where others are:",
        "What you have learned:",
        "What you remember:",
        "Your last events:",
        "What do you do?",
    ]
    assert [text.index(p) for p in parts] == sorted(text.index(p) for p in parts)
    claims = text.split("What others told you")[1].split("What you have learned:")[0]
    assert '- Hilde to you: "Storm today!"' in claims
    assert "- Lina: at the pier (Hilde said at 09:00)" in claims
    facts = text.split("What others told you")[0]
    assert "Storm today!" not in facts and "Lina: at the pier" not in facts
    assert '- 09:20 Hilde said to you: "Storm today!"' in text


def test_nothing_heard_about_the_others() -> None:
    text = observation(world_with(), "Jonas")
    assert "Heard about where others are:\n- nothing" in text


def test_seen_text_shows_only_what_a_villager_saw() -> None:
    world = world_with(
        Jonas={
            "beliefs": {
                "Greta": {"where": "fields", "cell": [2, 15], "tick": 25, "source": "seen"},
                "Lina": {
                    "where": "pier",
                    "cell": [12, 17],
                    "tick": 27,
                    "source": "heard",
                    "from": "Hilde",
                },
            }
        }
    )
    assert seen_text(world, "Jonas", "Greta") == "at the fields (seen 08:40)"
    assert seen_text(world, "Jonas", "Lina") == (
        "usually at the flower garden around now (their routine)"
    )
    assert belief_text(world, "Jonas", "Lina") == "at the pier (heard from Hilde at 09:00)"


def test_a_say_repeating_one_of_the_last_three_lines_is_refused() -> None:
    hx, hy = door("Hilde")
    said = ["Where are the fish?", "Good morning.", "Nice weather."]
    world = world_with(Jonas=at(hx + 1, hy), Hilde={"said": said})
    assert parse_action('{"action": "say", "text": " where ARE the fish "}', world, "Hilde") == (
        {"action": "wait"},
        "you already said that",
    )
    world = world_with(Jonas=at(hx + 1, hy), Hilde={"said": [*said[1:], "Bye."]})
    assert parse_action('{"action": "say", "text": "where are the fish"}', world, "Hilde") == (
        {"action": "say", "text": "where are the fish", "to": None},
        None,
    )


def test_a_goodbye_repeating_a_line_keeps_the_goodbye_without_the_text() -> None:
    world = world_with(Hilde={"said": ["See you later!"]})
    answer = '{"action": "goodbye", "text": "See you later", "place": "market"}'
    assert parse_action(answer, world, "Hilde") == (
        {"action": "goodbye", "text": None, "place": "market"},
        None,
    )


def test_the_observation_lists_what_the_villager_said_lately() -> None:
    text = observation(world_with(Jonas={"said": ["Fresh fish!", "Anyone?"]}), "Jonas")
    assert 'What you said lately:\n- "Fresh fish!"\n- "Anyone?"\n' in text
    assert text.index("Places: ") < text.index("What you said lately:")
    assert text.index("What you said lately:") < text.index("Where the others are")
    assert "What you said lately:\n- nothing yet\n" in observation(world_with(), "Jonas")


def test_a_long_line_repeats_what_was_spoken_of_it() -> None:
    hx, hy = door("Hilde")
    long = "Fish " * 50
    world = world_with(Jonas=at(hx + 1, hy), Hilde={"said": [long[:SPEECH_SHOWN]]})
    answer = json.dumps({"action": "say", "text": long})
    assert parse_action(answer, world, "Hilde")[1] == "you already said that"


def test_work_where_there_is_work() -> None:
    fields = place_cells("fields")[0]
    world = world_with(Greta=at(*fields))
    assert parse_action('{"action": "work"}', world, "Greta") == (
        {"action": "work", "place": "fields"},
        None,
    )
    assert parse_action('{"action": "work"}', world_with(), "Greta") == (
        {"action": "wait"},
        "there is no work for you here",
    )
    pier = place_cells("pier")[0]
    assert parse_action('{"action": "work"}', world_with(Hilde=at(*pier)), "Hilde") == (
        {"action": "wait"},
        "only Jonas fishes here; work with him while he fishes",
    )


def test_working_while_talking_is_allowed() -> None:
    fx, fy = place_cells("fields")[0]
    world = world_with(Greta=at(fx, fy), Lina=at(fx + 1, fy))
    world["conversations"] = [{"a": "Greta", "b": "Lina", "lines": 2, "last_tick": 30}]
    assert parse_action('{"action": "work"}', world, "Greta")[1] is None


def test_give_to_a_villager_or_onto_the_stalls() -> None:
    sx, sy = label_cell("square")
    world = world_with(Hilde={**at(sx, sy), "basket": "fish"}, Jonas=at(sx + 1, sy))
    assert parse_action('{"action": "give", "to": "jonas"}', world, "Hilde") == (
        {"action": "give", "to": "Jonas", "goods": "fish"},
        None,
    )
    assert parse_action('{"action": "give"}', world, "Hilde") == (
        {"action": "give", "to": None, "goods": "fish"},
        None,
    )
    assert parse_action('{"action": "give"}', world, "Jonas") == (
        {"action": "wait"},
        "your hands are empty",
    )


def test_the_facts_name_work_the_basket_and_in_autumn_the_stalls() -> None:
    fields = place_cells("fields")[0]
    autumn = _at(15, 9)
    world = world_with(
        tick=autumn,
        Greta={**at(*fields), "working": {"place": "fields", "steps": 2}, "basket": "vegetables"},
    )
    world["stalls"]["fish"] = 1
    facts = observation(world, "Greta").split("What others told you")[0]
    assert "You are at the fields. You are working here." in facts
    assert "You carry a basket of vegetables." in facts
    assert (
        "The festival stalls on the square hold fish; they still lack vegetables and flowers."
        in facts
    )
    summer = observation(world_with(tick=_at(8, 9)), "Greta")
    assert (
        "festival stalls" not in summer
        and "You carry" not in summer
        and "working here" not in summer
    )


def test_the_rules_describe_work_and_give() -> None:
    rules = villager_agent("Jonas")["config"]["blocks"][0]["system"]
    assert '{"action": "work"}' in rules
    assert '{"action": "give", "to": "Hilde"}' in rules
    assert '{"action": "give"} on the square' in rules


def test_in_autumn_a_carried_basket_is_meant_for_the_stalls() -> None:
    fields = place_cells("fields")[0]
    world = world_with(tick=_at(15, 9), Greta={**at(*fields), "basket": "vegetables"})
    facts = observation(world, "Greta").split("What others told you")[0]
    assert (
        "The stalls still lack vegetables. Take your basket to the square and set it out on the "
        "festival stalls." in facts
    )
    world["stalls"]["vegetables"] = 1
    facts = observation(world, "Greta").split("What others told you")[0]
    assert "still lack vegetables" not in facts
    assert "Take your basket to the square and set it out on the festival stalls." in facts
    sx, sy = label_cell("square")
    villager_at_square = world_with(tick=_at(15, 9), Greta={**at(sx, sy), "basket": "vegetables"})
    assert (
        "You are on the square: set out your vegetables on the festival stalls now with "
        '{"action": "give"}.' in observation(villager_at_square, "Greta")
    )
    summer = observation(world_with(tick=_at(8, 9), Greta={"basket": "vegetables"}), "Greta")
    assert "You carry a basket of vegetables." in summer and "festival stalls" not in summer


TRADER = {"day": 1, "stock": {"wood": 3, "paint": 0, "saplings": 1}}


def test_buy_a_load_for_the_basket_carried() -> None:
    world = world_with(Lina={**at(*MARKET), "basket": "flowers"})
    world["trader"] = TRADER
    assert parse_action('{"action": "buy", "goods": "Wood"}', world, "Lina") == (
        {"action": "buy", "goods": "wood", "paid": "flowers"},
        None,
    )


@pytest.mark.parametrize(
    ("goods", "changes", "reason"),
    [
        ("stone", {}, "the trader sells wood, paint and saplings"),
        ("paint", {}, "the trader has no paint left"),
        ("wood", {"basket": None}, "you have nothing to trade: bring a basket"),
        ("wood", {"basket": "saplings"}, "you already carry a load of saplings"),
        ("wood", {"x": 0, "y": 1}, "the trader is at the market"),
    ],
)
def test_buy_refused(goods: str, changes: dict[str, Any], reason: str) -> None:
    world = world_with(Lina={**at(*MARKET), "basket": "flowers", **changes})
    world["trader"] = TRADER
    answer = json.dumps({"action": "buy", "goods": goods})
    assert parse_action(answer, world, "Lina") == ({"action": "wait"}, reason)


def test_buy_without_a_trader_is_refused() -> None:
    world = world_with(tick=_at(1, 15), Lina={**at(*MARKET), "basket": "flowers"})
    assert parse_action('{"action": "buy", "goods": "wood"}', world, "Lina") == (
        {"action": "wait"},
        "no trader is at the market now; one comes every day from 09:00 to 14:00",
    )


def test_the_facts_name_the_trader_and_a_carried_load() -> None:
    early = observation(world_with(tick=_at(1, 7), Lina={"basket": "wood"}), "Lina")
    facts = early.split("What others told you")[0]
    assert "A trader comes to the market today from 09:00 to 14:00." in facts
    assert "You carry a load of wood." in facts
    world = world_with()
    world["trader"] = TRADER
    assert "A trader is at the market until 14:00, selling wood (3) and saplings (1);" in (
        observation(world, "Lina")
    )
    late = observation(world_with(tick=_at(1, 15)), "Lina")
    assert "The trader has left; the next one comes tomorrow at 09:00." in late


def test_the_rules_describe_buy() -> None:
    rules = villager_agent("Jonas")["config"]["blocks"][0]["system"]
    assert '{"action": "buy", "goods": "wood"} at the market while the trader is there' in rules


def test_the_facts_name_the_town_hall_meeting() -> None:
    facts = observation(world_with(), "Greta").split("What others told you")[0]
    assert "The next town hall meeting is on day 3 at 17:00." in facts
    on_the_day = observation(world_with(tick=_at(3, 9)), "Hilde")
    assert "You chair today's town hall meeting at 17:00; be there." in on_the_day
