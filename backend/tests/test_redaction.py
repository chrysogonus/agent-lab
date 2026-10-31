"""End to end: secrets in a prompt or the provider key never reach the database file."""

import json
from pathlib import Path
from typing import Any

import httpx
from fastapi.testclient import TestClient
from helpers import answer, fake_models
from test_agents_api import LUNA, new_agent
from test_api import WS_BASE, read_until_run_ended
from test_providers import KEY as OPENAI_KEY
from test_providers import openai_app

from agent_lab.api import create_app
from agent_lab.llm.fake import FakeLLM
from agent_lab.store import Store

API_KEY = "sk-live-0123456789abcdefghij"
BEARER = "Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig"


def test_secrets_never_stored(tmp_path: Path) -> None:
    path = tmp_path / "lab.db"
    llm = FakeLLM([answer(f"echo: {BEARER} and {API_KEY}")])
    app = create_app(store=Store(path), models=fake_models(llm), secrets=(API_KEY,))
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        prompt = f"my header is Authorization: {BEARER}, key {API_KEY}"
        run_id = client.post("/runs", json={"prompt": prompt}).json()["run_id"]
        with client.websocket_connect(f"ws://127.0.0.1:8000/runs/{run_id}/stream") as ws:
            while ws.receive_json()["type"] != "run_ended":
                pass
        detail = client.get(f"/runs/{run_id}").json()

    # The model saw the real prompt; storage and the API only ever see redacted text.
    assert API_KEY in llm.calls[0][1]["content"]
    assert detail["spans"] and "[REDACTED]" in detail["run"]["prompt"]
    raw = b"".join(p.read_bytes() for p in tmp_path.iterdir())  # db plus any -wal/-journal
    assert API_KEY.encode() not in raw
    assert b"eyJhbGciOiJIUzI1NiJ9" not in raw
    assert API_KEY not in str(detail) and "eyJhbGciOiJIUzI1NiJ9" not in str(detail)


LOCAL_KEY = "sk-local-abcdefghij0123456789"


def test_provider_keys_never_exposed(tmp_path: Path) -> None:
    """Neither provider key reaches storage, the stream or any API response (SC-005)."""

    def echo_key(body: dict[str, Any]) -> httpx.Response:  # a provider echoing the header
        return httpx.Response(401, text=f"Incorrect API key provided: Bearer {OPENAI_KEY}")

    store = Store(tmp_path / "lab.db")
    client, _ = openai_app(
        store, echo_key, local_script=[answer(f"echo {LOCAL_KEY}")], secrets=(LOCAL_KEY, OPENAI_KEY)
    )
    seen: list[str] = []
    with client:
        agent = new_agent(client, "react", model=LUNA)
        prompt = f"keys {LOCAL_KEY} and {OPENAI_KEY}"
        for agent_id in (agent["id"], "react"):
            run = client.post("/runs", json={"prompt": prompt, "agent_id": agent_id}).json()
            with client.websocket_connect(f"{WS_BASE}/runs/{run['run_id']}/stream") as ws:
                seen.append(json.dumps(read_until_run_ended(ws)))
            seen.append(client.get(f"/runs/{run['run_id']}").text)
        for path in ("/models", "/agents", "/runs"):
            seen.append(client.get(path).text)

    assert '"status": "error"' in seen[0] and "[REDACTED]" in seen[0]  # the 401 was recorded
    raw = b"".join(p.read_bytes() for p in tmp_path.iterdir())
    for key in (LOCAL_KEY, OPENAI_KEY):
        assert key.encode() not in raw
        assert not any(key in text for text in seen)
