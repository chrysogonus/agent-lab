"""The lab's running runs, so the owner can stop one. The village's never register (FR-012)."""

import asyncio

from agent_lab.harness.guard import RunGuard


class LiveRuns:
    def __init__(self) -> None:
        self._runs: dict[str, tuple[asyncio.Task[None], RunGuard]] = {}

    def add(self, run_id: str, task: asyncio.Task[None], guard: RunGuard) -> None:
        self._runs[run_id] = (task, guard)

    def remove(self, run_id: str) -> None:
        self._runs.pop(run_id, None)

    def stop(self, run_id: str) -> bool:
        """Cancels the run; False when it is not live."""
        entry = self._runs.get(run_id)
        if entry is None:
            return False
        task, guard = entry
        guard.stop_requested = True
        task.cancel()
        return True
