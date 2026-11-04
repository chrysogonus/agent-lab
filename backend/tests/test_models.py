"""Settings → the model catalog: providers, availability and the default (FR-001, FR-002)."""

from dataclasses import replace
from typing import Any

import pytest

from agent_lab.config import Settings, renamed_settings
from agent_lab.llm.models import ModelRef, models_from_settings, parse_ref


def settings(**changes: Any) -> Settings:
    """One local model, plus the given settings."""
    base = Settings(
        local_base_url="http://localhost:8001/v1",
        local_models=("qwen3.5-9b",),
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
    s = settings(local_models=("qwen3.5-9b", "qwen3:8b", "qwen3.5-9b", "Qwen/Qwen3-8B"))
    assert refs(s) == ["local/qwen3.5-9b", "local/qwen3:8b", "local/Qwen/Qwen3-8B"]


def test_openai_models_with_key() -> None:
    models = models_from_settings(settings(openai_models=("gpt-6-luna",), openai_api_key="sk-x"))
    entry = models.entries[1]
    assert str(entry.ref) == "openai/gpt-6-luna"
    assert (entry.external, entry.unavailable, entry.client.provider) == (True, None, "openai")


def test_openai_models_without_key_are_unavailable() -> None:
    entry = models_from_settings(settings(openai_models=("gpt-6-luna",))).entries[1]
    assert entry.unavailable == "no API key"


def test_no_openai_models_hides_openai() -> None:
    assert refs(settings(openai_api_key="sk-x")) == ["local/qwen3.5-9b"]


def test_same_id_on_both_providers_is_two_entries() -> None:
    s = settings(
        local_models=("qwen3.5-9b", "shared"), openai_models=("shared",), openai_api_key="sk-x"
    )
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


NAMES = (
    "DEFAULT_MODEL",
    "LOCAL_BASE_URL",
    "LOCAL_MODELS",
    "LOCAL_API_KEY",
    "OPENAI_MODELS",
    "OPENAI_API_KEY",
    "ANTHROPIC_MODELS",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_WORKSPACE_ID",
)


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for name in NAMES:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_env_defaults(clean_env: pytest.MonkeyPatch) -> None:
    s = Settings.from_env()
    assert (s.local_base_url, s.local_models, s.local_api_key) == (
        "http://localhost:8001/v1",
        ("qwen3.5-9b",),
        "",
    )
    assert (s.openai_models, s.anthropic_models) == (
        ("gpt-6-luna",),
        ("claude-haiku-5-5", "claude-sonnet-5-5"),
    )
    assert s.default_model == "local/qwen3.5-9b"


def test_a_key_alone_does_not_switch_the_default(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    assert Settings.from_env().default_model == "local/qwen3.5-9b"


@pytest.mark.parametrize(
    "default", ["anthropic/claude-sonnet-5-5", "openai/gpt-6-luna", "local/qwen3.5-9b"]
)
def test_default_model_switches_provider(clean_env: pytest.MonkeyPatch, default: str) -> None:
    clean_env.setenv("DEFAULT_MODEL", default)
    clean_env.setenv("OPENAI_API_KEY", "sk-x")
    clean_env.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    models = models_from_settings(Settings.from_env())
    assert str(models.default) == default
    assert [str(e.ref) for e in models.entries] == [
        "local/qwen3.5-9b",
        "openai/gpt-6-luna",
        "anthropic/claude-haiku-5-5",
        "anthropic/claude-sonnet-5-5",
    ]


def test_local_settings_from_env(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("LOCAL_BASE_URL", "http://localhost:11434/v1")
    clean_env.setenv("LOCAL_MODELS", "qwen3:8b, qwen3:14b")
    s = Settings.from_env()
    assert (s.local_base_url, s.local_models) == (
        "http://localhost:11434/v1",
        ("qwen3:8b", "qwen3:14b"),
    )
    assert s.default_model == "local/qwen3:8b"


def test_anthropic_workspace_from_env(clean_env: pytest.MonkeyPatch) -> None:
    assert Settings.from_env().anthropic_workspace_id == ""
    clean_env.setenv("ANTHROPIC_WORKSPACE_ID", "wrkspc_1")
    assert Settings.from_env().anthropic_workspace_id == "wrkspc_1"


def test_old_names_are_reported() -> None:
    environ = {"LLM_PROVIDER": "anthropic", "LLM_BASE_URL": "x", "LLM_MODEL": "y", "OTHER": "z"}
    assert renamed_settings(environ) == [
        "LLM_PROVIDER is gone: DEFAULT_MODEL picks the provider",
        "LLM_BASE_URL is now LOCAL_BASE_URL",
        "LLM_MODEL is now LOCAL_MODELS",
    ]
    assert renamed_settings({"LOCAL_MODELS": "q"}) == []
