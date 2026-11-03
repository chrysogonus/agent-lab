"""Observations, actions, beliefs and the villager agents (FR-009, FR-010, FR-014 to FR-016)."""

import json
from typing import Any

import pytest

from agent_lab.blocks.model import BlocksConfig, layout_errors
from agent_lab.village.build import new_project
from agent_lab.village.intention import start
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
from agent_lab.village.world import (
    VILLAGERS,
    door,
    label,
    label_cell,
    new_world,
    place_cells,
    steps_to,
)

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
    assert "Next to you: Hilde." in text
    assert "In sight: Lina (3 steps away)." in text
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
        ('{"action": "find", "villager": "Jonas"}', "Jonas is right next to you"),
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
    for example in ('{"action": "wait"}', '{"action": "bring"}'):
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


def test_setting_out_elsewhere_while_talking_says_goodbye_and_goes() -> None:
    """M14 (FR-009): no more "say goodbye first"."""
    hx, hy = door("Hilde")
    world = with_project("trees_square", saplings=1)
    world["villagers"][1] |= at(hx + 1, hy)
    world["conversations"] = [{"a": "Jonas", "b": "Hilde", "lines": 1, "last_tick": 30}]
    leaving = {"action": "goodbye", "text": None}
    assert parsed({"action": "move", "place": "market"}, world, "Hilde") == (
        leaving | {"place": "market"},
        None,
    )
    assert parsed({"action": "find", "villager": "Lina", "say": "Hi"}, world, "Hilde") == (
        leaving | {"villager": "Lina", "say": "Hi"},
        None,
    )
    assert parsed({"action": "build", "until": "12:00"}, world, "Hilde") == (
        leaving | {"then": {"action": "build", "until": 720}},
        None,
    )
    assert parsed({"action": "work", "place": "fields"}, world, "Hilde") == (
        leaving | {"then": {"action": "work", "place": "fields"}},
        None,
    )
    world["villagers"][3] |= at(hx + 4, hy)  # Lina in sight
    assert parsed({"action": "say", "text": "Lina!", "to": "Lina"}, world, "Hilde") == (
        leaving | {"villager": "Lina", "say": "Lina!"},
        None,
    )
    rules = villager_agent("Hilde")["config"]["blocks"][0]["system"]
    assert '"place": "market"} to end a conversation and leave' in rules
    assert "say goodbye before you walk off" not in rules
    assert "If you set out elsewhere while you talk, you say goodbye and go" in rules


def test_setting_out_where_the_other_talker_goes_keeps_the_talk() -> None:
    hx, hy = door("Hilde")
    world = world_with(Jonas=at(hx + 1, hy))
    world["conversations"] = [{"a": "Jonas", "b": "Hilde", "lines": 1, "last_tick": 30}]
    world["villagers"][1]["intention"] = start(
        world, "Jonas", {"action": "move", "place": "market"}
    )
    assert parsed({"action": "move", "place": "market"}, world, "Hilde") == (
        {"action": "move", "place": "market"},
        None,
    )


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
    asked = [{"from": "Jonas", "goods": "fish", "tick": 30}]
    world = world_with(
        Hilde={**at(sx, sy), "basket": "fish", "requests": asked}, Jonas=at(sx + 1, sy)
    )
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
    assert '{"action": "work", "place": "fields", "until": "12:00"}' in rules
    assert (
        '{"action": "give", "to": "Hilde"} to hand what you carry to someone next to you who'
        in rules
    )
    assert '{"action": "give"} on the square' in rules


def test_in_autumn_a_carried_basket_is_meant_for_the_stalls() -> None:
    fields = place_cells("fields")[0]
    world = world_with(tick=_at(15, 9), Greta={**at(*fields), "basket": "vegetables"})
    facts = observation(world, "Greta").split("What others told you")[0]
    assert "they still lack fish, vegetables and flowers." in facts
    assert "Take your basket" not in facts  # M14: the hint left; what you can do says it
    sx, sy = label_cell("square")
    villager_at_square = world_with(tick=_at(15, 9), Greta={**at(sx, sy), "basket": "vegetables"})
    assert (
        '- {"action": "give"}: the festival stalls still lack vegetables: set yours out now'
        in observation(villager_at_square, "Greta")
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


def with_project(key: str = "market_stand", **site: int) -> dict[str, Any]:
    world = world_with()
    world["project"] = new_project(key, 1)
    world["project"]["site"] |= site
    return world


def test_work_and_give_at_the_building_site() -> None:
    world = with_project(wood=1)
    world["villagers"][2] |= {**at(*MARKET), "basket": "paint"}
    assert parse_action('{"action": "work"}', world, "Greta") == (
        {"action": "work", "place": "site"},
        None,
    )
    assert parse_action('{"action": "give"}', world, "Greta") == (
        {"action": "give", "to": None, "goods": "paint"},
        None,
    )


def test_walking_to_the_building_site() -> None:
    world = with_project("bakehouse")
    for text in ("building site", "the site", "Building Site"):
        assert parse_action(json.dumps({"action": "move", "place": text}), world, "Lina") == (
            {"action": "move", "place": "site"},
            None,
        )
    places = observation(world, "Lina").split("Places: ")[1].split("\n")[0]
    assert "building site " in places and places.endswith("steps.")
    nothing = world_with()
    assert parse_action('{"action": "move", "place": "building site"}', nothing, "Lina") == (
        {"action": "wait"},
        "nothing is being built",
    )
    assert "building site" not in observation(nothing, "Lina").split("Places: ")[1]
    world["villagers"][3] |= at(14, 12)
    assert parse_action('{"action": "move", "place": "site"}', world, "Lina") == (
        {"action": "wait"},
        "already at the building site",
    )


# --- M14: answers that start intentions (FR-001) ---


def parsed(answer: dict[str, Any], world: dict[str, Any], name: str) -> tuple[Any, str | None]:
    return parse_action(json.dumps(answer), world, name)


def test_work_somewhere_else_until_a_time() -> None:
    world = world_with()  # Greta at her door, 09:30
    assert parsed(
        {"action": "work", "place": "the fields", "until": "12:00", "purpose": "weed"},
        world,
        "Greta",
    ) == ({"action": "work", "place": "fields", "until": 720, "purpose": "weed"}, None)
    assert parsed({"action": "work", "place": "pier"}, world, "Greta") == (
        {"action": "wait"},
        "only Jonas fishes here; work with him while he fishes",
    )
    assert parsed({"action": "work", "place": "market"}, world, "Greta") == (
        {"action": "wait"},
        "there is no work for you at the market",
    )
    assert parsed({"action": "work", "place": "harbour"}, world, "Greta") == (
        {"action": "wait"},
        "unknown place 'harbour'",
    )


@pytest.mark.parametrize(
    ("until", "why"),
    [
        ("noon", "\"until\" must be a time like 12:00, not 'noon'"),
        ("25:00", "\"until\" must be a time like 12:00, not '25:00'"),
        ("08:00", '"until" must be later than now (09:30)'),
    ],
)
def test_until_must_be_a_later_time(until: str, why: str) -> None:
    fields = place_cells("fields")[0]
    world = world_with(Greta=at(*fields))
    assert parsed({"action": "work", "until": until}, world, "Greta") == ({"action": "wait"}, why)


def test_build_needs_a_project_and_something_to_build_with() -> None:
    assert parsed({"action": "build"}, world_with(), "Greta") == (
        {"action": "wait"},
        "nothing is being built",
    )
    empty = with_project("trees_square")
    assert parsed({"action": "build"}, empty, "Greta") == (
        {"action": "wait"},
        "the building site has nothing to work with yet: bring goods first",
    )
    empty["villagers"][2]["basket"] = "saplings"
    assert parsed({"action": "build", "until": "15:00"}, empty, "Greta") == (
        {"action": "build", "until": 900},
        None,
    )
    held = with_project("trees_square", saplings=2)
    assert parsed({"action": "build"}, held, "Lina") == ({"action": "build"}, None)


def test_bring_needs_a_load_the_site_still_needs() -> None:
    world = with_project("trees_square")
    assert parsed({"action": "bring"}, world_with(), "Jonas") == (
        {"action": "wait"},
        "nothing is being built",
    )
    assert parsed({"action": "bring"}, world, "Jonas") == (
        {"action": "wait"},
        "your hands are empty",
    )
    world["villagers"][1]["basket"] = "wood"
    assert parsed({"action": "bring"}, world, "Jonas") == (
        {"action": "wait"},
        "you carry nothing the building site needs",
    )
    world["villagers"][1]["basket"] = "saplings"
    assert parsed({"action": "bring", "purpose": "trees"}, world, "Jonas") == (
        {"action": "bring", "purpose": "trees"},
        None,
    )


def test_find_with_a_line_to_say() -> None:
    answer = {"action": "find", "villager": "Lina", "say": " Any flowers? " + "x" * 300}
    action, why = parsed(answer, world_with(), "Hilde")
    assert why is None and action["villager"] == "Lina"
    assert action["say"] == ("Any flowers? " + "x" * 300)[:SPEECH_SHOWN]
    blank = parsed({"action": "find", "villager": "Lina", "say": " "}, world_with(), "Hilde")
    assert blank == ({"action": "find", "villager": "Lina"}, None)


# --- M14: the observation (FR-004) ---


def test_the_observation_shows_the_intention_and_what_you_can_do_here() -> None:
    fields = place_cells("fields")[0]
    world = world_with(Greta=at(*fields))
    world["growth"]["fields"]["stage"] = "growing"
    text = observation(world, "Greta")
    assert "\nYou are not set on anything.\n" in text
    assert (
        "What you can do here:\n"
        '- {"action": "work"}: you can work the fields here; an hour of work tends them\n'
    ) in text
    assert text.index("Places: ") < text.index("What you can do here:")
    assert text.index("What you can do here:") < text.index("What you said lately:")
    greta = world["villagers"][2]
    greta["intention"] = start(world, "Greta", {"action": "work", "until": 720})
    assert "You are set on: work at the fields until 12:00. Next: start working." in observation(
        world, "Greta"
    )


def test_the_building_hints_left_the_observation() -> None:
    world = with_project("trees_square", saplings=2)
    world["villagers"][1] |= {"basket": "saplings"}
    facts = observation(world, "Jonas")
    for hint in ("go and build", "set it down there", "set down your load of", "build here"):
        assert hint not in facts
    assert '- {"action": "build"}: the building site holds 2 saplings' in facts
    assert '- {"action": "bring"}: the building site still needs the saplings you carry' in facts


def test_build_at_the_site_is_work_there() -> None:
    """The same answer as M12's work at the site, so the M13 check build-with-loads holds."""
    world = with_project("trees_square", saplings=2)
    world["villagers"][2] |= at(18, 10)
    assert parsed({"action": "build", "until": "15:00"}, world, "Greta") == (
        {"action": "work", "place": "site", "until": 900},
        None,
    )


# --- M14 US2: reaching each other (FR-005, FR-006) ---


def test_a_say_to_someone_in_sight_becomes_a_find_that_says_it() -> None:
    mx, my = MARKET
    world = world_with(Jonas=at(mx, my), Greta=at(mx + 3, my + 1))
    answer = {"action": "say", "text": "Any vegetables?", "to": "Greta"}
    assert parsed(answer, world, "Jonas") == (
        {"action": "find", "villager": "Greta", "say": "Any vegetables?"},
        None,
    )
    world["villagers"][2]["asleep"] = True
    assert parsed(answer, world, "Jonas") == ({"action": "wait"}, "Greta is not next to you")


def test_finding_someone_next_to_you_is_a_wait_with_a_hint() -> None:
    hx, hy = door("Hilde")
    world = world_with(Jonas=at(hx + 1, hy))
    assert parsed({"action": "find", "villager": "Jonas"}, world, "Hilde") == (
        {"action": "wait"},
        'Jonas is right next to you; say what you want: {"action": "say", "to": "Jonas", ...}',
    )


def test_on_the_building_site_the_observation_says_so() -> None:
    """The M12 hints said it; without them a villager at the site thought it was elsewhere."""
    world = with_project("trees_square")
    world["villagers"][3] |= at(18, 10)
    assert "\nYou are at the building site.\n" in observation(world, "Lina")


@pytest.mark.parametrize("to", ["festival stalls", "the stalls", "Festival stall"])
def test_giving_to_the_stalls_or_the_site_by_name_is_giving_there(to: str) -> None:
    sx, sy = label_cell("square")
    world = world_with(Jonas={**at(sx, sy), "basket": "fish"})
    expected = {"action": "give", "to": None, "goods": "fish"}
    assert parsed({"action": "give", "to": to}, world, "Jonas") == (expected, None)
    site = with_project("trees_square")
    site["villagers"][1] |= {**at(18, 10), "basket": "saplings"}
    assert parsed({"action": "give", "to": "the building site"}, site, "Jonas") == (
        {"action": "give", "to": None, "goods": "saplings"},
        None,
    )


# --- M14 cleanup ---


def test_until_now_means_no_end_time() -> None:
    fields = place_cells("fields")[0]
    world = world_with(Greta=at(*fields))
    assert parsed({"action": "work", "until": "09:30"}, world, "Greta") == (
        {"action": "work", "place": "fields"},
        None,
    )


@pytest.mark.parametrize(
    ("answer", "place"),
    [
        ({"action": "walk", "place": "square"}, "square"),
        ({"action": "go", "place": "the pier"}, "pier"),
        ({"action": "home"}, "home"),
        ({"action": "go home"}, "home"),
        ({"action": "Walk", "place": "fields"}, "fields"),
    ],
)
def test_common_slips_for_move_are_moves(answer: dict[str, Any], place: str) -> None:
    world = world_with(Hilde=at(*MARKET))
    assert parsed(answer, world, "Hilde") == ({"action": "move", "place": place}, None)


# --- M15: happenings in a villager's turn (FR-002, FR-003, FR-014) ---


def goat_next_to_jonas(world: dict[str, Any]) -> dict[str, Any]:
    jonas = world["villagers"][1]
    goat = {
        "kind": "animal",
        "place": "market",
        "cell": [jonas["x"] + 1, jonas["y"]],
        "start": 540,
        "end": 1140,
        "concerns": "Greta",
        "details": {"text": "Greta's goat", "own": "your goat"},
        "state": "here",
        "by": None,
        "seen_by": ["Jonas"],
        "leader": None,
        "work": 0,
        "with_host": 0,
    }
    world["happenings"] = [goat]
    return goat


def test_lead_an_animal_next_to_you() -> None:
    world = world_with(Jonas=at(*MARKET))
    assert parsed({"action": "lead"}, world, "Jonas") == (
        {"action": "wait"},
        "there is no lost animal next to you",
    )
    goat_next_to_jonas(world)
    assert parsed({"action": "lead", "purpose": "home to Greta"}, world, "Jonas") == (
        {"action": "lead", "purpose": "home to Greta"},
        None,
    )


def test_buying_the_peddlers_curiosity_names_it_in_full() -> None:
    sx, sy = label_cell("square")
    world = world_with(Lina={**at(sx, sy), "basket": "flowers"})
    world["happenings"] = [
        {
            "kind": "peddler",
            "place": "square",
            "cell": [sx + 1, sy],
            "state": "here",
            "details": {"text": "a peddler with a fiddle", "goods": "a fiddle"},
            "by": None,
            "seen_by": [],
            "concerns": None,
            "leader": None,
        }
    ]
    assert parsed({"action": "buy", "goods": "Fiddle"}, world, "Lina") == (
        {"action": "buy", "goods": "a fiddle", "paid": "flowers"},
        None,
    )


def test_the_observation_names_happenings_seen_or_concerning_and_keepsakes() -> None:
    world = world_with(Jonas=at(*MARKET))
    goat_next_to_jonas(world)
    world["villagers"][1]["keepsakes"] = [{"name": "a lantern", "day": 1}]
    text = observation(world, "Jonas")
    assert "\nHappening: Greta's goat wandered to the market.\n" in text
    assert "You keep: a lantern." in text
    assert "Happening:" not in observation(world, "Lina")  # not seen
    greta = observation(world, "Greta")
    assert "Happening: Your goat got out and wandered off." in greta
    world["happenings"].append(
        {
            "kind": "letter",
            "place": None,
            "cell": list(door("Lina")),
            "concerns": "Lina",
            "details": {"text": "Roses sell well in town."},
            "state": "here",
            "seen_by": [],
            "leader": None,
        }
    )
    assert "Happening: A letter waits for you at home." in observation(world, "Lina")


def test_the_rules_describe_leading_and_the_peddler() -> None:
    from agent_lab.village.turn import OLD_RULES, RULES

    assert '{"action": "lead"} to take a lost animal next to you home' in RULES
    assert "the peddler's curiosity" in RULES
    assert '{"action": "lead"}' not in OLD_RULES[-1] and "Each turn lists" in OLD_RULES[-1]


# --- M15 US2: the boat (FR-006, FR-007) ---


def boat_world(**villagers: Any) -> dict[str, Any]:
    from agent_lab.village.evals.fixtures import build_world

    return build_world({"day": 66, "time": "14:00", "built": ["boat"], "villagers": villagers})


def test_row_the_boat_alone_with_someone_or_until_a_time() -> None:
    world = boat_world(Jonas={"at": "pier"}, Greta={"at": [21, 17]})
    assert parsed({"action": "row"}, world, "Jonas") == ({"action": "row"}, None)
    assert parsed({"action": "row", "with": "greta", "until": "15:00"}, world, "Jonas") == (
        {"action": "row", "with": "Greta", "until": 900},
        None,
    )
    assert parsed({"action": "row", "with": "Lina"}, world, "Jonas") == (
        {"action": "row", "ignored": "Lina is not next to you"},
        None,
    )
    assert parsed({"action": "row"}, world_with(), "Jonas") == (
        {"action": "wait"},
        "the village has no boat",
    )


def test_the_one_invited_joins_with_row() -> None:
    from agent_lab.village.boat import start_trip

    world = boat_world(Jonas={"at": "pier"}, Greta={"at": [21, 17]})
    start_trip(world, "Jonas", "Greta", None)
    assert parsed({"action": "row"}, world, "Greta") == ({"action": "row"}, None)


def test_work_in_the_boat_fishes_the_lake() -> None:
    from agent_lab.village.boat import start_trip

    world = boat_world(Jonas={"at": "pier"})
    start_trip(world, "Jonas", None, None)
    world["boat"]["state"] = "out"
    assert parsed({"action": "work"}, world, "Jonas") == ({"action": "work", "place": "lake"}, None)
    world["villagers"][1] |= {"x": 23, "y": 20}  # on the water
    text = observation(world, "Jonas")
    assert "You are out on the lake in the boat for about an hour." in text
    assert "\nYou are on the lake, in the boat.\n" in text
    assert label("lake") == "lake"
    assert "The boat is out on the lake with Jonas for about an hour." in observation(world, "Lina")


def test_the_rules_describe_rowing() -> None:
    from agent_lab.village.turn import RULES

    assert '{"action": "row", "with": "Greta"}' in RULES


def test_someone_seen_on_the_lake_is_on_the_lake() -> None:
    world = world_with()
    world["villagers"][0]["beliefs"]["Jonas"] = {
        "where": None,
        "cell": [23, 20],
        "tick": 30,
        "source": "seen",
    }
    assert belief_text(world, "Hilde", "Jonas") == "on the lake (seen 09:30)"


# --- M15: answers the real model gave (checks of 2026-11-03) ---


def visitor_for(world: dict[str, Any], host: str = "Greta") -> None:
    world["happenings"] = [
        {
            "kind": "visitor",
            "place": None,
            "cell": list(door(host)),
            "concerns": host,
            "details": {"text": "Anna, Greta's sister", "name": "Anna, your sister"},
            "state": "here",
            "seen_by": [],
            "leader": None,
        }
    ]


def test_naming_the_visitor_goes_to_where_the_visitor_is() -> None:
    world = world_with(Greta=at(*place_cells("fields")[0]))
    visitor_for(world)
    assert parsed({"action": "find", "villager": "Anna"}, world, "Greta") == (
        {"action": "move", "place": "home"},
        None,
    )
    assert parsed({"action": "say", "text": "Anna!", "to": "Anna"}, world, "Greta") == (
        {"action": "move", "place": "home"},
        None,
    )
    assert parsed({"action": "find", "villager": "Anna"}, world, "Lina") == (
        {"action": "find", "villager": "Greta"},
        None,
    )


def test_asking_someone_not_there_along_takes_the_boat_out_alone() -> None:
    world = boat_world(Jonas={"at": "pier"})
    for with_ in ("Greta", "nobody", ""):
        action, why = parsed({"action": "row", "with": with_}, world, "Jonas")
        assert why is None and action["action"] == "row" and "with" not in action
    assert parsed({"action": "row", "with": "Greta"}, world, "Jonas")[0]["ignored"] == (
        "Greta is not next to you"
    )


def test_selling_or_giving_to_the_peddler_is_trading_with_it() -> None:
    sx, sy = label_cell("square")
    world = world_with(Lina={**at(sx, sy), "basket": "flowers"})
    world["happenings"] = [
        {
            "kind": "peddler",
            "place": "square",
            "cell": [sx + 1, sy],
            "state": "here",
            "details": {"text": "a peddler with a lantern", "goods": "a lantern"},
            "by": None,
            "seen_by": [],
            "concerns": None,
            "leader": None,
        }
    ]
    trade = ({"action": "buy", "goods": "a lantern", "paid": "flowers"}, None)
    assert parsed({"action": "sell", "goods": "lantern"}, world, "Lina") == trade
    assert parsed({"action": "trade", "goods": "the lantern"}, world, "Lina") == trade
    assert parsed({"action": "give", "to": "the peddler"}, world, "Lina") == trade


def test_the_visitors_full_description_names_the_visitor_not_the_host() -> None:
    world = world_with(Greta=at(*place_cells("fields")[0]))
    visitor_for(world)
    for named in ("Anna, Greta's sister", "Anna"):
        assert parsed({"action": "find", "villager": named}, world, "Greta") == (
            {"action": "move", "place": "home"},
            None,
        ), named
    assert parsed({"action": "find", "villager": "Greta"}, world, "Lina") == (
        {"action": "find", "villager": "Greta"},
        None,
    )
