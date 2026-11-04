"""Settings from environment variables: one block per model provider, one default switch."""

import os
from collections.abc import Mapping
from dataclasses import dataclass

# Names used before the provider blocks, and what replaced them.
_RENAMED = {
    "LLM_PROVIDER": "LLM_PROVIDER is gone: DEFAULT_MODEL picks the provider",
    "LLM_BASE_URL": "LLM_BASE_URL is now LOCAL_BASE_URL",
    "LLM_MODEL": "LLM_MODEL is now LOCAL_MODELS",
    "LLM_MODELS": "LLM_MODELS is now LOCAL_MODELS",
    "LLM_API_KEY": "LLM_API_KEY is now LOCAL_API_KEY",
}


def _ids(name: str, default: str) -> tuple[str, ...]:
    """A comma-separated list of model ids; blanks dropped."""
    raw = os.environ.get(name, default)
    return tuple(i.strip() for i in raw.split(",") if i.strip())


def renamed_settings(environ: Mapping[str, str]) -> list[str]:
    """One line per old setting name still set, saying what replaced it."""
    return [message for name, message in _RENAMED.items() if name in environ]


@dataclass(frozen=True)
class Settings:
    local_base_url: str
    local_models: tuple[str, ...]  # the first is the local default
    db_path: str
    local_api_key: str = ""
    openai_api_key: str = ""
    openai_models: tuple[str, ...] = ()
    openai_base_url: str = "https://api.openai.com/v1"
    openai_reasoning_off: str = "none"  # reasoning_effort sent with thinking off; "" sends none
    anthropic_api_key: str = ""
    anthropic_models: tuple[str, ...] = ()
    anthropic_base_url: str = "https://api.anthropic.com/v1"
    anthropic_workspace_id: str = ""  # only for keys not scoped to a workspace
    default_model: str = ""  # provider/model; "" means the first local model
    mcp_servers_file: str = ""  # "" means data/mcp.json, else the committed mcp.json

    @classmethod
    def from_env(cls) -> "Settings":
        local_models = _ids("LOCAL_MODELS", "qwen3.5-9b") or ("qwen3.5-9b",)
        return cls(
            local_base_url=os.environ.get("LOCAL_BASE_URL", "http://localhost:8001/v1"),
            local_models=local_models,
            local_api_key=os.environ.get("LOCAL_API_KEY", ""),
            db_path=os.environ.get("AGENT_LAB_DB", "data/agent_lab.db"),
            openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
            openai_models=_ids("OPENAI_MODELS", "gpt-6-luna"),
            openai_base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            openai_reasoning_off=os.environ.get("OPENAI_REASONING_OFF", "none"),
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            anthropic_models=_ids("ANTHROPIC_MODELS", "claude-haiku-5-5,claude-sonnet-5-5"),
            anthropic_base_url=os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1"),
            anthropic_workspace_id=os.environ.get("ANTHROPIC_WORKSPACE_ID", ""),
            default_model=os.environ.get("DEFAULT_MODEL") or f"local/{local_models[0]}",
            mcp_servers_file=os.environ.get("MCP_SERVERS_FILE", ""),
        )
