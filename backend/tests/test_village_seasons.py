"""The village calendar, light and weather (M10, FR-007 to FR-009, SC-002)."""

from typing import Any

import pytest

from agent_lab.village import seasons
from agent_lab.village.seasons import (
    FIELD_NEWS,
    SEASONS,
    WEATHER,
    dark,
    date,
    date_text,
    end_day,
    festival_in,
    growth_text,
    neglected,
    sky,
    snow_cover,
    weather,
)
from agent_lab.village.world import new_world


def test_a_year_has_four_seasons_of_seven_days_from_spring() -> None:
    assert date(1) == (1, "spring", 1)
    assert date(7) == (1, "spring", 7)
    assert date(8) == (1, "summer", 1)
    assert date(15) == (1, "autumn", 1)
    assert date(22) == (1, "winter", 1)
    assert date(28) == (1, "winter", 7)
    assert date(29) == (2, "spring", 1)
    assert date_text(17) == "day 3 of autumn, year 1"


def test_the_festival_counts_down_through_autumn() -> None:
    assert [festival_in(d) for d in range(15, 22)] == [6, 5, 4, 3, 2, 1, 0]
    assert festival_in(14) is None and festival_in(22) is None
    assert festival_in(21 + 28) == 0  # every year


def test_light_follows_the_seasons_sun() -> None:
    summer, winter = 8, 22
    assert not dark(summer, 5 * 60) and dark(winter, 5 * 60)
    assert dark(winter, 17 * 60) and not dark(summer, 17 * 60)
    assert sky(winter, 7 * 60) == "night" and sky(summer, 7 * 60) == "morning"
    assert sky(winter, 15 * 60) == "evening" and sky(summer, 15 * 60) == "afternoon"
    assert sky(summer, 12 * 60) == "midday"
    assert sky(summer, 22 * 60) == "night"


def test_every_day_has_one_weather_its_season_allows_and_the_same_each_time() -> None:
    days = range(1, 2 * 28 + 1)
    first = [weather(d) for d in days]
    assert first == [weather(d) for d in days]  # reproducible (SC-002)
    for d, kind in zip(days, first, strict=True):
        season = "festival" if festival_in(d) == 0 else date(d)[1]
        assert kind in WEATHER[season], (d, kind)
    assert "snow" not in [weather(d) for d in days if date(d)[1] == "summer"]
    seen = {date(d)[1] for d in days}
    assert seen == set(SEASONS)


def test_the_festival_day_is_never_wet() -> None:
    assert all(weather(21 + 28 * year) in ("sun", "clouds") for year in range(20))


def test_snow_lies_on_a_snowy_day_and_the_day_after() -> None:
    snowy = next(d for d in range(22, 28 * 10) if weather(d) == "snow")
    assert snow_cover(snowy) and snow_cover(snowy + 1)
    dry = next(d for d in range(2, 28 * 10) if "snow" not in (weather(d), weather(d - 1)))
    assert not snow_cover(dry)


# --- growth (US4, FR-011 to FR-015, SC-003) ---


def _year(
    monkeypatch: pytest.MonkeyPatch | None = None,
    sky: str | None = None,
    fields: bool = True,
    garden: bool = False,
) -> tuple[dict[str, Any], dict[int, tuple[str, str]], list[str]]:
    """A scripted year of `end_day`: the stages after each day, and all the news."""
    if monkeypatch and sky:
        monkeypatch.setattr(seasons, "weather", dict.fromkeys(range(30), sky).__getitem__)
    world = new_world()
    stages: dict[int, tuple[str, str]] = {}
    news: list[str] = []
    for day in range(1, 29):
        world["tended"] = {"fields": 6 if fields else 0, "flower_garden": 6 if garden else 0}
        news += end_day(world, day)
        stages[day] = (
            world["growth"]["fields"]["stage"],
            world["growth"]["flower_garden"]["stage"],
        )
    return world, stages, news


def test_fields_tended_daily_without_rain_are_harvested_before_the_festival(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, stages, news = _year(monkeypatch, "sun")
    firsts = {stage: min(d for d, (s, _) in stages.items() if s == stage) for stage in FIELD_NEWS}
    assert firsts == {
        "tilled": 1,
        "sown": 2,
        "sprouting": 5,
        "growing": 10,
        "ripe": 16,
        "harvested": 17,  # before the festival on day 21 (SC-003)
    }
    assert stages[20][0] == "harvested" and stages[21][0] == "resting"  # winter comes after day 21
    assert "The harvest was brought in." in news


def test_rain_doubles_a_tended_days_growth(monkeypatch: pytest.MonkeyPatch) -> None:
    _, stages, _ = _year(monkeypatch, "rain")
    assert [stages[d][0] for d in (2, 3, 4)] == ["sown", "sown", "sprouting"]  # 2 + 2 >= 3
    assert stages[15][0] == "harvested"  # ripe early, harvested on the first autumn day


def test_with_the_real_weather_daily_tending_still_harvests_before_the_festival() -> None:
    _, stages, _ = _year()
    assert stages[20][0] == "harvested"


def test_untended_fields_stay_resting_all_year() -> None:
    world, stages, news = _year(fields=False)
    assert {s for s, _ in stages.values()} == {"resting"}
    assert not neglected(world["growth"])
    assert not any(n in news for n in FIELD_NEWS.values())


def test_growing_fields_left_alone_for_two_days_are_neglected_until_tended() -> None:
    world = new_world()
    world["growth"]["fields"] |= {"stage": "sprouting", "progress": 1}
    end_day(world, 9)
    assert world["growth"]["fields"]["untended"] == 1 and not neglected(world["growth"])
    end_day(world, 10)
    assert neglected(world["growth"])
    assert "nobody has tended them for 2 days" in growth_text("fields", world["growth"])
    world["tended"]["fields"] = 6
    end_day(world, 11)
    assert not neglected(world["growth"])


def test_unharvested_ripe_fields_are_lost_when_winter_comes() -> None:
    world = new_world()
    world["growth"]["fields"]["stage"] = "ripe"
    news = end_day(world, 21)  # the last day of autumn, untended
    assert world["growth"]["fields"]["stage"] == "resting"
    assert world["growth"]["flower_garden"]["stage"] == "resting"
    assert "The unharvested crop was lost to the frost." in news


def test_tending_in_winter_does_nothing() -> None:
    world = new_world()
    world["growth"] = seasons.new_growth("winter")
    world["tended"] = {"fields": 30, "flower_garden": 30}
    assert end_day(world, 24) == []
    assert world["growth"] == seasons.new_growth("winter")


def test_spring_buds_the_garden() -> None:
    world = new_world()
    world["growth"] = seasons.new_growth("winter")
    assert end_day(world, 28) == ["Spring came: the flower garden is budding."]
    assert world["growth"]["flower_garden"]["stage"] == "budding"


def test_a_dry_garden_wilts_and_recovers_with_rain_or_a_visit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sky = {9: "sun", 10: "sun", 11: "rain", 12: "sun", 13: "sun"}
    monkeypatch.setattr(seasons, "weather", sky.__getitem__)
    world = new_world()
    world["growth"] = seasons.new_growth("summer")  # blooming
    end_day(world, 9)
    assert world["growth"]["flower_garden"]["stage"] == "blooming"
    assert end_day(world, 10) == ["The flowers in the garden are wilting."]
    assert end_day(world, 11) == ["The flower garden is in bloom."]  # rain
    for day in (12, 13):  # a neighbour waters it on dry days
        world["tended"]["flower_garden"] = 6
        end_day(world, day)
    assert world["growth"]["flower_garden"]["stage"] == "blooming"


def test_budding_flowers_bloom_after_two_watered_days(monkeypatch: pytest.MonkeyPatch) -> None:
    _, stages, _ = _year(monkeypatch, "sun", fields=False, garden=True)
    assert [stages[d][1] for d in (1, 2, 20, 21)] == ["budding", "blooming", "blooming", "resting"]
