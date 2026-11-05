"""Budgets' limits and stopping a run over HTTP (specs/017-evaluation-harness/contracts)."""

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel

from agent_lab.harness.budget import DEFAULT_BUDGET, MAX_BUDGET, Budget
from agent_lab.harness.live import LiveRuns
from agent_lab.store import Run, Store


class BudgetLimits(BaseModel):
    default: Budget
    max: Budget


def add_harness_routes(app: FastAPI, store: Store, live: LiveRuns) -> None:
    @app.get("/budget-limits")
    async def budget_limits() -> BudgetLimits:
        return BudgetLimits(default=DEFAULT_BUDGET, max=MAX_BUDGET)

    @app.post("/runs/{run_id}/stop", status_code=status.HTTP_202_ACCEPTED)
    async def stop_run(run_id: str) -> Run:
        run = store.get_run(run_id)
        if run is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown run")
        if not live.stop(run_id):  # the village's runs never register
            raise HTTPException(status.HTTP_409_CONFLICT, "this run cannot be stopped")
        return run
