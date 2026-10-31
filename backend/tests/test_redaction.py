"""End to end: secrets in a prompt or the provider key never reach the database file."""

from pathlib import Path

from fastapi.testclient import TestClient
from helpers import answer, fake_models

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
