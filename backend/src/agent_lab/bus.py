"""In-process fan-out of run events to WebSocket subscribers."""

import asyncio
from collections import defaultdict
from typing import Any

Event = dict[str, Any]


class Bus:
    def __init__(self) -> None:
        self._subscribers: defaultdict[str, set[asyncio.Queue[Event]]] = defaultdict(set)

    def subscribe(self, run_id: str) -> asyncio.Queue[Event]:
        queue: asyncio.Queue[Event] = asyncio.Queue()
        self._subscribers[run_id].add(queue)
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue[Event]) -> None:
        self._subscribers[run_id].discard(queue)
        if not self._subscribers[run_id]:
            del self._subscribers[run_id]

    def publish(self, run_id: str, event: Event) -> None:
        for queue in self._subscribers.get(run_id, ()):
            queue.put_nowait(event)
