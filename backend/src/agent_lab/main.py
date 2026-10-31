"""uvicorn entry point: `uvicorn agent_lab.main:app --host 127.0.0.1`."""

from agent_lab.api import create_app
from agent_lab.config import Settings
from agent_lab.llm.models import models_from_settings
from agent_lab.store import Store

settings = Settings.from_env()
if settings.llm_provider != "openai_compat":
    raise SystemExit(f"unsupported LLM_PROVIDER {settings.llm_provider!r} (only openai_compat)")
try:
    models = models_from_settings(settings)
except ValueError as exc:
    raise SystemExit(str(exc)) from None

app = create_app(
    store=Store(settings.db_path),
    models=models,
    secrets=(settings.llm_api_key, settings.openai_api_key),
)
