import json

import pytest

from agent_lab.tools.base import ToolError
from agent_lab.tools.calculator import calculate
from agent_lab.tools.weather import get_weather


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("17*23", "391"),
        ("1 + 2 * 3", "7"),
        ("(1 + 2) * 3", "9"),
        ("-2**2", "-4"),
        ("2**3**2", "512"),
        ("7 / 2", "3.5"),
        ("10 / 2", "5"),
        ("7 % 3", "1"),
        (".5 + 1.25", "1.75"),
        ("--3", "3"),
        ("2**-1", "0.5"),
    ],
)
def test_calculator_evaluates(expression: str, expected: str) -> None:
    assert calculate(expression) == expected


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('id')",
        "abs(-1)",
        "x + 1",
        "1 +",
        "(1 + 2",
        "1 2",
        "2 ** 999",
        "(9**64)**64",
        "1 / 0",
        "5 % 0",
        "0 ** -1",
        "(-8) ** 0.5",
        "",
        "1" * 201,
    ],
)
def test_calculator_rejects(expression: str) -> None:
    with pytest.raises(ToolError):
        calculate(expression)


def test_weather_deterministic() -> None:
    first = json.loads(get_weather("Berlin"))
    assert first == json.loads(get_weather(" berlin ".title().strip()))
    assert set(first) == {"city", "temperature_c", "condition"}
    assert -10 <= first["temperature_c"] <= 35


def test_weather_rejects_bad_city() -> None:
    with pytest.raises(ToolError):
        get_weather("")


@pytest.mark.parametrize("value", [5, None, ["1+1"], {"x": 1}])
def test_tools_reject_non_string_arguments(value: object) -> None:
    # Model JSON can carry any type; the isinstance checks are the validation.
    with pytest.raises(ToolError):
        calculate(value)
    with pytest.raises(ToolError):
        get_weather(value)
