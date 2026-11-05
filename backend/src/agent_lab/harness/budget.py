"""What an agent may use per run, and what it asks about first. Kept beside its config, so that
giving an agent a budget changes no config version (specs/017-evaluation-harness/research.md §1)."""

from pydantic import BaseModel, ConfigDict, Field


class Budget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_calls: int = Field(ge=1, le=200)
    tokens: int = Field(ge=1, le=2_000_000)
    tool_calls: int = Field(ge=1, le=200)
    seconds: int = Field(ge=1, le=3_600)


DEFAULT_BUDGET = Budget(model_calls=30, tokens=200_000, tool_calls=30, seconds=600)
MAX_BUDGET = Budget(model_calls=200, tokens=2_000_000, tool_calls=200, seconds=3_600)


class Harness(BaseModel):
    budget: Budget | None = None
    ask_first: list[str] = []


class OverBudget(Exception):
    """A limit was reached: the run starts no further step."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason

    @classmethod
    def of(cls, what: str, used: int, limit: int) -> "OverBudget":
        return cls(f"{what}: {used:,} of {limit:,}")

    @classmethod
    def of_time(cls, seconds: int) -> "OverBudget":
        return cls(f"time: {seconds:,} s of {seconds:,} s")
