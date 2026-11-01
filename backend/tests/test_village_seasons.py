"""The village calendar, light and weather (M10, FR-007 to FR-009, SC-002)."""

from agent_lab.village.seasons import (
    SEASONS,
    WEATHER,
    dark,
    date,
    date_text,
    festival_in,
    sky,
    snow_cover,
    weather,
)


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
