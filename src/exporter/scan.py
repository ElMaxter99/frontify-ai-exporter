# SPDX-License-Identifier: Apache-2.0
"""Discover everything the token can access and keep it in memory (no database)."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.assets.classify import category_for, mime_for
from src.exporter.progress import Progress
from src.frontify import queries as Q
from src.frontify.client import FrontifyClient, FrontifyError, FrontifyGraphQLError
from src.utils.files import sha1_text

log = logging.getLogger("scan")

CHILD_KEYS = {
    "GuidelineDocumentNavigationItem": "docChildren",
    "GuidelineDocumentGroupNavigationItem": "groupChildren",
    "GuidelineDocumentPageCategoryNavigationItem": "catChildren",
}
CAPS = "query Caps { __schema { queryType { fields { name } } } }"


class Scanner:
    def __init__(self, client: FrontifyClient, progress: Progress, *, page_size: int = 50, include_related: bool = True) -> None:
        self.client, self.progress, self.page_size, self.include_related = client, progress, page_size, include_related
        self.level = 0
        self.errors: list[dict[str, Any]] = []
        self.cancelled = False
        self._found: dict[str, int] = {}

    def _err(self, where: str, exc: Exception | str) -> None:
        log.error("%s: %s", where, exc)
        self.errors.append({"where": where, "reason": str(exc)})
        self.progress.errors += 1

    # ------------------------------------------------------------------ main
    async def scan(self) -> dict[str, Any]:
        inv: dict[str, Any] = {"brands": [], "api_capabilities": await self._capabilities()}
        data = await self.client.execute(Q.ACCOUNT_BRANDS)
        brands = [b for b in data.get("brands") or [] if b]
        log.info("Frontify returned %d accessible brand(s)", len(brands))
        for b in brands:
            if self.cancelled:
                break
            rec = {"id": b["id"], "name": b.get("name"), "slug": b.get("slug"), "avatar": b.get("avatar"), "containers": [],
                   "folders": [], "assets": {}, "collections": [], "related": {}, "guideline_list": [], "nav": [],
                   "library_page_assets": {}, "essentials": None}
            inv["brands"].append(rec)
            try:
                await self._brand(rec)
            except FrontifyError as exc:
                self._err(f"brand {b.get('name')}", exc)
            rec["assets"] = list(rec["assets"].values())
        return inv

    async def _capabilities(self) -> dict[str, Any]:
        try:
            d = await self.client.execute(CAPS)
            names = sorted(f["name"] for f in d["__schema"]["queryType"]["fields"])
            return {"introspection": True, "root_queries": names,
                    "design_tokens_or_components_queries": [n for n in names if any(k in n.lower() for k in ("token", "component", "designsystem"))]}
        except Exception:  # introspection may be disabled; fall back to the documented reference
            return {"introspection": False, "note": "Introspection unavailable; capabilities follow the official GraphQL reference "
                    "(no design-token or component queries exist there).", "design_tokens_or_components_queries": []}

    async def _brand(self, brand: dict[str, Any]) -> None:
        bid, name = brand["id"], brand.get("name")
        log.info("Scanning brand %s", name)
        for kind, q, key in (("library", Q.BRAND_LIBRARIES, "libraries"), ("workspace", Q.BRAND_WORKSPACES, "workspaceProjects")):
            try:
                for c in await self.client.collect(q, ["brand", key], {"id": bid}, page_size=self.page_size):
                    brand["containers"].append({"id": c["id"], "kind": kind, "name": c.get("name"), "expected_assets": None, "complete": False})
            except FrontifyError as exc:
                self._err(f"{key} of {name}", exc)
        await asyncio.gather(*(self._container(brand, c) for c in brand["containers"]))
        await self._essentials(brand)
        await self._guidelines(brand)
        if self.include_related:
            await self._related(brand)

    # ---------------------------------------------------------------- assets
    async def _container(self, brand: dict[str, Any], c: dict[str, Any]) -> None:
        cname = c["name"] or c["id"]
        before_err, before_found = len(self.errors), len(brand["assets"])
        try:
            q, path = Q.container_total_query(c["kind"])
            node: Any = await self.client.execute(q, {"id": c["id"]})
            for k in path:
                node = (node or {}).get(k)
            c["expected_assets"] = (node or {}).get("total")
        except FrontifyError as exc:
            log.warning("could not read asset total of %s: %s", cname, exc)
        log.info("Crawling %s '%s'", c["kind"], cname)
        await self._crawl(brand, c, c["kind"], c["id"], None, cname)
        found = len(brand["assets"]) - before_found
        exp = c["expected_assets"]
        if exp is not None and found < exp:
            self._err(f"{c['kind']} {cname}", f"only {found} of {exp} assets reachable through folders (permissions or API limits)")
        c["complete"] = len(self.errors) == before_err
        if c["kind"] == "library":
            await self._collections(brand, c)

    async def _crawl(self, brand: dict[str, Any], c: dict[str, Any], root_kind: str, node_id: str, folder_id: str | None, path: str) -> None:
        if self.cancelled:
            return
        kind = "folder" if folder_id else root_kind
        await self._assets(brand, c, kind, node_id, folder_id, path)
        try:
            q, qpath = Q.folders_query(kind)
            folders = await self.client.collect(q, qpath, {"id": node_id}, page_size=self.page_size)
        except FrontifyError as exc:
            self._err(f"folders of {path}", exc)
            return
        subs = []
        for f in folders:
            fpath = f"{path}/{f.get('name')}"
            brand["folders"].append({"id": f["id"], "container_id": c["id"], "parent_id": folder_id, "name": f.get("name"), "path": fpath,
                                     "created_at": f.get("createdAt"), "modified_at": f.get("modifiedAt")})
            subs.append(self._crawl(brand, c, root_kind, f["id"], f["id"], fpath))
        if subs:
            await asyncio.gather(*subs)

    async def _assets(self, brand: dict[str, Any], c: dict[str, Any], kind: str, node_id: str, folder_id: str | None, path: str) -> None:
        while True:
            q, qpath = Q.assets_query(kind, self.level)
            try:
                items = await self.client.collect(q, qpath, {"id": node_id}, page_size=self.page_size)
            except FrontifyGraphQLError as exc:
                if exc.is_validation and self.level < len(Q.ASSET_LEVELS) - 1:
                    self.level += 1
                    log.warning("asset query rejected by this instance; falling back to a smaller field set: %s", exc)
                    continue
                self._err(f"assets of {path}", exc)
                return
            except FrontifyError as exc:
                self._err(f"assets of {path}", exc)
                return
            break
        for a in items:
            ext = a.get("extension")
            rec = {k: v for k, v in a.items() if k not in ("downloadUrl",)}
            rec.update(folder_id=folder_id, folder_path=path, container_id=c["id"], container_name=c["name"],
                       category=category_for(ext, path, a.get("title"), a.get("filename")), mime=mime_for(a.get("filename"), ext),
                       fingerprint=sha1_text(a.get("modifiedAt"), a.get("fileCreatedAt"), a.get("size"), a.get("filename")))
            brand["assets"][a["id"]] = rec
        self._found[brand["id"]] = len(brand["assets"])
        self.progress.found = sum(self._found.values())

    async def _collections(self, brand: dict[str, Any], c: dict[str, Any]) -> None:
        try:
            for col in await self.client.collect(Q.LIBRARY_COLLECTIONS, ["library", "collections"], {"id": c["id"]}, page_size=self.page_size):
                ids = await self.client.collect(Q.COLLECTION_ASSETS, ["node", "assets"], {"id": col["id"]}, page_size=self.page_size)
                brand["collections"].append({"id": col["id"], "name": col.get("name"), "library_id": c["id"], "asset_ids": [i["id"] for i in ids]})
        except FrontifyError as exc:
            self._err(f"collections of library {c['name']}", exc)

    async def _related(self, brand: dict[str, Any]) -> None:
        ids = list(brand["assets"])
        for i in range(0, len(ids), 25):
            try:
                data = await self.client.execute(Q.ASSETS_RELATED, {"ids": ids[i:i + 25]})
            except FrontifyError as exc:
                self._err("related assets", exc)
                return
            for a in data.get("assets") or []:
                rel = [r["id"] for r in ((a or {}).get("relatedAssets") or {}).get("items") or [] if r]
                if rel:
                    brand["related"][a["id"]] = rel

    async def _essentials(self, brand: dict[str, Any]) -> None:
        try:
            data = await self.client.execute(Q.BRAND_ESSENTIALS, {"id": brand["id"]})
            brand["essentials"] = (data.get("brand") or {}).get("essentials")
        except FrontifyError as exc:
            self._err(f"brand essentials of {brand['name']} (colors/fonts)", exc)

    # ------------------------------------------------------------ guidelines
    async def _guidelines(self, brand: dict[str, Any]) -> None:
        try:
            gl = await self.client.collect(Q.BRAND_GUIDELINES, ["brand", "guidelines"], {"id": brand["id"]}, page_size=self.page_size)
        except FrontifyError as exc:
            self._err(f"guidelines of {brand['name']}", exc)
            return
        for g in gl:
            gname = g.get("name") or g["id"]
            brand["guideline_list"].append(g)
            brand["nav"].append({"id": g["id"], "guideline_id": g["id"], "parent_id": None, "title": gname, "url": g.get("url"),
                                 "kind": "Guideline", "path": gname, "position": 0})
            try:
                nav = await self.client.collect(Q.GUIDELINE_NAV, ["node", "navigation"], {"id": g["id"]}, page_size=100)
                await self._walk(brand, g["id"], g["id"], gname, nav)
            except FrontifyError as exc:
                self._err(f"navigation of guideline {gname}", exc)

    async def _walk(self, brand: dict[str, Any], gid: str, parent: str, path: str, items: list[dict[str, Any]]) -> None:
        for pos, it in enumerate(items):
            if not it.get("id"):
                continue
            kind = it.get("__typename", "")
            title = it.get("title") or it["id"]
            ipath = f"{path}/{title}"
            brand["nav"].append({"id": it["id"], "guideline_id": gid, "parent_id": parent, "title": title, "url": it.get("url"),
                                 "kind": kind.replace("Guideline", "", 1).replace("NavigationItem", ""), "path": ipath, "position": pos,
                                 "hidden": it.get("isHiddenInNavigation"), "published": it.get("isPublished")})
            if kind == "GuidelineDocumentLibraryNavigationItem":
                try:
                    ids = await self.client.collect(Q.LIBRARY_PAGE_ASSETS, ["node", "assets"], {"id": it["id"]}, page_size=self.page_size)
                    brand["library_page_assets"][it["id"]] = [i["id"] for i in ids if i.get("id")]
                except FrontifyError as exc:
                    self._err(f"assets of library page {title}", exc)
            key = CHILD_KEYS.get(kind)
            if key:
                try:
                    await self._walk(brand, gid, it["id"], ipath, await self._children(it["id"], key))
                except FrontifyError as exc:
                    self._err(f"children of {ipath}", exc)

    async def _children(self, item_id: str, key: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        page = 1
        while True:
            data = await self.client.execute(Q.NAV_CHILDREN, {"id": item_id, "page": page, "limit": 100})
            conn = (data.get("guidelineNavigationItem") or {}).get(key) or {}
            out += [c for c in conn.get("items") or [] if c]
            if not conn.get("hasNextPage"):
                return out
            page += 1
