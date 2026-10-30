"""Fake, deterministic weather: the same city always gets the same report."""

import hashlib
import json

from agent_lab.tools.base import Tool, ToolError

_CONDITIONS = ["sunny", "cloudy", "rain", "snow", "fog", "windy"]


def get_weather(city: str) -> str:
    if not isinstance(city, str) or not city.strip() or len(city) > 100:
        raise ToolError("city must be a non-empty string of at most 100 characters")
    name = city.strip()
    digest = hashlib.sha256(name.lower().encode()).digest()
    return json.dumps(
        {
            "city": name,
            "temperature_c": digest[0] % 46 - 10,  # -10..35
            "condition": _CONDITIONS[digest[1] % len(_CONDITIONS)],
        }
    )


WEATHER = Tool(
    name="get_weather",
    description="Get the current weather for a city (temperature in Celsius and condition).",
    parameters={
        "type": "object",
        "properties": {"city": {"type": "string", "description": "City name, e.g. Berlin"}},
        "required": ["city"],
        "additionalProperties": False,
    },
    fn=get_weather,
)
