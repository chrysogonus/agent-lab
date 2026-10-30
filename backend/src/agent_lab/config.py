"""Settings from environment variables."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    llm_provider: str
    llm_base_url: str
    llm_model: str
    llm_api_key: str
    db_path: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            llm_provider=os.environ.get("LLM_PROVIDER", "openai_compat"),
            llm_base_url=os.environ.get("LLM_BASE_URL", "http://localhost:8001/v1"),
            llm_model=os.environ.get("LLM_MODEL", "qwen3.5-9b"),
            llm_api_key=os.environ.get("LLM_API_KEY", ""),
            db_path=os.environ.get("AGENT_LAB_DB", "data/agent_lab.db"),
        )
