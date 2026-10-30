"""uvicorn entry point: `uvicorn agent_lab.main:app --host 127.0.0.1`."""

from agent_lab.api import create_app
from agent_lab.config import Settings
from agent_lab.llm.openai_compat import OpenAICompatClient
from agent_lab.store import Store

settings = Settings.from_env()
if settings.llm_provider != "openai_compat":
    raise SystemExit(f"unsupported LLM_PROVIDER {settings.llm_provider!r} (only openai_compat)")

app = create_app(
    store=Store(settings.db_path),
    llm=OpenAICompatClient(
        base_url=settings.llm_base_url, model=settings.llm_model, api_key=settings.llm_api_key
    ),
    secrets=(settings.llm_api_key,),
)
