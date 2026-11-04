"""uvicorn entry point: `uvicorn agent_lab.main:app --host 127.0.0.1`."""

import os

import httpx

from agent_lab.api import create_app
from agent_lab.config import Settings, renamed_settings
from agent_lab.llm.models import models_from_settings
from agent_lab.mcp.host import Host
from agent_lab.mcp.servers_file import find
from agent_lab.store import Store

if renamed := renamed_settings(os.environ):
    raise SystemExit("Rename these settings in .env (see .env.example):\n" + "\n".join(renamed))
settings = Settings.from_env()
try:
    models = models_from_settings(settings)
except ValueError as exc:
    raise SystemExit(str(exc)) from None

app = create_app(
    store=Store(settings.db_path),
    models=models,
    secrets=(settings.local_api_key, settings.openai_api_key, settings.anthropic_api_key),
    host=Host(find(settings.mcp_servers_file), httpx.AsyncClient()),
)
