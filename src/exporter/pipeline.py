"""Orchestrates scan -> download -> guidelines -> knowledge -> index -> metadata -> manifest/report."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from src.ai.embeddings import make_embedder
from src.ai.indexer import Indexer
from src.ai.knowledge import build_knowledge
from src.ai.vectorstore import make_store
from src.assets.downloader import AssetDownloader
from src.config import RuntimeConfig
from src.database.db import Database
from src.database.repo import Repo
from src.exporter.layout import Layout
from src.exporter.scanner import Scanner
from src.frontify.client import FrontifyClient
from src.guidelines.exporter import GuidelineExporter
from src.metadata.writer import build_inventory, write_brand_metadata
from src.utils.events import EventBus
from src.utils.files import human_size, sha256_file, utcnow_iso, write_json

log = logging.getLogger("pipeline")
VERSION = "0.1.0"


@dataclass
class ExportOptions:
    brand_ids: set[str] | None = None
    categories: set[str] | None = None
    scan: bool = True
    download: bool = True
    guidelines: bool = True
    knowledge: bool = True
    index: bool = True
    force: bool = False          # re-download everything, ignoring change detection
    kind: str = "export"

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ExportOptions:
        def s(k: str) -> set[str] | None:
            v = d.get(k)
            return set(v) if v else None
        return cls(brand_ids=s("brand_ids"), categories=s("categories"),
                   **{k: bool(d[k]) for k in ("scan", "download", "guidelines", "knowledge", "index", "force") if k in d},
                   kind=d.get("kind", "export"))


@dataclass
class Pipeline:
    cfg: RuntimeConfig
    db: Database
    bus: EventBus
    api_transport: httpx.AsyncBaseTransport | None = None
    download_transport: httpx.AsyncBaseTransport | None = None
    api_base_url: str | None = None
    _scanner: Scanner | None = field(default=None, repr=False)
    _downloader: AssetDownloader | None = field(default=None, repr=False)
    _cancelled: bool = field(default=False, repr=False)

    def cancel(self) -> None:
        self._cancelled = True
        for x in (self._scanner, self._downloader):
            if x:
                x.cancel()

    def make_client(self) -> FrontifyClient:
        return FrontifyClient(self.cfg.domain, self.cfg.token, timeout=self.cfg.base.request_timeout,
                              max_retries=self.cfg.base.max_retries, concurrency=int(self.cfg.get("api_concurrency")),
                              transport=self.api_transport, base_url=self.api_base_url)

    async def run(self, opts: ExportOptions) -> dict[str, Any]:
        t0 = time.time()
        repo = Repo(self.db)
        root = self.cfg.export_path
        root.mkdir(parents=True, exist_ok=True)
        run_id = repo.start_run(opts.kind)
        report: dict[str, Any] = {"run_id": run_id, "kind": opts.kind, "started_at": utcnow_iso(), "options": {
            "brand_ids": sorted(opts.brand_ids or []), "categories": sorted(opts.categories or []), "force": opts.force}}
        status = "completed"
        client = self.make_client()
        try:
            if opts.scan:
                self._scanner = Scanner(client, repo, self.bus, page_size=int(self.cfg.get("page_size")),
                                        include_related=bool(self.cfg.get("include_related_assets")), run_id=run_id)
                report["scan"] = await self._scanner.scan(opts.brand_ids)
            layout = Layout(self.db, root)
            if opts.download and not self._cancelled:
                dl = AssetDownloader(client, repo, self.bus, layout, concurrency=int(self.cfg.get("download_concurrency")),
                                     dedupe_hardlinks=bool(self.cfg.get("dedupe_hardlinks")), transport=self.download_transport)
                self._downloader = dl
                try:
                    report["downloads"] = await dl.run(opts.brand_ids, opts.categories, opts.force)
                finally:
                    await dl.aclose()
            if opts.guidelines and not self._cancelled:
                ge = GuidelineExporter(client, repo, self.bus, layout, run_id=run_id, transport=self.download_transport,
                                       concurrency=int(self.cfg.get("api_concurrency")))
                try:
                    report["guidelines"] = await ge.run(opts.brand_ids)
                finally:
                    await ge.aclose()
            if (opts.knowledge or opts.index) and not self._cancelled:
                report["knowledge"] = await asyncio.to_thread(self._knowledge, layout, opts, report)
            if self._cancelled:
                status = "cancelled"
            file_meta = (report.get("knowledge") or {}).pop("_file_meta", {})
            await asyncio.to_thread(self._metadata, layout, opts, file_meta, report)
            report["api_requests"] = client.request_count
            report["partial_graphql_errors"] = client.partial_errors[:200]
        except asyncio.CancelledError:
            status = "cancelled"
            raise
        except Exception as exc:
            status = "failed"
            log.exception("export failed")
            report["fatal_error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            await client.aclose()
            report.update(self._summary(repo, run_id))
            report["status"] = status
            report["finished_at"] = utcnow_iso()
            report["duration_seconds"] = round(time.time() - t0, 1)
            try:
                self._write_global(Layout(self.db, root), report)
            except Exception:  # never mask the original error
                log.exception("could not write final report")
            repo.finish_run(run_id, status, {k: report[k] for k in report if k not in ("partial_graphql_errors",)})
        return report

    # ------------------------------------------------------------------ steps
    def _knowledge(self, layout: Layout, opts: ExportOptions, report: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        brands = [b["id"] for b in self.db.query("SELECT id FROM brands WHERE status='active'") if not opts.brand_ids or b["id"] in opts.brand_ids]
        if opts.knowledge:
            for b in brands:
                build_knowledge(self.db, layout, b, self.cfg.domain)
            out["knowledge_files"] = len(brands) * 7
        if opts.index:
            embedder = None
            try:
                embedder = make_embedder(str(self.cfg.get("embeddings_provider")), str(self.cfg.get("embeddings_model")), self.cfg.openai_key)
            except Exception as exc:
                log.error("embeddings disabled: %s", exc)
                out["embeddings_error"] = str(exc)
            store = None
            try:
                store = make_store(str(self.cfg.get("vector_store")), self.db, Path(self.cfg.base.data_dir), str(self.cfg.get("qdrant_url")))
            except Exception as exc:
                log.error("vector store '%s' unavailable, falling back to sqlite: %s", self.cfg.get("vector_store"), exc)
                out["vector_store_error"] = str(exc)
            idx = Indexer(self.db, layout, self.bus, domain=self.cfg.domain, embedder=embedder, store=store,
                          ocr=bool(self.cfg.get("ocr_enabled")), cache_dir=Path(self.cfg.base.data_dir) / "text_cache")
            res = idx.run(opts.brand_ids)
            out["_file_meta"] = res.pop("file_metadata")
            out.update(res)
        return out

    def _metadata(self, layout: Layout, opts: ExportOptions, file_meta: dict[str, Any], report: dict[str, Any]) -> None:
        report["metadata"] = {}
        for b in self.db.query("SELECT id, name FROM brands WHERE status='active'"):
            if opts.brand_ids and b["id"] not in opts.brand_ids:
                continue
            report["metadata"][b["name"]] = write_brand_metadata(self.db, layout, b["id"], file_meta)

    # ---------------------------------------------------------------- reports
    def _summary(self, repo: Repo, run_id: int) -> dict[str, Any]:
        db = self.db
        failed = db.query("SELECT id,title,folder_path,error,attempts FROM assets WHERE download_status='failed' AND status='active'")
        unavailable = db.query("SELECT id,title,folder_path,error FROM assets WHERE download_status='unavailable' AND status='active'")
        changes = db.query("SELECT entity, change, count(*) n FROM changes WHERE run_id=? GROUP BY entity, change", (run_id,))
        total_bytes = db.scalar("SELECT coalesce(sum(size),0) FROM assets WHERE status='active' AND download_status='done'")
        pages_failed = db.query("SELECT id,title,error FROM guideline_pages WHERE export_status IN ('failed','inaccessible')")
        return {
            "totals": {
                "brands": db.scalar("SELECT count(*) FROM brands WHERE status='active'"),
                "assets": db.scalar("SELECT count(*) FROM assets WHERE status='active'"),
                "assets_downloaded": db.scalar("SELECT count(*) FROM assets WHERE status='active' AND download_status='done'"),
                "bytes_downloaded": db.scalar("SELECT coalesce(sum(size),0) FROM assets WHERE status='active' AND download_status='done'"),
                "assets_inaccessible_or_deleted": db.scalar("SELECT count(*) FROM assets WHERE status='deleted'"),
                "duplicates": db.scalar("SELECT count(*) FROM assets WHERE duplicate_of IS NOT NULL AND status='active'"),
                "guideline_pages": db.scalar("SELECT count(*) FROM guideline_pages WHERE status='active' AND markdown_path IS NOT NULL"),
                "chunks": db.scalar("SELECT count(*) FROM chunks"),
            },
            "changes_this_run": changes,
            "failed_assets": failed,
            "unavailable_assets": unavailable,
            "failed_guideline_pages": pages_failed,
            "human": f"{human_size(total_bytes)} exported",
        }

    def _write_global(self, layout: Layout, report: dict[str, Any]) -> None:
        g = layout.root / "global"
        write_json(g / "inventory.json", build_inventory(self.db, layout))
        write_json(g / "export_report.json", report)
        brands = []
        for b in self.db.query("SELECT id,name,slug FROM brands WHERE status='active'"):
            d = layout.brand_dir(b["id"])
            kn = d / "knowledge"
            brands.append({"id": b["id"], "name": b["name"], "dir": layout.rel(d),
                           "knowledge_files": {p.name: {"bytes": p.stat().st_size, "sha256": sha256_file(p)}
                                               for p in sorted(kn.glob("*")) if p.is_file()} if kn.exists() else {}})
        write_json(layout.root / "manifest.json", {
            "generator": "frontify-ai-exporter", "version": VERSION, "generated_at": utcnow_iso(), "frontify_domain": self.cfg.domain,
            "run_id": report.get("run_id"), "totals": report.get("totals"), "brands": brands,
            "notes": "Originals are stored untouched under brands/*/assets. Everything under knowledge/ is derived text; "
                     "each chunk in chunks.jsonl carries its provenance (brand, source file, Frontify id, folder, extraction date).",
            "layout": ["brands/<brand>/assets/<category>/<library>/<folder...>", "brands/<brand>/guidelines/{markdown,original,pdf}",
                       "brands/<brand>/metadata/*.json", "brands/<brand>/knowledge/*.md|chunks.jsonl", "global/{inventory,export_report}.json"]})
