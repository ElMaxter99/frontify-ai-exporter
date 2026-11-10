# SPDX-License-Identifier: Apache-2.0
"""Export every guideline page: Markdown (hierarchy kept) + raw API JSON + embedded previews."""
from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import os
from pathlib import Path
from typing import Any

import httpx

from src.exporter.layout import DIRS, Layout, State
from src.exporter.progress import Progress
from src.frontify import queries as Q
from src.frontify.client import FrontifyClient, FrontifyGraphQLError
from src.guidelines.markdown import render_library_page, render_page
from src.utils.files import safe_name, sha1_text, slugify, utcnow_iso, write_json, write_text

log = logging.getLogger("guidelines")
CONTENT_KINDS = {"DocumentPage", "CoverPage"}
LIBRARY_KIND = "DocumentLibrary"


class GuidelineExporter:
    def __init__(self, client: FrontifyClient, layout: Layout, state: State, progress: Progress,
                 transport: httpx.AsyncBaseTransport | None = None, concurrency: int = 4) -> None:
        self.client, self.layout, self.state, self.progress = client, layout, state, progress
        self._http = httpx.AsyncClient(transport=transport, follow_redirects=True, timeout=60.0)
        self.sem = asyncio.Semaphore(concurrency)
        self.with_assets = True
        self.results: list[dict[str, Any]] = []

    async def aclose(self) -> None:
        await self._http.aclose()

    async def run(self, brand: dict[str, Any], asset_paths: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        targets = [p for p in brand["nav"] if p["kind"] in CONTENT_KINDS | {LIBRARY_KIND}]
        base = self.layout.dir("guidelines") / self.layout.brand(brand["id"])
        write_json(base / "_original" / "navigation.json", brand["nav"])

        async def one(p: dict[str, Any]) -> None:
            async with self.sem:
                try:
                    res = await self._page(brand, p, base, asset_paths)
                except Exception as exc:
                    log.error("FAILED guideline page %s: %s", p["title"], exc)
                    res = {"status": "failed", "reason": f"{type(exc).__name__}: {exc}"}
                    self.progress.errors += 1
                self.results.append({"id": p["id"], "title": p["title"], "path": p["path"], "url": p.get("url"), "kind": p["kind"],
                                     "brand_id": brand["id"], **res})
                if res["status"] in ("exported", "unchanged"):
                    self.progress.documents += 1

        await asyncio.gather(*(one(p) for p in targets))
        return self.results

    def _file(self, base: Path, p: dict[str, Any], kind: str) -> Path:
        parts = [safe_name(x, "page") for x in p["path"].split("/") if x]
        parts[-1] = f"{int(p.get('position') or 0):02d}-{slugify(parts[-1], 'page')}"
        if kind == "md":
            return base.joinpath(*parts[:-1], f"{parts[-1]}.md")
        return base.joinpath("_original", *parts[:-1], f"{parts[-1]}.json")

    async def _page(self, brand: dict[str, Any], p: dict[str, Any], base: Path, asset_paths: dict[str, dict[str, Any]]) -> dict[str, Any]:
        now = utcnow_iso()
        md_path, json_path = self._file(base, p, "md"), self._file(base, p, "json")
        if p["kind"] == LIBRARY_KIND:
            assets = []
            for aid in brand["library_page_assets"].get(p["id"], []):
                a = next((x for x in brand["assets"] if x["id"] == aid), None)
                if a:
                    assets.append({"id": aid, "title": a.get("title"), "description": a.get("description"),
                                   "rel_path": (asset_paths.get(aid) or {}).get("path")})
            md = render_library_page({"id": p["id"], "title": p["title"], "url": p.get("url")}, assets, brand=brand["name"] or "",
                                     brand_id=brand["id"], path=p["path"], extracted_at=now)
            raw: Any = {"page": {"id": p["id"], "title": p["title"], "url": p.get("url")}, "assets": assets}
        else:
            fetched = await self._fetch(p["id"])
            if fetched is None:
                return {"status": "inaccessible", "reason": "page not returned by the API (permissions, unpublished or unsupported page type)"}
            meta, sections = fetched
            media = await self._media(brand, p, sections, md_path)
            md = render_page(meta, sections, brand=brand["name"] or "", brand_id=brand["id"], path=p["path"], extracted_at=now, media=media)
            raw = {"page": meta, "sections": sections, "navigation": p}
        h = sha1_text(json.dumps(raw, sort_keys=True, default=str))
        if self.state.pages.get(p["id"]) == h and md_path.exists():
            return {"status": "unchanged", "file": self.layout.rel(md_path)}
        write_text(md_path, md)
        write_json(json_path, raw)
        self.state.pages[p["id"]] = h
        return {"status": "exported", "file": self.layout.rel(md_path), "original_json": self.layout.rel(json_path)}

    async def _query(self, pid: str, spage: int, epage: int) -> dict[str, Any]:
        while True:
            try:
                return await self.client.execute(Q.guideline_page_query(self.with_assets),
                                                 {"id": pid, "page": spage, "limit": 50, "elementsPage": epage})
            except FrontifyGraphQLError as exc:
                if exc.is_validation and self.with_assets:
                    log.warning("block asset settings rejected; retrying without them: %s", exc)
                    self.with_assets = False
                    continue
                raise

    async def _fetch(self, pid: str) -> tuple[dict[str, Any], list[list[dict[str, Any]]]] | None:
        order: list[str] = []
        secs: dict[str, list[dict[str, Any]]] = {}
        meta: dict[str, Any] = {}
        spage = 1
        while True:
            epage, pending = 1, True
            conn: dict[str, Any] = {}
            while pending:
                gp = (await self._query(pid, spage, epage)).get("guidelinePage")
                if not gp:
                    return None
                meta = {k: gp.get(k) for k in ("id", "title", "url", "modifiedAt")}
                conn, pending = gp.get("sections") or {}, False
                for s in conn.get("items") or []:
                    if not s:
                        continue
                    if s["id"] not in secs:
                        secs[s["id"]] = []
                        order.append(s["id"])
                    els = s.get("elements") or {}
                    secs[s["id"]] += [e for e in els.get("items") or [] if e]
                    pending = pending or bool(els.get("hasNextPage"))
                epage += 1
            if not conn.get("hasNextPage"):
                return meta, [secs[i] for i in order]
            spage += 1

    async def _media(self, brand: dict[str, Any], p: dict[str, Any], sections: list[list[dict[str, Any]]], md_path: Path) -> dict[str, list[str]]:
        """Previews of assets embedded in blocks (the API gives only previewUrl for these, no asset id)."""
        out: dict[str, list[str]] = {}
        mdir = self.layout.dir("guidelines") / self.layout.brand(brand["id"]) / "_media"
        for els in sections:
            for el in els:
                blk = (el.get("block") if el.get("__typename") == "GuidelinePageBlockReference" else el) or {}
                n = 0
                for st in (blk.get("assetSettings") or {}).get("items") or []:
                    for a in ((st or {}).get("assets") or {}).get("items") or []:
                        url = (a or {}).get("previewUrl")
                        if not url:
                            continue
                        n += 1
                        try:
                            r = await self._http.get(url)
                            r.raise_for_status()
                            ext = mimetypes.guess_extension((r.headers.get("content-type") or "").split(";")[0]) or ".bin"
                            dest = mdir / f"{p['id']}-{blk.get('id')}-{n}{ext}"
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            dest.write_bytes(r.content)
                            out.setdefault(blk.get("id", ""), []).append(Path(os.path.relpath(dest, md_path.parent)).as_posix())
                        except Exception as exc:
                            log.warning("embedded preview not fetched (block %s): %s", blk.get("id"), type(exc).__name__)
        return out


__all__ = ["GuidelineExporter", "DIRS"]
