"""Settings from environment variables."""

import os
from dataclasses import dataclass


def _ids(name: str) -> tuple[str, ...]:
    """A comma-separated list of model ids; blanks dropped."""
    return tuple(i.strip() for i in os.environ.get(name, "").split(",") if i.strip())


@dataclass(frozen=True)
class Settings:
    llm_provider: str
    llm_base_url: str
    llm_model: str
    llm_api_key: str
    db_path: str
    llm_models: tuple[str, ...] = ()
    openai_api_key: str = ""
    openai_models: tuple[str, ...] = ()
    openai_base_url: str = "https://api.openai.com/v1"
    openai_reasoning_off: str = "none"  # reasoning_effort sent with thinking off; "" sends none
    default_model: str = ""  # provider/model; "" means local/{llm_model}

    @classmethod
    def from_env(cls) -> "Settings":
        llm_model = os.environ.get("LLM_MODEL", "qwen3.5-9b")
        return cls(
            llm_provider=os.environ.get("LLM_PROVIDER", "openai_compat"),
            llm_base_url=os.environ.get("LLM_BASE_URL", "http://localhost:8001/v1"),
            llm_model=llm_model,
            llm_api_key=os.environ.get("LLM_API_KEY", ""),
            db_path=os.environ.get("AGENT_LAB_DB", "data/agent_lab.db"),
            llm_models=_ids("LLM_MODELS"),
            openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
            openai_models=_ids("OPENAI_MODELS"),
            openai_base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            openai_reasoning_off=os.environ.get("OPENAI_REASONING_OFF", "none"),
            default_model=os.environ.get("DEFAULT_MODEL") or f"local/{llm_model}",
        )
