"""What a stopped lab leaves behind, and how a stream shows a waiting run (M17, FR-022)."""

from pathlib import Path

from fastapi.testclient import TestClient
from helpers import fake_models
from test_api import BASE, ORIGIN, WS_BASE

from agent_lab.agents.react import build_graph
from agent_lab.api import create_app
from agent_lab.llm.fake import FakeLLM
from agent_lab.store import Run, RunStatus, Store


def stored_run(store: Store, run_id: str, status: RunStatus, tick: int | None = None) -> None:
    store.create_run(
        Run(
            run_id=run_id,
            agent_id="react",
            config_version="v",
            prompt="hi",
            status=status,
            graph=build_graph([]),
            config={},
            started_at=1.0,
            village_tick=tick,
        )
    )


def test_the_labs_start_interrupts_runs_it_left_behind(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    stored_run(store, "orphan", "running")
    stored_run(store, "waiting", "waiting_approval")
    stored_run(store, "turn", "running", tick=3)

    with TestClient(create_app(store=store, models=fake_models(FakeLLM([]))), base_url=BASE) as c:
        assert c.get("/runs/orphan").json()["run"]["status"] == "interrupted"
        assert c.get("/runs/waiting").json()["run"]["status"] == "interrupted"
        assert c.get("/runs/turn").json()["run"]["status"] == "running"


def test_a_stream_of_an_interrupted_run_ends(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    stored_run(store, "orphan", "running")
    with (
        TestClient(create_app(store=store, models=fake_models(FakeLLM([]))), base_url=BASE) as c,
        c.websocket_connect(f"{WS_BASE}/runs/orphan/stream", headers={"origin": ORIGIN}) as ws,
    ):
        event = ws.receive_json()
    assert event["type"] == "run_ended"
    assert event["run"]["status"] == "interrupted"


def test_a_stream_of_a_waiting_run_says_so_and_stays_open(tmp_path: Path) -> None:
    store = Store(tmp_path / "lab.db")
    stored_run(store, "waiting", "waiting_approval")
    client = TestClient(create_app(store=store, models=fake_models(FakeLLM([]))), base_url=BASE)
    with client.websocket_connect(
        f"{WS_BASE}/runs/waiting/stream", headers={"origin": ORIGIN}
    ) as ws:
        event = ws.receive_json()
    assert event == {"type": "run_status", "run_id": "waiting", "status": "waiting_approval"}
