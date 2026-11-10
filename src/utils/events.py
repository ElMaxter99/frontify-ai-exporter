"""Thread-safe pub/sub used for realtime logs and progress (consumed via SSE)."""
from __future__ import annotations

import asyncio
import itertools
import threading
import time
from collections import deque
from typing import Any


class EventBus:
    def __init__(self, history: int = 500) -> None:
        self._history: deque[dict[str, Any]] = deque(maxlen=history)
        self._subs: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = []
        self._lock = threading.Lock()
        self._ids = itertools.count(1)

    def publish(self, kind: str, data: dict[str, Any]) -> None:
        evt = {"id": next(self._ids), "ts": time.time(), "kind": kind, "data": data}
        with self._lock:
            self._history.append(evt)
            subs = list(self._subs)
        for loop, q in subs:
            try:
                loop.call_soon_threadsafe(self._put, q, evt)
            except RuntimeError:  # loop closed
                pass

    @staticmethod
    def _put(q: asyncio.Queue, evt: dict[str, Any]) -> None:
        if q.full():
            try:
                q.get_nowait()
            except asyncio.QueueEmpty:
                pass
        q.put_nowait(evt)

    def history(self, kinds: set[str] | None = None) -> list[dict[str, Any]]:
        with self._lock:
            return [e for e in self._history if not kinds or e["kind"] in kinds]

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        with self._lock:
            self._subs.append((asyncio.get_running_loop(), q))
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            self._subs = [(lp, s) for (lp, s) in self._subs if s is not q]
