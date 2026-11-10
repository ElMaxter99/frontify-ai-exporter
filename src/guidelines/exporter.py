"""Export guideline pages: original JSON, Markdown, embedded-asset previews, change detection."""
from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
from pathlib import Path
from typing import Any

import httpx

from src.database.repo import Repo
from src.exporter.layout import Layout
from src.frontify import queries as Q
from src.frontify.client import FrontifyClient, FrontifyError, FrontifyGraphQLError
from src.guidelines.markdown import render_library_page, render_page
from src.utils.events import EventBus
from src.utils.files import safe_name, sha1_text, slugify, utcnow_iso, write_json, write_text

log = logging.getLogger("guidelines")

CONTENT_KINDS = {"DocumentPage", "CoverPage"}
LIBRARY_KIND = "DocumentLibrary"


class GuidelineExporter:
    def __init__(self, client: FrontifyClient, repo: Repo, bus: EventBus, layout: Layout, *, run_id: int | None = None,
                 transport: httpx.AsyncBaseTransport | None = None, concurrency: int = 4) -> None:
        self.client, self.repo, self.bus, self.layout, self.run_id = client, repo, bus, layout, run_id
        self._http = httpx.AsyncClient(transport=transport, follow_redirects=True, timeout=60.0)
        self.sem = asyncio.Semaphore(concurrency)
        self.with_assets = True
        self.stats = {"pages": 0, "new": 0, "modified": 0, "unchanged": 0, "failed": 0, "media": 0}

    async def aclose(self) -> None:
        await self._http.aclose()

    async def run(self, brand_ids: set[str] | None = None) -> dict[str, Any]:
        pages = self.repo.db.query(
            "SELECT * FROM guideline_pages WHERE status='active' ORDER BY brand_id, guideline_id, path")
        targets = [p for p in pages if (not brand_ids or p["brand_id"] in brand_ids) and p["kind"] in CONTENT_KINDS | {LIBRARY_KIND}]
        log.info("Exporting %d guideline page(s)", len(targets))
        done = 0

        async def one(p: dict[str, Any]) -> None:
            nonlocal done
            async with self.sem:
                try:
                    await self._export_page(p)
                except Exception as exc:
                    log.error("guideline page %s '%s' failed: %s", p["id"], p["title"], exc)
                    self.repo.db.execute("UPDATE guideline_pages SET export_status='failed', error=? WHERE id=?", (str(exc)[:500], p["id"]))
                    self.stats["failed"] += 1
                done += 1
                self.bus.publish("progress", {"phase": "guidelines", "done": done, "total": len(targets), **self.stats})

        await asyncio.gather(*(one(p) for p in targets))
        self._write_index()
        return dict(self.stats)

    def _write_pdf_note(self, brand_id: str) -> None:
        d = self.layout.brand_dir(brand_id) / "guidelines" / "pdf"
        if not d.exists() or not any(d.iterdir()):
            write_text(d / "README.txt", "Frontify's GraphQL API does not expose a PDF export of guidelines, so none can be generated "
                       "legitimately here. Guideline content is in ../markdown (readable) and ../original (raw API JSON). "
                       "PDF files that exist as assets in your libraries are exported under assets/documents/.\n")

    # ----------------------------------------------------------------- fetching
    async def _query(self, pid: str, spage: int, epage: int) -> dict[str, Any]:
        while True:
            try:
                return await self.client.execute(Q.guideline_page_query(self.with_assets),
                                                 {"id": pid, "page": spage, "limit": 50, "elementsPage": epage},
                                                 operation="GuidelinePageContent")
            except FrontifyGraphQLError as exc:
                if exc.is_validation and self.with_assets:
                    log.warning("block asset settings rejected; retrying without them: %s", exc)
                    self.with_assets = False
                    continue
                raise

    async def fetch_page(self, pid: str) -> tuple[dict[str, Any], list[list[dict[str, Any]]]] | None:
        order: list[str] = []
        sections: dict[str, list[dict[str, Any]]] = {}
        meta: dict[str, Any] | None = None
        spage = 1
        while True:
            epage, pending = 1, True
            conn: dict[str, Any] = {}
            while pending:
                data = await self._query(pid, spage, epage)
                gp = data.get("guidelinePage")
                if not gp:
                    return None
                meta = {k: gp.get(k) for k in ("id", "title", "url", "modifiedAt")}
                conn = gp.get("sections") or {}
                pending = False
                for s in conn.get("items") or []:
                    if not s:
                        continue
                    if s["id"] not in sections:
                        sections[s["id"]] = []
                        order.append(s["id"])
                    els = s.get("elements") or {}
                    sections[s["id"]] += [e for e in els.get("items") or [] if e]
                    pending = pending or bool(els.get("hasNextPage"))
                epage += 1
            if not conn.get("hasNextPage"):
                break
            spage += 1
        return (meta or {}), [sections[i] for i in order]

    # ---------------------------------------------------------------- exporting
    def _page_file(self, p: dict[str, Any], ext: str) -> Path:
        parts = [safe_name(x, "page") for x in (p["path"] or "").split("/") if x]
        # prefix with sibling position to keep Frontify's reading order, e.g. 03-logo-usage.md
        parts[-1] = f"{int(p.get('position') or 0):02d}-{slugify(parts[-1])}"
        return self.layout.brand_dir(p["brand_id"]) / "guidelines" / ext / Path(*parts[:-1]) / f"{parts[-1]}.{'md' if ext == 'markdown' else 'json'}"

    async def _export_page(self, p: dict[str, Any]) -> None:
        brand = self.repo.db.one("SELECT name FROM brands WHERE id=?", (p["brand_id"],)) or {}
        now = utcnow_iso()
        if p["kind"] == LIBRARY_KIND:
            rows = self.repo.db.query(
                """SELECT a.id,a.title,a.local_path,json_extract(a.raw,'$.description') AS description FROM relationships r
                   JOIN assets a ON a.id=r.dst_id WHERE r.src_id=? AND r.rel='shows' AND a.status='active' ORDER BY a.title""", (p["id"],))
            assets = [{**r, "rel_path": self._rel_to_brand(p["brand_id"], r["local_path"])} for r in rows]
            md = render_library_page({"id": p["id"], "title": p["title"], "url": p["url"]}, assets,
                                     brand=brand.get("name", ""), brand_id=p["brand_id"], path=p["path"], extracted_at=now)
            raw: Any = {"page": {"id": p["id"], "title": p["title"], "url": p["url"]}, "assets": assets}
            modified = None
        else:
            fetched = await self.fetch_page(p["id"])
            if fetched is None:
                self.repo.db.execute("UPDATE guideline_pages SET export_status='inaccessible', error='page not returned by API' WHERE id=?", (p["id"],))
                self.stats["failed"] += 1
                return
            meta, sections = fetched
            media = await self._download_media(p, sections)
            md = render_page(meta, sections, brand=brand.get("name", ""), brand_id=p["brand_id"], path=p["path"],
                             extracted_at=now, media=media)
            raw = {"page": meta, "sections": sections, "navigation": json.loads(p["raw"] or "{}")}
            modified = meta.get("modifiedAt")
        chash = sha1_text(json.dumps(raw, sort_keys=True, default=str))
        md_path = self._page_file(p, "markdown")
        change = self.repo.set_page_content(p["id"], modified, chash, str(md_path), "done")
        if change != "unchanged" or not md_path.exists():
            write_text(md_path, md)
            write_json(self._page_file(p, "original"), raw)
        self.stats["pages"] += 1
        self.stats[change] += 1
        if change != "unchanged" and self.run_id:
            self.repo.record_change(self.run_id, "guideline_content", p["id"], change, p["title"] or "", p["brand_id"])

    def _rel_to_brand(self, brand_id: str, local: str | None) -> str | None:
        if not local:
            return None
        try:
            return Path(local).relative_to(self.layout.brand_dir(brand_id)).as_posix()
        except ValueError:
            return local

    async def _download_media(self, p: dict[str, Any], sections: list[list[dict[str, Any]]]) -> dict[str, list[str]]:
        """Fetch the preview image of every asset referenced by a block (best effort).

        The API exposes only ``previewUrl`` for these references (no asset id), so these are previews of
        what the page shows; the ORIGINAL files are exported from the libraries."""
        media: dict[str, list[str]] = {}
        base = self._page_file(p, "markdown").parent
        for elements in sections:
            for el in elements:
                blk = (el.get("block") if el.get("__typename") == "GuidelinePageBlockReference" else el) or {}
                n = 0
                for setting in ((blk.get("assetSettings") or {}).get("items") or []):
                    for a in ((setting or {}).get("assets") or {}).get("items") or []:
                        url = (a or {}).get("previewUrl")
                        if not url:
                            continue
                        n += 1
                        try:
                            r = await self._http.get(url)
                            r.raise_for_status()
                            ext = mimetypes.guess_extension((r.headers.get("content-type") or "").split(";")[0]) or ".bin"
                            dest = self.layout.brand_dir(p["brand_id"]) / "guidelines" / "original" / "media" / f"{p['id']}-{blk.get('id')}-{n}{ext}"
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            dest.write_bytes(r.content)
                            media.setdefault(blk.get("id", ""), []).append(Path(_relpath(dest, base)).as_posix())
                            self.stats["media"] += 1
                        except Exception as exc:
                            log.warning("could not fetch embedded preview for block %s: %s", blk.get("id"), type(exc).__name__)
        return media

    def _write_index(self) -> None:
        """Navigation tree per brand (original/navigation.json) so the hierarchy is never lost."""
        for b in self.repo.db.query("SELECT DISTINCT brand_id FROM guideline_pages WHERE status='active'"):
            rows = self.repo.db.query(
                "SELECT id,parent_id,guideline_id,title,url,kind,path,position,hidden,export_status,markdown_path FROM guideline_pages "
                "WHERE brand_id=? AND status='active' ORDER BY guideline_id, path", (b["brand_id"],))
            write_json(self.layout.brand_dir(b["brand_id"]) / "guidelines" / "original" / "navigation.json", rows)
            self._write_pdf_note(b["brand_id"])


def _relpath(target: Path, start: Path) -> str:
    import os

    return os.path.relpath(target, start)
