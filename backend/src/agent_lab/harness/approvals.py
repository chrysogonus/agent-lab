"""Who decides before a tool marked ask first is called: the owner, or an evaluation's case.

Open requests live in memory, as futures. A restart ends their runs as interrupted, so none has to
survive one and no call can go out after it (FR-022).
"""

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from pydantic import BaseModel

from agent_lab.tracing.redact import redact

TIMEOUT_SECONDS = 600  # an unanswered request is denied after 10 minutes (FR-017)
DecidedBy = Literal["owner", "timeout", "case"]


@dataclass(frozen=True)
class Decision:
    approved: bool
    by: DecidedBy
    reason: str | None = None

    @property
    def text(self) -> str:
        """What the approval span shows; when denied, what the tool's result says."""
        if self.approved:
            return "approved"
        if self.by == "case":
            return "denied by the test case"
        return f"denied by the owner: {self.reason}" if self.reason else "denied by the owner"

    @property
    def outcome(self) -> Literal["approved", "denied", "timed_out"]:
        if self.by == "timeout":
            return "timed_out"
        return "approved" if self.approved else "denied"


class Decider(Protocol):
    immediate: bool  # False: the run waits, and its time budget's clock with it

    async def decide(self, tool: str, server: str, arguments: dict[str, Any]) -> Decision: ...


class OpenRequest(BaseModel):
    approval_id: str
    run_id: str
    agent_name: str
    prompt: str
    tool: str
    server: str
    arguments: dict[str, Any]  # redacted
    asked_at: float
    expires_at: float


class Approvals:
    def __init__(self, *, timeout: float = TIMEOUT_SECONDS) -> None:
        self.timeout = timeout
        self._open: dict[str, tuple[OpenRequest, asyncio.Future[Decision]]] = {}

    def open(self) -> list[OpenRequest]:
        """Oldest first: a dict keeps the order they were asked in."""
        return [request for request, _ in self._open.values()]

    def answer(self, approval_id: str, *, approve: bool, reason: str | None) -> bool:
        """False when it is no longer open."""
        entry = self._open.get(approval_id)
        if entry is None or entry[1].done():
            return False
        entry[1].set_result(Decision(approve, "owner", reason))
        return True

    async def ask(
        self,
        *,
        run_id: str,
        agent_name: str,
        prompt: str,
        tool: str,
        server: str,
        arguments: dict[str, Any],
    ) -> Decision:
        now = time.time()
        request = OpenRequest(
            approval_id=uuid.uuid4().hex,
            run_id=run_id,
            agent_name=agent_name,
            prompt=prompt,
            tool=tool,
            server=server,
            arguments=arguments,
            asked_at=now,
            expires_at=now + self.timeout,
        )
        future: asyncio.Future[Decision] = asyncio.get_running_loop().create_future()
        self._open[request.approval_id] = (request, future)
        try:
            return await asyncio.wait_for(future, self.timeout)
        except TimeoutError:
            return Decision(False, "timeout", "no answer from the owner")
        finally:
            del self._open[request.approval_id]


class OwnerDecider:
    immediate = False

    def __init__(
        self,
        approvals: Approvals,
        *,
        run_id: str,
        agent_name: str,
        prompt: str,
        secrets: tuple[str, ...] = (),
    ) -> None:
        self.approvals, self.run_id, self.agent_name = approvals, run_id, agent_name
        self.prompt, self.secrets = prompt, secrets

    async def decide(self, tool: str, server: str, arguments: dict[str, Any]) -> Decision:
        return await self.approvals.ask(
            run_id=self.run_id,
            agent_name=self.agent_name,
            prompt=redact(self.prompt, self.secrets),
            tool=tool,
            server=server,
            arguments=redact(arguments, self.secrets),
        )


class CaseDecider:
    """An evaluation has nobody watching: the case says what to do with requests (FR-020)."""

    immediate = True

    def __init__(self, setting: Literal["approve", "deny"]) -> None:
        self.setting = setting

    async def decide(self, tool: str, server: str, arguments: dict[str, Any]) -> Decision:
        return Decision(self.setting == "approve", "case")
