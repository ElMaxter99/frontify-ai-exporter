"""Full discovery of everything the token can see: brands, libraries, workspaces, folders,
assets, collections, guideline structure, brand essentials. Results go to SQLite with change detection."""
from __future__ import annotations

import asyncio
import json
import logging
from collections import Counter
from typing import Any

from src.assets.classify import category_for, mime_for
from src.database.repo import Repo
from src.frontify import queries as Q
from src.frontify.client import FrontifyClient, FrontifyError, FrontifyGraphQLError
from src.utils.events import EventBus
from src.utils.files import utcnow_iso, utcnow_precise

log = logging.getLogger("scanner")

CHILD_KEYS = {
    "GuidelineDocumentNavigationItem": "docChildren",
    "GuidelineDocumentGroupNavigationItem": "groupChildren",
    "GuidelineDocumentPageCategoryNavigationItem": "catChildren",
}


class Scanner:
    def __init__(self, client: FrontifyClient, repo: Repo, bus: EventBus, *, page_size: int = 50,
                 include_related: bool = True, run_id: int | None = None) -> None:
        self.client, self.repo, self.bus = client, repo, bus
        self.page_size = page_size
        self.include_related = include_related
        self.run_id = run_id
        self.level = 0
        self.counts: Counter[str] = Counter()
        self.errors: list[dict[str, Any]] = []
        self.seen = utcnow_precise()
        self._cancel = asyncio.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def _change(self, entity: str, eid: str, change: str, name: str, brand_id: str) -> None:
        if change in ("unchanged", None):
            self.counts[f"{entity}_unchanged"] += 1
            return
        self.counts[f"{entity}_{change}"] += 1
        if self.run_id:
            self.repo.record_change(self.run_id, entity, eid, change, name or "", brand_id)

    def _err(self, where: str, exc: Exception) -> None:
        log.error("scan error in %s: %s", where, exc)
        self.errors.append({"where": where, "error": str(exc)})

    def _progress(self, phase: str, **kw: Any) -> None:
        self.bus.publish("progress", {"phase": phase, **kw, "counts": dict(self.counts)})

    # ------------------------------------------------------------------ main
    async def scan(self, brand_ids: set[str] | None = None) -> dict[str, Any]:
        self._progress("brands")
        data = await self.client.execute(Q.ACCOUNT_BRANDS, operation="Brands")
        brands = [b for b in (data.get("brands") or []) if b]
        log.info("Frontify returned %d accessible brand(s)", len(brands))
        if brand_ids is None:
            for old in self.repo.db.query("SELECT id FROM brands WHERE status='active'"):
                if old["id"] not in {b["id"] for b in brands}:
                    self.repo.db.execute("UPDATE brands SET status='deleted' WHERE id=?", (old["id"],))
                    self._change("brand", old["id"], "deleted", "", old["id"])
        for b in brands:
            if brand_ids and b["id"] not in brand_ids:
                continue
            if self._cancel.is_set():
                break
            self._change("brand", b["id"], self.repo.upsert_brand(b, self.seen), b.get("name", ""), b["id"])
            try:
                await self._scan_brand(b)
            except FrontifyError as exc:
                self._err(f"brand {b.get('name')}", exc)
        summary = {"counts": dict(self.counts), "errors": self.errors, "api_requests": self.client.request_count,
                   "partial_graphql_errors": len(self.client.partial_errors)}
        self._progress("scan_done")
        return summary

    async def _scan_brand(self, brand: dict[str, Any]) -> None:
        bid = brand["id"]
        log.info("Scanning brand %s", brand.get("name"))
        containers: list[tuple[str, dict[str, Any]]] = []
        for kind, q, key, op in (("library", Q.BRAND_LIBRARIES, "libraries", "BrandLibraries"),
                                 ("workspace", Q.BRAND_WORKSPACES, "workspaceProjects", "BrandWorkspaces")):
            try:
                for c in await self.client.collect(q, ["brand", key], {"id": bid}, page_size=self.page_size, operation=op):
                    containers.append((kind, c))
            except FrontifyError as exc:
                self._err(f"{key} of {brand.get('name')}", exc)
        for kind, c in containers:
            if self._cancel.is_set():
                return
            self._change(kind, c["id"], self.repo.upsert_container(bid, kind, c, self.seen), c.get("name", ""), bid)
        await asyncio.gather(*(self._scan_container(bid, k, c) for k, c in containers))
        await self._scan_essentials(bid)
        await self._scan_guidelines(brand)
        if self.include_related:
            await self._scan_related(bid)

    # ---------------------------------------------------------- assets crawl
    async def _scan_container(self, brand_id: str, kind: str, c: dict[str, Any]) -> None:
        cid, cname = c["id"], c.get("name") or c["id"]
        log.info("Crawling %s '%s'", kind, cname)
        start_errors = len(self.errors)
        expected: int | None = None
        try:
            q, path = Q.container_total_query(kind)
            data = await self.client.execute(q, {"id": cid}, operation="ContainerTotal")
            node = data
            for k in path:
                node = (node or {}).get(k)
            expected = (node or {}).get("total")
        except FrontifyError as exc:
            log.warning("could not read expected asset total for %s: %s", cname, exc)
        found_before = self.counts["asset_seen"]
        await self._crawl(brand_id, cid, kind, cid, None, cname)
        found = self.counts["asset_seen"] - found_before
        complete = len(self.errors) == start_errors
        if expected is not None and found < expected:
            log.warning("%s '%s': crawl found %d assets but Frontify reports %d (assets may lack folder visibility)", kind, cname, found, expected)
            self.errors.append({"where": f"{kind} {cname}", "error": f"found {found} of {expected} assets"})
            complete = False
        self.repo.set_container_scan(cid, expected, complete)
        if complete:
            for a in self.repo.mark_missing("assets", brand_id, cid, self.seen):
                self._change("asset", a["id"], "deleted", a["name"], brand_id)
            for f in self.repo.mark_missing("folders", brand_id, cid, self.seen):
                self._change("folder", f["id"], "deleted", f["name"], brand_id)
        else:
            log.warning("%s '%s' scan incomplete: deletion detection skipped", kind, cname)
        if kind == "library":
            await self._scan_collections(brand_id, cid)

    async def _crawl(self, brand_id: str, container_id: str, root_kind: str, node_id: str,
                     folder_id: str | None, path: str) -> None:
        """Assets and sub folders of one place (root of container, or a folder)."""
        if self._cancel.is_set():
            return
        kind = "folder" if folder_id else root_kind
        await self._crawl_assets(brand_id, container_id, kind, node_id, folder_id, path)
        try:
            q, qpath = Q.folders_query(kind)
            folders = await self.client.collect(q, qpath, {"id": node_id}, page_size=self.page_size, operation="Folders")
        except FrontifyError as exc:
            self._err(f"folders of {path}", exc)
            return
        subs = []
        for f in folders:
            fpath = f"{path}/{f.get('name')}"
            self._change("folder", f["id"], self.repo.upsert_folder(brand_id, container_id, folder_id, f, fpath, self.seen), f.get("name", ""), brand_id)
            subs.append(self._crawl(brand_id, container_id, root_kind, f["id"], f["id"], fpath))
        if subs:
            await asyncio.gather(*subs)

    async def _crawl_assets(self, brand_id: str, container_id: str, kind: str, node_id: str,
                            folder_id: str | None, path: str) -> None:
        while True:
            q, qpath = Q.assets_query(kind, self.level)
            items: list[dict[str, Any]] = []
            try:
                async for a in self.client.paginate(q, qpath, {"id": node_id}, page_size=self.page_size, operation="Assets"):
                    items.append(a)
            except FrontifyGraphQLError as exc:
                if exc.is_validation and self.level < len(Q.ASSET_LEVELS) - 1:
                    self.level += 1
                    log.warning("asset query rejected by this Frontify instance; falling back to detail level %d: %s", self.level, exc)
                    continue
                self._err(f"assets of {path}", exc)
                return
            except FrontifyError as exc:
                self._err(f"assets of {path}", exc)
                return
            break
        for a in items:
            ext = a.get("extension")
            cat = category_for(ext, path, a.get("title"), a.get("filename"))
            mime = mime_for(a.get("filename"), ext)
            self.counts["asset_seen"] += 1
            self._change("asset", a["id"], self.repo.upsert_asset(brand_id, container_id, folder_id, path, a, cat, mime, self.seen),
                         a.get("title", ""), brand_id)
        self._progress("assets", path=path)

    async def _scan_collections(self, brand_id: str, library_id: str) -> None:
        try:
            cols = await self.client.collect(Q.LIBRARY_COLLECTIONS, ["library", "collections"], {"id": library_id},
                                             page_size=self.page_size, operation="LibraryCollections")
            for col in cols:
                ids = await self.client.collect(Q.COLLECTION_ASSETS, ["node", "assets"], {"id": col["id"]},
                                                page_size=self.page_size, operation="CollectionAssets")
                self.repo.add_relationships([("collection", col["id"], "contains", "asset", i["id"], brand_id) for i in ids])
                self.repo.add_relationships([("library", library_id, "has_collection", "collection", col["id"], brand_id)])
                self.repo.db.execute("INSERT OR REPLACE INTO collections(id,brand_id,library_id,name) VALUES (?,?,?,?)",
                                     (col["id"], brand_id, library_id, col.get("name")))
                self.counts["collections"] += 1
        except FrontifyError as exc:
            self._err(f"collections of library {library_id}", exc)

    async def _scan_related(self, brand_id: str) -> None:
        ids = [r["id"] for r in self.repo.db.query("SELECT id FROM assets WHERE brand_id=? AND status='active'", (brand_id,))]
        for i in range(0, len(ids), 25):
            try:
                data = await self.client.execute(Q.ASSETS_RELATED, {"ids": ids[i:i + 25]}, operation="AssetRelated")
            except FrontifyError as exc:
                self._err("related assets", exc)
                return
            for a in data.get("assets") or []:
                if a and (a.get("relatedAssets") or {}).get("items"):
                    self.repo.add_relationships([("asset", a["id"], "related", "asset", r["id"], brand_id)
                                                 for r in a["relatedAssets"]["items"] if r])

    # ------------------------------------------------------------ essentials
    async def _scan_essentials(self, brand_id: str) -> None:
        try:
            data = await self.client.execute(Q.BRAND_ESSENTIALS, {"id": brand_id}, operation="BrandEssentials")
            ess = (data.get("brand") or {}).get("essentials")
            self.repo.db.execute("INSERT OR REPLACE INTO essentials(brand_id, raw, fetched_at) VALUES (?,?,?)",
                                 (brand_id, json.dumps(ess, default=str), utcnow_iso()))
            self.counts["essentials"] += 1
        except FrontifyError as exc:
            self._err(f"brand essentials {brand_id}", exc)

    # ----------------------------------------------------------- guidelines
    async def _scan_guidelines(self, brand: dict[str, Any]) -> None:
        bid = brand["id"]
        try:
            guidelines = await self.client.collect(Q.BRAND_GUIDELINES, ["brand", "guidelines"], {"id": bid},
                                                   page_size=self.page_size, operation="BrandGuidelines")
        except FrontifyError as exc:
            self._err(f"guidelines of {brand.get('name')}", exc)
            return
        for g in guidelines:
            gname = g.get("name") or g["id"]
            root = {"id": g["id"], "brand_id": bid, "guideline_id": g["id"], "parent_id": None, "title": gname,
                    "url": g.get("url"), "kind": "Guideline", "path": gname, "position": 0, "raw": g}
            self._change("guideline", g["id"], self.repo.upsert_guideline_page(root, self.seen), gname, bid)
            try:
                nav = await self.client.collect(Q.GUIDELINE_NAV, ["node", "navigation"], {"id": g["id"]},
                                                page_size=100, operation="GuidelineNav")
                await self._walk_nav(bid, g["id"], g["id"], gname, nav)
            except FrontifyError as exc:
                self._err(f"navigation of guideline {gname}", exc)

    async def _walk_nav(self, brand_id: str, guideline_id: str, parent_id: str, path: str, items: list[dict[str, Any]]) -> None:
        for pos, it in enumerate(items):
            kind = it.get("__typename", "")
            if not it.get("id"):
                continue
            title = it.get("title") or it["id"]
            ipath = f"{path}/{title}"
            rec = {"id": it["id"], "brand_id": brand_id, "guideline_id": guideline_id, "parent_id": parent_id, "title": title,
                   "url": it.get("url"), "kind": kind.replace("Guideline", "", 1).replace("NavigationItem", ""),
                   "path": ipath, "position": pos, "hidden": it.get("isHiddenInNavigation"), "raw": it}
            self._change("guideline_page", it["id"], self.repo.upsert_guideline_page(rec, self.seen), title, brand_id)
            if kind == "GuidelineDocumentLibraryNavigationItem":
                await self._scan_library_page(brand_id, it["id"])
            ckey = CHILD_KEYS.get(kind)
            if ckey:
                try:
                    children = await self._nav_children(it["id"], ckey)
                    await self._walk_nav(brand_id, guideline_id, it["id"], ipath, children)
                except FrontifyError as exc:
                    self._err(f"children of {ipath}", exc)

    async def _nav_children(self, item_id: str, key: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        page = 1
        while True:
            data = await self.client.execute(Q.NAV_CHILDREN, {"id": item_id, "page": page, "limit": 100}, operation="NavChildren")
            conn = (data.get("guidelineNavigationItem") or {}).get(key) or {}
            out += [c for c in conn.get("items") or [] if c]
            if not conn.get("hasNextPage"):
                return out
            page += 1

    async def _scan_library_page(self, brand_id: str, page_id: str) -> None:
        try:
            ids = await self.client.collect(Q.LIBRARY_PAGE_ASSETS, ["node", "assets"], {"id": page_id},
                                            page_size=self.page_size, operation="LibraryPageAssets")
            self.repo.add_relationships([("guideline_page", page_id, "shows", "asset", i["id"], brand_id) for i in ids if i.get("id")])
        except FrontifyError as exc:
            self._err(f"assets of library page {page_id}", exc)
