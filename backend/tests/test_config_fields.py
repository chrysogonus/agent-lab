import pytest
from pydantic import BaseModel, ValidationError

from agent_lab.agents.config_fields import (
    BlockName,
    ItemName,
    Prompt,
    ShortText,
    fill,
    known_tool,
    unique,
)


class Fields(BaseModel):
    prompt: Prompt = "p"
    text: ShortText = "t"
    name: ItemName = "n"


@pytest.mark.parametrize("value", ["", "   ", "x" * 4001])
def test_prompt_rejected(value: str) -> None:
    with pytest.raises(ValidationError):
        Fields(prompt=value)


def test_prompt_limits_and_trimming() -> None:
    assert Fields(prompt="x" * 4000).prompt == "x" * 4000
    assert Fields(prompt="  a  ").prompt == "a"


def test_short_text_limit() -> None:
    Fields(text="x" * 300)
    with pytest.raises(ValidationError):
        Fields(text="x" * 301)


@pytest.mark.parametrize("name", ["poem", "step-2", "a", "x" * 30])
def test_item_name_ok(name: str) -> None:
    assert Fields(name=name).name == name


@pytest.mark.parametrize("name", ["", "Poem", "two words", "x" * 31, "tool:x", "start", "merge"])
def test_item_name_rejected(name: str) -> None:
    with pytest.raises(ValidationError):
        Fields(name=name)


def test_known_tool() -> None:
    assert known_tool("calculator") == "calculator"
    with pytest.raises(ValueError, match="unknown tool"):
        known_tool("read_file")


def test_unique() -> None:
    unique(["a", "b"], "route")
    with pytest.raises(ValueError, match="duplicate route 'a'"):
        unique(["a", "b", "a"], "route")


def test_fill_keeps_other_braces() -> None:
    text = 'Review {aspect}. Reply like {"a": 1} for {aspect}.'
    assert fill(text, aspect="tone") == 'Review tone. Reply like {"a": 1} for tone.'


class Named(BaseModel):
    name: BlockName


@pytest.mark.parametrize("name", ["gate", "router", "merge", "calc-2"])
def test_block_name_ok(name: str) -> None:
    assert Named(name=name).name == name  # template-internal names are free for blocks


@pytest.mark.parametrize("name", ["start", "end", "input", "previous", "feedback", "item", "A"])
def test_block_name_rejected(name: str) -> None:
    with pytest.raises(ValidationError):
        Named(name=name)
