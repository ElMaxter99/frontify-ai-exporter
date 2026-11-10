"""FastAPI application. Credentials never leave the server: no endpoint returns the token."""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from src.ai.embeddings import make_embedder
from src.ai.indexer import Searcher
from src.ai.vectorstore import make_store
from src.config import RuntimeConfig, Settings
from src.database.db import Database
from src.exporter.pipeline import Pipeline
from src.frontify import queries as Q
from src.frontify.client import FrontifyAuthError, FrontifyClient, FrontifyError
from src.sync import history
from src.utils.events import EventBus
from src.utils.logging import register_secret, setup_logging
from src.workers.jobs import JobManager

log = logging.getLogger("api")


class SettingsIn(BaseModel):
    values: dict[str, Any]
    token: str | None = None   # optional, kept in server memory only (never persisted, never returned)


class JobIn(BaseModel):
    brand_ids: list[str] | None = None
    categories: list[str] | None = None
    scan: bool = True
    download: bool = True
    guidelines: bool = True
    knowledge: bool = True
    index: bool = True
    force: bool = False


def create_app(settings: Settings | None = None, *, api_transport: httpx.AsyncBaseTransport | None = None,
               download_transport: httpx.AsyncBaseTransport | None = None, api_base_url: str | None = None) -> FastAPI:
    base = settings or Settings()
    bus = EventBus()
    setup_logging(base.log_level, bus)
    db = Database(base.db_path)
    cfg = RuntimeConfig(base, db.get_settings())
    register_secret(cfg.token)
    register_secret(cfg.openai_key)

    def factory() -> Pipeline:
        return Pipeline(cfg, db, bus, api_transport=api_transport, download_transport=download_transport, api_base_url=api_base_url)

    jobs = JobManager(db, bus, factory)
    app = FastAPI(title="Frontify AI Exporter", version="0.1.0")
    app.state.db, app.state.cfg, app.state.jobs, app.state.bus = db, cfg, jobs, bus

    # ------------------------------------------------------------- connection
    @app.get("/api/settings")
    def get_settings() -> dict[str, Any]:
        return cfg.public()

    @app.put("/api/settings")
    def put_settings(body: SettingsIn) -> dict[str, Any]:
        clean = cfg.set_overrides(body.values)
        db.put_settings(clean)
        if body.token is not None:
            cfg.set_session_token(body.token.strip() or None)
            register_secret(cfg.token)
        return cfg.public()

    @app.post("/api/connection/test")
    async def test_connection() -> dict[str, Any]:
        if not cfg.domain or not cfg.token:
            return {"ok": False, "error": "Set FRONTIFY_DOMAIN and FRONTIFY_TOKEN (or enter them in Settings)"}
        try:
            async with FrontifyClient(cfg.domain, cfg.token, timeout=20, max_retries=1, transport=api_transport, base_url=api_base_url) as c:
                data = await c.execute(Q.CURRENT_USER, operation="CurrentUser")
                brands = await c.execute(Q.ACCOUNT_BRANDS, operation="Brands")
            return {"ok": True, "user": (data.get("currentUser") or {}).get("name"),
                    "brands": [{"id": b["id"], "name": b["name"]} for b in brands.get("brands") or [] if b]}
        except FrontifyAuthError as exc:
            return {"ok": False, "error": str(exc)}
        except FrontifyError as exc:
            return {"ok": False, "error": str(exc)}

    # ------------------------------------------------------------------- jobs
    @app.post("/api/scan")
    async def scan(body: JobIn | None = None) -> dict[str, Any]:
        b = body or JobIn()
        return _start("scan", {"brand_ids": b.brand_ids, "scan": True, "download": False, "guidelines": False, "knowledge": False, "index": False})

    @app.post("/api/export")
    async def export(body: JobIn | None = None) -> dict[str, Any]:
        return _start("export", (body or JobIn()).model_dump())

    def _start(kind: str, params: dict[str, Any]) -> dict[str, Any]:
        if not cfg.domain or not cfg.token:
            raise HTTPException(400, "Frontify domain/token not configured")
        try:
            return jobs.start(kind, params)
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/api/jobs/cancel")
    async def cancel() -> dict[str, bool]:
        return {"cancelling": jobs.cancel()}

    @app.get("/api/jobs")
    def list_jobs() -> dict[str, Any]:
        rows = db.query("SELECT id,kind,status,started_at,finished_at,error FROM jobs ORDER BY started_at DESC LIMIT 20")
        return {**jobs.status(), "history": rows}

    @app.get("/api/events")
    async def events() -> EventSourceResponse:
        q = bus.subscribe()

        async def gen():
            try:
                for e in bus.history():
                    yield {"event": e["kind"], "id": str(e["id"]), "data": json.dumps(e)}
                while True:
                    try:
                        e = await asyncio.wait_for(q.get(), 15)
                        yield {"event": e["kind"], "id": str(e["id"]), "data": json.dumps(e)}
                    except asyncio.TimeoutError:
                        yield {"event": "ping", "data": "{}"}
            finally:
                bus.unsubscribe(q)
        return EventSourceResponse(gen())

    # -------------------------------------------------------------- dashboard
    @app.get("/api/dashboard")
    def dashboard() -> dict[str, Any]:
        s = db.one("""SELECT count(*) n, coalesce(sum(size),0) bytes, sum(download_status='done') done,
                      sum(download_status='failed') failed, sum(download_status='pending') pending,
                      sum(download_status='unavailable') unavailable FROM assets WHERE status='active'""") or {}
        return {
            "configured": bool(cfg.domain and cfg.token), "domain": cfg.domain,
            "brands": db.scalar("SELECT count(*) FROM brands WHERE status='active'"),
            "assets": s.get("n", 0), "total_bytes": s.get("bytes", 0), "downloaded": s.get("done") or 0,
            "failed": s.get("failed") or 0, "pending": s.get("pending") or 0, "unavailable": s.get("unavailable") or 0,
            "documents": db.scalar("SELECT count(*) FROM assets WHERE status='active' AND category='documents'"),
            "guideline_pages": db.scalar("SELECT count(*) FROM guideline_pages WHERE status='active' AND kind IN ('DocumentPage','CoverPage','DocumentLibrary')"),
            "deleted_assets": db.scalar("SELECT count(*) FROM assets WHERE status='deleted'"),
            "chunks": db.scalar("SELECT count(*) FROM chunks"),
            "last_sync": history.last_sync(db), "job": jobs.status(), "progress": _last_progress(),
        }

    def _last_progress() -> dict[str, Any] | None:
        ev = [e for e in bus.history({"progress"})]
        return ev[-1]["data"] if ev else None

    # --------------------------------------------------------------- explorer
    @app.get("/api/brands")
    def brands() -> list[dict[str, Any]]:
        return db.query("""SELECT b.id, b.name, b.slug, b.status,
            (SELECT count(*) FROM assets a WHERE a.brand_id=b.id AND a.status='active') AS assets,
            (SELECT count(*) FROM folders f WHERE f.brand_id=b.id AND f.status='active') AS folders,
            (SELECT count(*) FROM guideline_pages g WHERE g.brand_id=b.id AND g.status='active' AND g.kind IN ('DocumentPage','CoverPage','DocumentLibrary')) AS guideline_pages
            FROM brands b ORDER BY b.name""")

    @app.get("/api/brands/{brand_id}/tree")
    def tree(brand_id: str) -> dict[str, Any]:
        return {
            "containers": db.query("SELECT id,kind,name,expected_assets,scan_complete FROM containers WHERE brand_id=? AND status='active' ORDER BY kind,name", (brand_id,)),
            "folders": db.query("SELECT id,container_id,parent_id,name,path FROM folders WHERE brand_id=? AND status='active' ORDER BY path", (brand_id,)),
            "guidelines": db.query("SELECT id,parent_id,guideline_id,title,url,kind,path,position,export_status FROM guideline_pages WHERE brand_id=? AND status='active' ORDER BY guideline_id,path", (brand_id,)),
        }

    @app.get("/api/assets")
    def assets(brand_id: str | None = None, folder_id: str | None = None, container_id: str | None = None, category: str | None = None,
               status: str | None = None, q: str | None = None, limit: int = Query(100, le=500), offset: int = 0) -> dict[str, Any]:
        where, p = ["a.status!='deleted'"], []
        for col, val in (("brand_id", brand_id), ("folder_id", folder_id), ("container_id", container_id), ("category", category), ("download_status", status)):
            if val:
                where.append(f"a.{col}=?")
                p.append(val)
        if q:
            where.append("(a.title LIKE ? OR a.filename LIKE ?)")
            p += [f"%{q}%", f"%{q}%"]
        w = " AND ".join(where)
        total = db.scalar(f"SELECT count(*) FROM assets a WHERE {w}", p)
        rows = db.query(f"""SELECT id,brand_id,title,filename,extension,mime,size,category,folder_path,created_at,modified_at,
                            download_status,local_path,sha256,error,duplicate_of FROM assets a WHERE {w}
                            ORDER BY folder_path,title LIMIT ? OFFSET ?""", p + [limit, offset])
        return {"total": total, "items": rows}

    @app.get("/api/assets/{asset_id}")
    def asset(asset_id: str) -> dict[str, Any]:
        r = db.one("SELECT * FROM assets WHERE id=?", (asset_id,))
        if not r:
            raise HTTPException(404, "Unknown asset")
        raw = json.loads(r.pop("raw") or "{}")
        raw.pop("downloadUrl", None)
        rel = db.query("SELECT rel,dst_type,dst_id FROM relationships WHERE src_id=? ", (asset_id,))
        return {**r, "frontify": raw, "relationships": rel}

    @app.get("/api/guidelines/{page_id}")
    def guideline(page_id: str) -> dict[str, Any]:
        r = db.one("SELECT * FROM guideline_pages WHERE id=?", (page_id,))
        if not r:
            raise HTTPException(404, "Unknown page")
        md = Path(r["markdown_path"]).read_text("utf-8") if r["markdown_path"] and Path(r["markdown_path"]).exists() else None
        return {"id": r["id"], "title": r["title"], "path": r["path"], "url": r["url"], "kind": r["kind"], "export_status": r["export_status"], "markdown": md}

    # ----------------------------------------------------------- sync / report
    @app.get("/api/sync/history")
    def sync_history() -> list[dict[str, Any]]:
        return history.list_runs(db)

    @app.get("/api/sync/{run_id}/changes")
    def sync_changes(run_id: int) -> list[dict[str, Any]]:
        return history.run_changes(db, run_id)

    @app.get("/api/report")
    def report() -> Any:
        f = cfg.export_path / "global" / "export_report.json"
        if not f.exists():
            return JSONResponse({"available": False})
        return json.loads(f.read_text("utf-8"))

    @app.get("/api/failures")
    def failures() -> dict[str, Any]:
        return {
            "assets": db.query("SELECT id,title,folder_path,download_status,error,attempts FROM assets WHERE status='active' AND download_status IN ('failed','unavailable') ORDER BY title LIMIT 500"),
            "pages": db.query("SELECT id,title,export_status,error FROM guideline_pages WHERE export_status IN ('failed','inaccessible')"),
        }

    # ------------------------------------------------------------------ search
    @app.get("/api/search")
    def search(q: str, brand_id: str | None = None, k: int = Query(8, le=50)) -> dict[str, Any]:
        embedder = None
        try:
            embedder = make_embedder(str(cfg.get("embeddings_provider")), str(cfg.get("embeddings_model")), cfg.openai_key)
        except Exception as exc:
            log.warning("embeddings unavailable for search: %s", exc)
        store = None
        try:
            store = make_store(str(cfg.get("vector_store")), db, Path(base.data_dir), str(cfg.get("qdrant_url")))
        except Exception:
            pass
        return {"results": Searcher(db, embedder, store).search(q, k, brand_id)}

    # ----------------------------------------------------------------- frontend
    dist = Path(base.web_dist)
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="static") if (dist / "assets").exists() else None

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            if path.startswith("api/"):
                raise HTTPException(404)
            f = (dist / path).resolve()
            if path and f.is_file() and dist.resolve() in f.parents:
                return FileResponse(f)
            return FileResponse(dist / "index.html")
    return app


def app_factory() -> FastAPI:  # uvicorn --factory src.api.app:app_factory
    return create_app()
