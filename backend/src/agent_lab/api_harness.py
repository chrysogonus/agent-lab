"""Budgets' limits, stopping a run and approvals over HTTP (specs/017-evaluation-harness)."""

from collections.abc import Sequence
from typing import Annotated, Literal

from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, StringConstraints

from agent_lab.harness.approvals import Approvals, OpenRequest
from agent_lab.harness.budget import DEFAULT_BUDGET, MAX_BUDGET, Budget
from agent_lab.harness.live import LiveRuns
from agent_lab.store import Run, Store


class BudgetLimits(BaseModel):
    default: Budget
    max: Budget


class ApprovalAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve", "deny"]
    reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None


def add_harness_routes(
    app: FastAPI,
    store: Store,
    live: LiveRuns,
    approvals: Approvals,
    allowed_origins: Sequence[str],
) -> None:
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

    @app.get("/approvals")
    async def open_approvals() -> list[OpenRequest]:
        return approvals.open()

    @app.post("/approvals/{approval_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def answer_approval(
        approval_id: str, body: ApprovalAnswer, origin: Annotated[str | None, Header()] = None
    ) -> None:
        # This lets a tool run: no other page may send it, as for `/mcp`.
        if origin is not None and origin not in allowed_origins:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "origin not allowed")
        approve = body.decision == "approve"
        if not approvals.answer(approval_id, approve=approve, reason=body.reason or None):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "this request is no longer open")
