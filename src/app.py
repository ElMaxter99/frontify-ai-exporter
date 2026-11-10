"""Local web UI (binds to 127.0.0.1). One job at a time, state in memory, nothing persisted but the export folder."""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.exporter.progress import Progress
from src.exporter.run import Exporter
from src.frontify.client import FrontifyError
from src.utils.logging import setup_logging

UI = Path(__file__).parent / "ui" / "index.html"


class Job(BaseModel):
    url: str
    token: str = ""
    dest: str
    name: str | None = None
    concurrency: int = 4


def create_app(*, api_transport: httpx.AsyncBaseTransport | None = None, download_transport: httpx.AsyncBaseTransport | None = None,
               api_base_url: str | None = None) -> FastAPI:
    setup_logging(os.getenv("LOG_LEVEL", "INFO"))
    app = FastAPI(title="Frontify Exporter", docs_url=None, redoc_url=None)
    progress = Progress()
    state: dict[str, Any] = {"task": None, "exporter": None}

    def running() -> bool:
        t = state["task"]
        return t is not None and not t.done()

    def make(job: Job) -> Exporter:
        token = job.token.strip() or os.getenv("FRONTIFY_TOKEN", "")
        return Exporter(job.url, token, job.dest, client_name=job.name or None, concurrency=max(1, min(job.concurrency, 32)), progress=progress,
                        api_transport=api_transport, download_transport=download_transport, api_base_url=api_base_url)

    async def run(kind: str, job: Job) -> None:
        try:
            ex = make(job)
            state["exporter"] = ex
            await (ex.analyze() if kind == "analyze" else ex.export())
        except FrontifyError:
            pass  # message already stored in progress
        except Exception as exc:  # keep the UI informative, never crash the server
            logging.getLogger("app").exception("job failed")
            progress.running, progress.phase, progress.message = False, "failed", f"{type(exc).__name__}: {exc}"
            progress.result = {"kind": "error", "error": progress.message}

    async def start(kind: str, job: Job) -> dict[str, bool]:
        if running():
            raise HTTPException(409, "A job is already running")
        if not job.url.strip() or not (job.token.strip() or os.getenv("FRONTIFY_TOKEN")):
            raise HTTPException(400, "Enter the Frontify URL and the API token")
        if not job.dest.strip():
            raise HTTPException(400, "Choose a destination folder")
        progress.reset()
        progress.running, progress.phase = True, "connecting"
        state["task"] = asyncio.create_task(run(kind, job))
        return {"started": True}

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(UI)

    @app.get("/api/config")
    def config() -> dict[str, Any]:
        return {"default_dest": str(Path(os.getenv("EXPORT_DIR", "EXPORTS")).resolve()), "has_env_token": bool(os.getenv("FRONTIFY_TOKEN")),
                "default_url": os.getenv("FRONTIFY_URL", ""), "can_pick_folder": _can_pick()}

    @app.post("/api/analyze")
    async def analyze(job: Job) -> dict[str, bool]:
        return await start("analyze", job)

    @app.post("/api/export")
    async def export(job: Job) -> dict[str, bool]:
        return await start("export", job)

    @app.post("/api/cancel")
    async def cancel() -> dict[str, bool]:
        ex = state["exporter"]
        if running() and ex:
            ex.cancel()
            return {"cancelling": True}
        return {"cancelling": False}

    @app.get("/api/status")
    def status() -> dict[str, Any]:
        return progress.snapshot()

    @app.post("/api/pick-folder")
    def pick_folder() -> dict[str, Any]:
        code = "import tkinter as t,tkinter.filedialog as f;r=t.Tk();r.withdraw();r.attributes('-topmost',True);print(f.askdirectory() or '')"
        try:
            out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=300)
            path = out.stdout.strip()
            if out.returncode != 0:
                return {"path": None, "error": "No folder dialog available on this system; type the path instead."}
            return {"path": path or None}
        except Exception:
            return {"path": None, "error": "No folder dialog available on this system; type the path instead."}

    @app.post("/api/open-folder")
    def open_folder() -> dict[str, Any]:
        folder = progress.folder
        if not folder or not Path(folder).exists():
            raise HTTPException(404, "Nothing exported yet")
        try:
            if sys.platform.startswith("win"):
                os.startfile(folder)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", folder], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {"opened": folder}
        except Exception as exc:
            return {"opened": None, "error": f"Could not open a file manager ({exc}). Folder: {folder}"}

    return app


def _can_pick() -> bool:
    try:
        import tkinter  # noqa: F401
        return True
    except ImportError:
        return False


def app_factory() -> FastAPI:
    return create_app()
