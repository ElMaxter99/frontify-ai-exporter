"""Orchestration: analyze (read-only) and export (full)."""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

import httpx

from src.config import normalize_domain
from src.exporter.docs import DocWriter
from src.exporter.download import Downloader
from src.exporter.extract import extract_text
from src.exporter.guidelines import GuidelineExporter
from src.exporter.layout import Layout, State
from src.exporter.progress import Progress, ProgressLogHandler
from src.exporter.scan import Scanner
from src.frontify.client import FrontifyAuthError, FrontifyClient, FrontifyError
from src.utils.files import human_size, safe_name, sha256_file, utcnow_iso, write_json, write_text
from src.utils.logging import RedactingFilter, register_secret

log = logging.getLogger("exporter")

LIMITATIONS = [
    "Frontify's GraphQL API exposes no PDF export of guidelines: guidelines are exported as Markdown + raw JSON. PDF files stored as assets are downloaded normally.",
    "Assets embedded in guideline blocks only expose a previewUrl (no id) in the API: previews are saved next to the page; originals come from the library crawl.",
    "The API has no design-token or component queries; DESIGN_SYSTEM.md uses Brand Essentials (colors, fonts) and guideline pages.",
    "Assets are classified into LOGOS/IMAGES/PHOTOGRAPHY/ICONS/ILLUSTRATIONS by name/folder heuristics (no such flag exists in the API).",
    "Not exported: asset variants, revisions, comments, licenses, workflows, creative templates.",
]


class Exporter:
    def __init__(self, url: str, token: str, dest: str | Path, *, client_name: str | None = None, concurrency: int = 4,
                 page_size: int = 50, progress: Progress | None = None, api_transport: httpx.AsyncBaseTransport | None = None,
                 download_transport: httpx.AsyncBaseTransport | None = None, api_base_url: str | None = None) -> None:
        self.domain = normalize_domain(url)
        self.token = token.strip()
        self.dest = Path(dest).expanduser().resolve()
        self.client_name = safe_name(client_name or self.domain.split(".")[0] or "client", "client")
        self.client_dir = self.dest / self.client_name
        self.concurrency, self.page_size = concurrency, page_size
        self.progress = progress or Progress()
        self.api_transport, self.download_transport, self.api_base_url = api_transport, download_transport, api_base_url
        self._scanner: Scanner | None = None
        self._downloader: Downloader | None = None
        register_secret(self.token)

    def cancel(self) -> None:
        self.progress.cancelled = True
        for x in (self._scanner, self._downloader):
            if x:
                x.cancelled = True

    def _client(self) -> FrontifyClient:
        if not self.domain:
            raise FrontifyError("Enter the Frontify URL (e.g. https://acme.frontify.com)")
        if not self.token:
            raise FrontifyAuthError("Enter the API token")
        return FrontifyClient(self.domain, self.token, concurrency=self.concurrency, transport=self.api_transport, base_url=self.api_base_url)

    # --------------------------------------------------------------- analyze
    async def analyze(self) -> dict[str, Any]:
        p = self.progress
        p.reset()
        p.running, p.phase = True, "connecting"
        handler = ProgressLogHandler(p)
        logging.getLogger().addHandler(handler)
        try:
            async with self._client() as client:
                p.phase = "analyzing"
                self._scanner = Scanner(client, p, page_size=self.page_size, include_related=False)
                inv = await self._scanner.scan()
                summary = self._analysis(inv, self._scanner.errors, client.partial_errors)
            p.phase, p.result = "analyzed", {"kind": "analysis", **summary}
            return summary
        except FrontifyError as exc:
            p.phase, p.message = "failed", str(exc)
            p.result = {"kind": "error", "error": str(exc)}
            raise
        finally:
            p.running = False
            logging.getLogger().removeHandler(handler)

    @staticmethod
    def _analysis(inv: dict[str, Any], errors: list[dict[str, Any]], partial: list[dict[str, Any]]) -> dict[str, Any]:
        cats: dict[str, int] = {}
        for b in inv["brands"]:
            for a in b["assets"]:
                cats[a["category"]] = cats.get(a["category"], 0) + 1
        return {
            "brands": [b["name"] for b in inv["brands"]],
            "libraries_workspaces": sum(len(b["containers"]) for b in inv["brands"]),
            "folders": sum(len(b["folders"]) for b in inv["brands"]),
            "assets": sum(len(b["assets"]) for b in inv["brands"]),
            "bytes": sum(int(a.get("size") or 0) for b in inv["brands"] for a in b["assets"]),
            "by_type": cats,
            "guideline_pages": sum(1 for b in inv["brands"] for n in b["nav"] if n["kind"] in ("DocumentPage", "CoverPage", "DocumentLibrary")),
            "errors": errors, "inaccessible_partial": partial[:50], "api_capabilities": inv["api_capabilities"],
        }

    # ---------------------------------------------------------------- export
    async def export(self) -> dict[str, Any]:
        p = self.progress
        p.reset()
        p.running, p.phase = True, "connecting"
        self.client_dir.mkdir(parents=True, exist_ok=True)
        p.folder = str(self.client_dir)
        handler = ProgressLogHandler(p)
        fh = logging.FileHandler(self.client_dir / "export.log", encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        fh.addFilter(RedactingFilter())
        root = logging.getLogger()
        root.addHandler(handler)
        root.addHandler(fh)
        started = utcnow_iso()
        t0 = time.time()
        status, fatal = "completed", None
        report: dict[str, Any] = {}
        try:
            async with self._client() as client:
                p.phase = "analyzing"
                self._scanner = Scanner(client, p, page_size=self.page_size)
                inv = await self._scanner.scan()
                scan_errors, partial = list(self._scanner.errors), list(client.partial_errors)
                layout = Layout(self.client_dir, inv["brands"])
                state = State(self.client_dir / ".export_state.json")
                pairs = [(b["id"], a) for b in inv["brands"] for a in b["assets"]]
                p.found = len(pairs)

                p.phase = "downloading"
                dl = Downloader(client, layout, state, p, concurrency=self.concurrency, transport=self.download_transport)
                self._downloader = dl
                try:
                    results = {} if p.cancelled else await dl.run(pairs)
                finally:
                    await dl.aclose()

                p.phase = "guidelines"
                ge = GuidelineExporter(client, layout, state, p, transport=self.download_transport, concurrency=self.concurrency)
                page_results: list[dict[str, Any]] = []
                try:
                    for b in inv["brands"]:
                        if not p.cancelled:
                            page_results += await ge.run(b, results)
                finally:
                    await ge.aclose()
                    state.save()

                p.phase = "documents"
                text_files = await asyncio.to_thread(self._extract_documents, inv, results, layout, p)

                p.phase = "writing"
                report = self._report(inv, results, page_results, scan_errors, partial, text_files, started)
                writer = DocWriter(layout, inv, results, page_results, text_files, client_name=self.client_name, domain=self.domain)
                writer.write_metadata()
                writer.write_ai(report["summary"])
                if p.cancelled:
                    status = "cancelled"
                self._finish(report, layout, results, status, started, t0)
        except FrontifyError as exc:
            status, fatal = "failed", str(exc)
            log.error("export aborted: %s", exc)
            p.message = str(exc)
            write_json(self.client_dir / "EXPORT_REPORT.json", {"status": "failed", "error": str(exc), "started_at": started, "finished_at": utcnow_iso()})
        except Exception as exc:
            status, fatal = "failed", f"{type(exc).__name__}: {exc}"
            log.exception("unexpected failure")
            p.message = fatal
            write_json(self.client_dir / "EXPORT_REPORT.json", {"status": "failed", "error": fatal, "started_at": started, "finished_at": utcnow_iso()})
        finally:
            p.running = False
            p.phase = "done" if status in ("completed", "cancelled") else "failed"
            p.result = {"kind": "export", "status": status, "error": fatal, "summary": (report or {}).get("summary"), "folder": str(self.client_dir)}
            root.removeHandler(handler)
            root.removeHandler(fh)
            fh.close()
        return report or {"status": status, "error": fatal}

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def _extract_documents(inv: dict[str, Any], results: dict[str, dict[str, Any]], layout: Layout, p: Progress) -> dict[str, str]:
        out: dict[str, str] = {}
        for b in inv["brands"]:
            for a in b["assets"]:
                r = results.get(a["id"]) or {}
                if a["category"] != "documents" or not r.get("path"):
                    continue
                p.documents += 1
                got = extract_text(layout.root / r["path"], a.get("extension"))
                if got:
                    dest = layout.dir("docs") / layout.brand(b["id"]) / "_extracted_text" / f"{safe_name(a.get('title') or a['id'])[:80]}-{a['id']}.md"
                    write_text(dest, f"---\nsource_file: \"{r['path']}\"\nfrontify_id: \"{a['id']}\"\nextraction: {got[1]}\nextracted_at: {utcnow_iso()}\n---\n\n# {a.get('title')}\n\n{got[0]}\n")
                    out[a["id"]] = layout.rel(dest)
        return out

    def _report(self, inv: dict[str, Any], results: dict[str, dict[str, Any]], pages: list[dict[str, Any]], scan_errors: list[dict[str, Any]],
                partial: list[dict[str, Any]], text_files: dict[str, str], started: str) -> dict[str, Any]:
        by = {s: 0 for s in ("downloaded", "unchanged", "failed", "unavailable")}
        not_exported: list[dict[str, Any]] = []
        titles = {a["id"]: a for b in inv["brands"] for a in b["assets"]}
        for aid, a in titles.items():
            r = results.get(aid)
            st = r["status"] if r else "not attempted"
            if st in by:
                by[st] += 1
            if st in ("failed", "unavailable") or r is None:
                not_exported.append({"type": "asset", "id": aid, "name": a.get("title"), "folder": a.get("folder_path"), "status": st,
                                     "reason": (r or {}).get("reason") or "export cancelled before this file"})
        for pg in pages:
            if pg["status"] in ("failed", "inaccessible"):
                not_exported.append({"type": "guideline_page", "id": pg["id"], "name": pg["title"], "status": pg["status"], "reason": pg.get("reason")})
        pg_found = sum(1 for b in inv["brands"] for n in b["nav"] if n["kind"] in ("DocumentPage", "CoverPage", "DocumentLibrary"))
        pg_ok = sum(1 for pg in pages if pg["status"] in ("exported", "unchanged"))
        n_assets = len(titles)
        ok_assets = by["downloaded"] + by["unchanged"]
        summary = {
            "assets_found": n_assets, "assets_downloaded": by["downloaded"], "assets_unchanged": by["unchanged"],
            "assets_failed": by["failed"], "assets_unavailable": by["unavailable"],
            "bytes_downloaded": sum(int(r.get("size") or 0) for r in results.values() if r.get("status") == "downloaded"),
            "duplicates_detected": sum(1 for r in results.values() if r.get("duplicate_of")),
            "guideline_pages_found": pg_found, "guideline_pages_exported": pg_ok,
            "documents_processed": pg_ok + sum(1 for a in titles.values() if a["category"] == "documents" and (results.get(a["id"]) or {}).get("path")),
            "document_texts_extracted": len(text_files),
            "total_items_found": n_assets + pg_found, "total_items_exported": ok_assets + pg_ok,
            "brands": len(inv["brands"]), "folders": sum(len(b["folders"]) for b in inv["brands"]),
            "libraries_workspaces": sum(len(b["containers"]) for b in inv["brands"]),
            "collections": sum(len(b["collections"]) for b in inv["brands"]),
            "errors": len(not_exported) + len(scan_errors),
        }
        return {"client": self.client_name, "frontify_domain": self.domain, "started_at": started, "summary": summary,
                "not_exported": not_exported, "scan_errors": scan_errors,
                "inaccessible_due_to_permissions_or_api": [{"path": e.get("path"), "operation": e.get("operation"), "message": e.get("message")} for e in partial[:300]],
                "skipped_unchanged": [{"id": i, "name": titles[i].get("title")} for i, r in results.items() if r.get("status") == "unchanged"][:2000],
                "duplicates": [{"id": i, "duplicate_of": r["duplicate_of"], "path": r.get("path")} for i, r in results.items() if r.get("duplicate_of")],
                "api_capabilities": inv["api_capabilities"], "limitations": LIMITATIONS}

    def _finish(self, report: dict[str, Any], layout: Layout, results: dict[str, dict[str, Any]], status: str, started: str, t0: float) -> None:
        report.update(status=status, finished_at=utcnow_iso(), duration_seconds=round(time.time() - t0, 1))
        write_json(layout.root / "EXPORT_REPORT.json", report)
        files = {}
        for sub in ("guidelines", "assets", "docs", "design", "meta", "ai"):
            for f in sorted(layout.dir(sub).rglob("*")) if layout.dir(sub).exists() else []:
                if f.is_file() and not f.name.endswith(".part"):
                    files[layout.rel(f)] = {"bytes": f.stat().st_size, "sha256": results_hash(f, results, layout)}
        write_json(layout.root / "manifest.json", {"generator": "frontify-exporter", "generated_at": utcnow_iso(), "frontify_domain": self.domain,
                                                   "summary": report["summary"], "files": files})
        log.info("Export %s: %s", status, human_size(report["summary"]["bytes_downloaded"]) + " downloaded")


def results_hash(f: Path, results: dict[str, dict[str, Any]], layout: Layout) -> str:
    rel = layout.rel(f)
    for r in results.values():
        if r.get("path") == rel and r.get("sha256"):
            return r["sha256"]  # already computed (and verified) while downloading
    return sha256_file(f)
