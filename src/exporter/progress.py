# SPDX-License-Identifier: Apache-2.0
"""Live counters + log tail shown by the UI. Plain in-memory object, no persistence."""
from __future__ import annotations

import logging
import time
from collections import deque
from typing import Any

from src.utils.logging import RedactingFilter


class Progress:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.running = False
        self.phase = "idle"
        self.found = 0            # files (assets) found in Frontify
        self.to_download = 0
        self.processed = 0        # files handled so far in the download phase
        self.downloaded = 0
        self.documents = 0        # guideline pages + document files processed
        self.errors = 0
        self.skipped = 0
        self.bytes = 0
        self.message = ""
        self.result: dict[str, Any] | None = None
        self.folder: str | None = None
        self.cancelled = False
        self.logs: deque[dict[str, Any]] = deque(maxlen=300)

    def percent(self) -> int:
        if self.phase in ("done", "analyzed"):
            return 100
        if self.phase == "downloading" and self.to_download:
            return 10 + int(80 * self.processed / self.to_download)
        return {"connecting": 2, "analyzing": 6, "guidelines": 92, "documents": 96, "writing": 98}.get(self.phase, 0)

    def snapshot(self) -> dict[str, Any]:
        return {"running": self.running, "phase": self.phase, "percent": self.percent(), "found": self.found,
                "to_download": self.to_download, "processed": self.processed, "downloaded": self.downloaded,
                "documents": self.documents, "errors": self.errors, "skipped": self.skipped, "bytes": self.bytes,
                "message": self.message, "folder": self.folder, "result": self.result, "cancelled": self.cancelled,
                "logs": list(self.logs)[-80:]}


class ProgressLogHandler(logging.Handler):
    def __init__(self, progress: Progress) -> None:
        super().__init__(level=logging.INFO)
        self.progress = progress
        self.addFilter(RedactingFilter())

    def emit(self, record: logging.LogRecord) -> None:
        self.progress.logs.append({"t": time.strftime("%H:%M:%S"), "level": record.levelname, "msg": record.getMessage()})
