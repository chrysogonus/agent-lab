"""The village calendar, its light and weather, and the fields and flowers that grow from work
(specs/010-village-seasons/research.md §2-§3). Everything but growth is derived from the day."""

import random
from typing import Any

SEASONS = ("spring", "summer", "autumn", "winter")
DAYS_PER_SEASON = 7
FESTIVAL_DAY = 7  # of autumn

SUN = {  # sunrise and sunset, minutes of the day
    "spring": (6 * 60, 20 * 60),
    "summer": (5 * 60, 21 * 60 + 30),
    "autumn": (6 * 60 + 30, 19 * 60),
    "winter": (8 * 60, 17 * 60),
}

WEATHER = {  # kinds and weights
    "spring": {"sun": 4, "clouds": 3, "rain": 3},
    "summer": {"sun": 6, "clouds": 3, "storm": 1},
    "autumn": {"clouds": 3, "rain": 3, "fog": 2, "storm": 1, "sun": 1},
    "winter": {"clouds": 3, "snow": 3, "fog": 2, "sun": 2},
    "festival": {"sun": 1, "clouds": 1},
}
WEATHER_TEXT = {
    "sun": "Sunny",
    "clouds": "Cloudy",
    "rain": "Rain all day",
    "storm": "A storm with thunder and heavy rain",
    "fog": "Thick fog",
    "snow": "Snow is falling",
}
WET = ("rain", "storm")


def date(day: int) -> tuple[int, str, int]:
    """(year, season, day of the season) of village day `day` (1 is day 1 of spring, year 1)."""
    year, rest = divmod(day - 1, DAYS_PER_SEASON * len(SEASONS))
    season, day_of_season = divmod(rest, DAYS_PER_SEASON)
    return year + 1, SEASONS[season], day_of_season + 1


def date_text(day: int) -> str:
    year, season, day_of_season = date(day)
    return f"day {day_of_season} of {season}, year {year}"


def festival_in(day: int) -> int | None:
    """Days until the harvest festival while it is autumn: 0 on the day, else None."""
    _, season, day_of_season = date(day)
    return FESTIVAL_DAY - day_of_season if season == "autumn" else None


def sky(day: int, minute: int) -> str:
    """The light of the moment as one of the view's five skies, shifted by the season's sun."""
    sunrise, sunset = SUN[date(day)[1]]
    if minute < sunrise - 30 or minute >= sunset + 30:
        return "night"
    if minute >= sunset - 120:
        return "evening"
    if minute < 11 * 60:
        return "morning"
    return "midday" if minute < 14 * 60 else "afternoon"


def dark(day: int, minute: int) -> bool:
    sunrise, sunset = SUN[date(day)[1]]
    return minute < sunrise or minute >= sunset


def weather(day: int) -> str:
    """The day's weather: drawn from its season, the same every time the day comes."""
    kinds = WEATHER["festival" if festival_in(day) == 0 else date(day)[1]]
    rng = random.Random(day)  # noqa: S311 -- reproducible weather, not security
    return rng.choices(list(kinds), weights=list(kinds.values()))[0]


def snow_cover(day: int) -> bool:
    return "snow" in (weather(day), weather(day - 1) if day > 1 else None)


# --- growth ---

FIELD_STAGES = ("resting", "tilled", "sown", "sprouting", "growing", "ripe", "harvested")
GARDEN_STAGES = ("resting", "budding", "blooming", "wilting")
GROWS = {"sown": 3, "sprouting": 5, "growing": 6}  # points to the next stage
TENDED_STEPS = 6  # one village hour of awake villagers on the place
LABELS = {"fields": "fields", "flower_garden": "flower garden"}


def new_growth(season: str = "spring") -> dict[str, Any]:
    """The places as a season normally finds them: day 1 of spring, or an upgraded village."""
    fields = {"spring": "resting", "summer": "growing", "autumn": "ripe", "winter": "resting"}
    garden = {"spring": "budding", "summer": "blooming", "autumn": "blooming", "winter": "resting"}
    return {
        "fields": {"stage": fields[season], "progress": 0, "untended": 0},
        "flower_garden": {"stage": garden[season], "watered": 0, "dry": 0},
    }


def neglected(growth: dict[str, Any]) -> bool:
    fields = growth["fields"]
    return fields["stage"] in ("sprouting", "growing", "ripe") and fields["untended"] >= 2


def growth_text(place: str, growth: dict[str, Any]) -> str:
    """How a place is doing, as a villager or the chronicler is told."""
    if place == "flower_garden":
        stage = growth["flower_garden"]["stage"]
        return f"The flower garden is {'resting for the winter' if stage == 'resting' else stage}."
    fields = growth["fields"]
    stage, untended = fields["stage"], fields["untended"]
    text = f"The fields are {'ripe for harvest' if stage == 'ripe' else stage}"
    if stage in ("sown", "sprouting", "growing", "ripe") and untended:
        text += (
            "; nobody tended them yesterday"
            if untended == 1
            else (f"; nobody has tended them for {untended} days")
        )
    return text + "."


FIELD_NEWS = {
    "tilled": "The fields were tilled.",
    "sown": "The fields were sown.",
    "sprouting": "The fields sprouted.",
    "growing": "The crops are growing well.",
    "ripe": "The crops are ripe for harvest.",
    "harvested": "The harvest was brought in.",
}
GARDEN_NEWS = {
    "blooming": "The flower garden is in bloom.",
    "wilting": "The flowers in the garden are wilting.",
}


def _grow_fields(fields: dict[str, Any], tended: bool, wet: bool, season: str) -> str:
    stage = fields["stage"]
    if not tended:
        fields["untended"] += 1
        return stage
    fields["untended"] = 0
    if stage in ("resting", "tilled"):
        return FIELD_STAGES[FIELD_STAGES.index(stage) + 1]
    if stage in GROWS:
        fields["progress"] += 2 if wet else 1
        if fields["progress"] >= GROWS[stage]:
            fields["progress"] = 0
            return FIELD_STAGES[FIELD_STAGES.index(stage) + 1]
    if stage == "ripe" and season == "autumn":
        return "harvested"
    return stage


def _grow_garden(garden: dict[str, Any], watered: bool) -> str:
    stage = garden["stage"]
    if watered:
        garden["watered"] += 1
        garden["dry"] = 0
        if stage == "wilting" or (stage == "budding" and garden["watered"] >= 2):
            return "blooming"
    else:
        garden["dry"] += 1
        if stage == "blooming" and garden["dry"] >= 2:
            return "wilting"
    return stage


def end_day(world: dict[str, Any], day: int) -> list[str]:
    """Grows the fields and the flower garden for `day`, from how long awake villagers stood on
    them and the day's rain, then turns the season; returns the news for the chronicle."""
    growth, tended = world["growth"], world["tended"]
    fields, garden = growth["fields"], growth["flower_garden"]
    season, wet = date(day)[1], weather(day) in WET
    news: list[str] = []
    if season != "winter":
        stage = _grow_fields(fields, tended["fields"] >= TENDED_STEPS, wet, season)
        if stage != fields["stage"]:
            fields["stage"] = stage
            news.append(FIELD_NEWS[stage])
        stage = _grow_garden(garden, tended["flower_garden"] >= TENDED_STEPS or wet)
        if stage != garden["stage"]:
            garden |= {"stage": stage, "watered": 0, "dry": 0}
            news.append(GARDEN_NEWS[stage])
    world["tended"] = {"fields": 0, "flower_garden": 0}
    coming = date(day + 1)[1]
    if coming == "winter" and season != "winter":
        if fields["stage"] == "ripe":
            news.append("The unharvested crop was lost to the frost.")
        growth |= new_growth("winter")
        news.append("Winter came: the fields and the flower garden rest.")
    elif coming == "spring" and season == "winter":
        growth |= new_growth("spring")
        news.append("Spring came: the flower garden is budding.")
    return news
