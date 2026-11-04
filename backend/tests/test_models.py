"""Settings → the model catalog: providers, availability and the default (FR-001, FR-002)."""

from dataclasses import replace
from typing import Any

import pytest

from agent_lab.config import Settings
from agent_lab.llm.models import ModelRef, models_from_settings, parse_ref


def settings(**changes: Any) -> Settings:
    """The M3 environment, plus the given M4 settings."""
    base = Settings(
        llm_provider="openai_compat",
        llm_base_url="http://localhost:8001/v1",
        llm_model="qwen3.5-9b",
        llm_api_key="",
        db_path=":memory:",
    )
    return replace(base, **changes)


def refs(s: Settings) -> list[str]:
    return [str(e.ref) for e in models_from_settings(s).entries]


def test_m3_environment_is_one_local_model() -> None:
    models = models_from_settings(settings())
    assert refs(settings()) == ["local/qwen3.5-9b"]
    assert models.default == ModelRef(provider="local", model="qwen3.5-9b")
    entry = models.entries[0]
    assert (entry.external, entry.unavailable, entry.client.provider) == (False, None, "local")


def test_further_local_models_without_duplicates() -> None:
    s = settings(llm_models=("qwen3:8b", "qwen3.5-9b", "Qwen/Qwen3-8B"))
    assert refs(s) == ["local/qwen3.5-9b", "local/qwen3:8b", "local/Qwen/Qwen3-8B"]


def test_openai_models_with_key() -> None:
    models = models_from_settings(
        settings(openai_models=("gpt-6-luna",), openai_api_key="sk-x", llm_models=())
    )
    entry = models.entries[1]
    assert str(entry.ref) == "openai/gpt-6-luna"
    assert (entry.external, entry.unavailable, entry.client.provider) == (True, None, "openai")


def test_openai_models_without_key_are_unavailable() -> None:
    entry = models_from_settings(settings(openai_models=("gpt-6-luna",))).entries[1]
    assert entry.unavailable == "no API key"


def test_no_openai_models_hides_openai() -> None:
    assert refs(settings(openai_api_key="sk-x")) == ["local/qwen3.5-9b"]


def test_same_id_on_both_providers_is_two_entries() -> None:
    s = settings(llm_models=("shared",), openai_models=("shared",), openai_api_key="sk-x")
    assert refs(s) == ["local/qwen3.5-9b", "local/shared", "openai/shared"]


def test_default_can_be_an_openai_model() -> None:
    s = settings(
        openai_models=("gpt-6-luna",), openai_api_key="sk-x", default_model="openai/gpt-6-luna"
    )
    models = models_from_settings(s)
    assert models.default == ModelRef(provider="openai", model="gpt-6-luna")


@pytest.mark.parametrize(
    "default",
    [
        "local/other",  # not configured
        "openai/gpt-6-luna",  # no key
        "qwen3.5-9b",  # no provider
        "other/claude",  # unknown provider
        "anthropic/claude-sonnet-5-5",  # not configured
        "local/",  # no model
    ],
)
def test_unusable_default_names_the_setting(default: str) -> None:
    with pytest.raises(ValueError, match=r"^DEFAULT_MODEL: "):
        models_from_settings(settings(openai_models=("gpt-6-luna",), default_model=default))


def test_parse_ref_splits_at_first_slash() -> None:
    assert parse_ref("local/Qwen/Qwen3-8B") == ModelRef(provider="local", model="Qwen/Qwen3-8B")


def test_anthropic_models_with_key() -> None:
    s = settings(anthropic_models=("claude-sonnet-5-5",), anthropic_api_key="sk-ant-x")
    entry = models_from_settings(s).entries[1]
    assert str(entry.ref) == "anthropic/claude-sonnet-5-5"
    assert (entry.external, entry.unavailable, entry.client.provider) == (True, None, "anthropic")


def test_anthropic_models_without_key_are_unavailable() -> None:
    entry = models_from_settings(settings(anthropic_models=("claude-sonnet-5-5",))).entries[1]
    assert entry.unavailable == "no API key"


def test_default_can_be_an_anthropic_model() -> None:
    s = settings(
        anthropic_models=("claude-sonnet-5-5",),
        anthropic_api_key="sk-ant-x",
        default_model="anthropic/claude-sonnet-5-5",
    )
    assert models_from_settings(s).default == ModelRef(
        provider="anthropic", model="claude-sonnet-5-5"
    )


def test_env_default_is_claude_with_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("DEFAULT_MODEL", "ANTHROPIC_MODELS", "LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    s = Settings.from_env()
    assert (s.default_model, s.anthropic_models) == (
        "anthropic/claude-sonnet-5-5",
        ("claude-sonnet-5-5",),
    )
    monkeypatch.setenv("ANTHROPIC_MODELS", "claude-haiku-5-5, claude-sonnet-5-5")
    assert Settings.from_env().default_model == "anthropic/claude-haiku-5-5"


def test_env_default_stays_local_without_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("DEFAULT_MODEL", "ANTHROPIC_API_KEY", "LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)
    assert Settings.from_env().default_model == "local/qwen3.5-9b"
