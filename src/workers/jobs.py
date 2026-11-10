"""Single-slot background job runner (scan / export) with progress, cancel and persistence."""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, Callable

from src.database.db import Database
from src.exporter.pipeline import ExportOptions, Pipeline
from src.utils.events import EventBus
from src.utils.files import utcnow_iso

log = logging.getLogger("jobs")


class JobManager:
    def __init__(self, db: Database, bus: EventBus, pipeline_factory: Callable[[], Pipeline]) -> None:
        self.db, self.bus, self.factory = db, bus, pipeline_factory
        self._task: asyncio.Task | None = None
        self._pipeline: Pipeline | None = None
        self.current: dict[str, Any] | None = None
        self.last_progress: dict[str, Any] = {}
        self.db.execute("UPDATE jobs SET status='interrupted', finished_at=? WHERE status='running'", (utcnow_iso(),))
        bus.publish("info", {"message": "ready"})

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self, kind: str, params: dict[str, Any]) -> dict[str, Any]:
        if self.running:
            raise RuntimeError("A job is already running")
        job = {"id": uuid.uuid4().hex[:12], "kind": kind, "status": "running", "params": params, "started_at": utcnow_iso()}
        self.db.execute("INSERT INTO jobs(id,kind,status,params,started_at) VALUES (?,?,?,?,?)",
                        (job["id"], kind, "running", json.dumps(params), job["started_at"]))
        self.current = job
        self.last_progress = {}
        self._pipeline = self.factory()
        opts = ExportOptions.from_dict({**params, "kind": kind})
        self._task = asyncio.create_task(self._run(job, opts))
        self.bus.publish("job", {"id": job["id"], "kind": kind, "status": "running"})
        return job

    async def _run(self, job: dict[str, Any], opts: ExportOptions) -> None:
        status, error, result = "completed", None, None
        try:
            assert self._pipeline
            result = await self._pipeline.run(opts)
            status = result.get("status", "completed")
        except asyncio.CancelledError:
            status = "cancelled"
        except Exception as exc:
            status, error = "failed", f"{type(exc).__name__}: {exc}"
            log.error("job %s failed: %s", job["id"], error)
        job.update(status=status, error=error)
        self.db.execute("UPDATE jobs SET status=?, finished_at=?, error=?, result=? WHERE id=?",
                        (status, utcnow_iso(), error, json.dumps(result, default=str) if result else None, job["id"]))
        self.bus.publish("job", {"id": job["id"], "kind": job["kind"], "status": status, "error": error})

    def cancel(self) -> bool:
        if not self.running:
            return False
        if self._pipeline:
            self._pipeline.cancel()
        log.warning("Cancellation requested; finishing in-flight work")
        return True

    def status(self) -> dict[str, Any]:
        return {"running": self.running, "job": self.current}
