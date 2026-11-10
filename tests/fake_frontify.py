# SPDX-License-Identifier: Apache-2.0
"""An in-process fake of the Frontify GraphQL API + CDN, built on httpx.MockTransport.

It implements only what the exporter queries (dispatching on the document's operation name)
and serves data from a mutable ``FakeFrontify.state`` so incremental syncs can be tested."""
from __future__ import annotations

import io
import json
import re
from typing import Any

import httpx
from PIL import Image

TOKEN = "test-token-123456"
CDN = "https://cdn.test"


def png_bytes(color: str = "red") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 4), color).save(buf, "PNG")
    return buf.getvalue()


def conn(items: list[Any], page: int, limit: int) -> dict[str, Any]:
    start = (page - 1) * limit
    return {"total": len(items), "page": page, "limit": limit, "hasNextPage": start + limit < len(items),
            "items": items[start:start + limit]}


def asset(id_: str, title: str, ext: str, size: int, typename: str = "File", modified: str = "2025-01-01T00:00:00Z", **kw: Any) -> dict[str, Any]:
    return {"__typename": typename, "id": id_, "title": title, "description": kw.pop("description", None), "alternativeText": None,
            "externalId": None, "createdAt": "2024-01-01T00:00:00Z", "modifiedAt": modified, "expiresAt": None, "author": "Jane",
            "status": "FINISHED", "creator": {"id": "u1", "name": "Jane"}, "modifier": None, "tags": [{"value": "brand", "source": "MANUAL"}],
            "customMetadata": [], "filename": f"{title}.{ext}", "size": size, "extension": ext, "fileCreatedAt": "2024-01-01T00:00:00Z",
            "previewUrl": f"{CDN}/preview/{id_}", "thumbnailUrl": None, "downloadUrl": f"{CDN}/dl/{id_}", **kw}


class FakeFrontify:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {
            "a1": png_bytes("red"), "a2": b"<svg xmlns='http://www.w3.org/2000/svg'><title>Icon</title></svg>",
            "a3": b"Brand voice: friendly and direct.\nAlways keep clear space around the logo.\n", "a4": b"# Notes\nWeekly notes",
            "a6": b"will-404",
        }
        self.state: dict[str, Any] = {}
        self.reset()
        self.requests: list[str] = []
        self.downloads: list[str] = []
        self.fail_once: dict[str, int] = {}
        self.cdn_404: set[str] = {"a6"}
        self.transport = httpx.MockTransport(self.handle)

    def reset(self) -> None:
        f = self.files
        self.state = {
            "brands": [{"id": "b1", "name": "Acme Corp", "slug": "acme", "avatar": None}],
            "libraries": [{"id": "l1", "name": "Logos"}, {"id": "l2", "name": "Docs"}],
            "folders": {"l1": [{"id": "f1", "name": "Primary", "createdAt": "2024-01-01T00:00:00Z", "modifiedAt": None}],
                        "f1": [{"id": "f2", "name": "Dark", "createdAt": "2024-01-01T00:00:00Z", "modifiedAt": None}]},
            "assets": {
                "l1": [asset("a1", "Acme Logo", "png", len(f["a1"]), "Image", width=8, height=4)],
                "f1": [asset("a2", "Icon Set", "svg", len(f["a2"]), "Image", width=1, height=1, description="Icons for UI")],
                "f2": [asset("a3", "Voice Guide", "txt", len(f["a3"]), "Document", width=0, height=0, pageCount=1)],
                "l2": [asset("a4", "Notes", "md", len(f["a4"]), "Document", width=0, height=0, pageCount=1),
                       asset("a5", "Protected", "pdf", 10, "Document", width=0, height=0, pageCount=1, downloadUrl=None),
                       asset("a6", "Broken", "bin", 7, "File")],
            },
            "guidelines": [{"id": "g1", "name": "Brand Book", "url": "https://acme.frontify.com/d/g1"}],
            "nav": {"g1": [
                {"__typename": "GuidelineCoverPageNavigationItem", "id": "cv1", "title": "Cover", "url": "/cover"},
                {"__typename": "GuidelineDocumentNavigationItem", "id": "d1", "title": "Foundations", "url": "/d/d1", "isHiddenInNavigation": False},
                {"__typename": "GuidelineDocumentLibraryNavigationItem", "id": "lp1", "title": "Logo library", "url": "/d/lp1",
                 "isHiddenInNavigation": False, "libraryType": "LOGO"}]},
            "children": {
                "d1": ("docChildren", [
                    {"__typename": "GuidelineDocumentPageNavigationItem", "id": "p1", "title": "Logo usage", "url": "/p1", "isHiddenInNavigation": False, "isPublished": True},
                    {"__typename": "GuidelineDocumentPageCategoryNavigationItem", "id": "c1", "title": "Voice", "url": "/c1"}]),
                "c1": ("catChildren", [
                    {"__typename": "GuidelineDocumentPageNavigationItem", "id": "p2", "title": "Tone of voice", "url": "/p2", "isHiddenInNavigation": False, "isPublished": True}]),
            },
            "pages": {
                "cv1": {"id": "cv1", "title": "Cover", "url": "/cover", "modifiedAt": "2025-01-01T00:00:00Z", "sections": [[]]},
                "p1": {"id": "p1", "title": "Logo usage", "url": "/p1", "modifiedAt": "2025-01-01T00:00:00Z", "sections": [[
                    {"__typename": "GuidelinePageHeading", "id": "h1", "title": "Clear space", "url": "/p1#h1", "modifiedAt": "2025-01-01T00:00:00Z"},
                    {"__typename": "GuidelinePageBlock", "id": "bl1", "url": "/p1#bl1", "modifiedAt": "2025-01-01T00:00:00Z",
                     "content": "Keep clear space equal to the height of the A around the logo.", "settings": {}, "type": {"id": "t1", "name": "Text"},
                     "assetSettings": {"total": 1, "items": [{"settingName": "images", "assets": {"total": 1, "items": [{"previewUrl": f"{CDN}/preview/a1"}]}}]}},
                ]]},
                "p2": {"id": "p2", "title": "Tone of voice", "url": "/p2", "modifiedAt": "2025-01-01T00:00:00Z", "sections": [[
                    {"__typename": "GuidelinePageBlock", "id": "bl2", "url": "/p2#bl2", "modifiedAt": "2025-01-01T00:00:00Z",
                     "content": "We are friendly, direct and optimistic.", "settings": {}, "type": {"id": "t1", "name": "Text"}, "assetSettings": None},
                    {"__typename": "BrandEssentialsColorBlock", "id": "bl3", "url": "/p2#bl3", "modifiedAt": "2025-01-01T00:00:00Z",
                     "content": None, "settings": {"palette": "main"}, "type": {"id": "t2", "name": "Color"}, "assetSettings": None},
                ]]},
            },
            "library_page_assets": {"lp1": ["a1"]},
            "collections": {"l1": [{"id": "col1", "name": "Hero"}]}, "collection_assets": {"col1": ["a1", "a2"]},
            "related": {"a1": ["a2"]},
            "essentials": {"colorPalettes": {"total": 1, "hasNextPage": False, "items": [{"id": "pal1", "name": "Core", "description": "Main palette",
                "colors": {"total": 1, "hasNextPage": False, "items": [{"id": "c1", "name": "Acme Red", "description": "Primary",
                    "representations": {"hex": {"name": "HEX", "value": "#E4002B"}, "pantone": {"name": "Pantone", "value": "186 C"},
                                        "pantoneCoated": None, "pantoneUncoated": None}}]}}]},
                "fontFamilies": {"total": 1, "hasNextPage": False, "items": [{"id": "ff1", "name": "Acme Sans", "cssName": "Acme Sans", "provider": "SELFHOSTED",
                    "fontStyles": [{"name": "Regular", "weight": 400, "isItalic": False}]}]}},
        }

    def all_assets(self) -> dict[str, dict[str, Any]]:
        return {a["id"]: a for lst in self.state["assets"].values() for a in lst}

    # ------------------------------------------------------------------ http
    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "cdn.test":
            return self._cdn(request)
        assert request.url.path == "/graphql", request.url
        assert request.headers["authorization"] == f"Bearer {TOKEN}"
        body = json.loads(request.content)
        op, v = body.get("operationName"), body.get("variables") or {}
        self.requests.append(op or "?")
        if self.fail_once.get(op, 0) > 0:
            self.fail_once[op] -= 1
            return httpx.Response(503, json={"errors": [{"message": "unavailable"}]})
        fn = getattr(self, f"op_{op}", None)
        if fn is None:
            return httpx.Response(200, json={"errors": [{"message": f"Cannot query field (unknown op {op})", "extensions": {"code": "GRAPHQL_VALIDATION_FAILED"}}]})
        return httpx.Response(200, json={"data": fn(v)})

    def _cdn(self, request: httpx.Request) -> httpx.Response:
        parts = request.url.path.strip("/").split("/")
        if parts[0] == "preview":
            return httpx.Response(200, content=png_bytes("blue"), headers={"content-type": "image/png"})
        aid = parts[1]
        self.downloads.append(aid)
        if aid in self.cdn_404 or aid not in self.files:
            return httpx.Response(404)
        data = self.files[aid]
        rng = request.headers.get("range")
        if rng:
            start = int(re.match(r"bytes=(\d+)-", rng).group(1))  # type: ignore[union-attr]
            return httpx.Response(206, content=data[start:], headers={"content-range": f"bytes {start}-{len(data) - 1}/{len(data)}"})
        return httpx.Response(200, content=data)

    # ------------------------------------------------------------- operations
    def op_Caps(self, v):
        return {"__schema": {"queryType": {"fields": [{"name": n} for n in ("brands", "brand", "library", "assets", "node", "guidelinePage")]}}}

    def op_CurrentUser(self, v):
        return {"currentUser": {"id": "u1", "name": "Jane"}}

    def op_Brands(self, v):
        return {"brands": self.state["brands"]}

    def op_BrandLibraries(self, v):
        return {"brand": {"libraries": conn(self.state["libraries"], v["page"], v["limit"])}}

    def op_BrandWorkspaces(self, v):
        return {"brand": {"workspaceProjects": conn([], v["page"], v["limit"])}}

    def op_RootFolders(self, v):
        return {"library": {"browse": {"folders": conn(self.state["folders"].get(v["id"], []), v["page"], v["limit"])}}}

    def op_FolderChildren(self, v):
        return {"node": {"folders": conn(self.state["folders"].get(v["id"], []), v["page"], v["limit"])}}

    def op_RootAssets(self, v):
        return {"library": {"browse": {"assets": conn(self.state["assets"].get(v["id"], []), v["page"], v["limit"])}}}

    def op_FolderAssets(self, v):
        return {"node": {"assets": conn(self.state["assets"].get(v["id"], []), v["page"], v["limit"])}}

    def op_ContainerTotal(self, v):
        def count(node: str) -> int:
            return len(self.state["assets"].get(node, [])) + sum(count(f["id"]) for f in self.state["folders"].get(node, []))
        return {"library": {"assets": {"total": count(v["id"])}}}

    def op_LibraryCollections(self, v):
        return {"library": {"collections": conn(self.state["collections"].get(v["id"], []), v["page"], v["limit"])}}

    def op_CollectionAssets(self, v):
        return {"node": {"assets": conn([{"id": i} for i in self.state["collection_assets"][v["id"]]], v["page"], v["limit"])}}

    def op_AssetDownloadUrls(self, v):
        allx = self.all_assets()
        return {"assets": [{"id": i, "downloadUrl": allx[i]["downloadUrl"]} for i in v["ids"] if i in allx]}

    def op_AssetRelated(self, v):
        return {"assets": [{"id": i, "relatedAssets": {"total": len(self.state["related"].get(i, [])),
                                                       "items": [{"id": r} for r in self.state["related"].get(i, [])]}} for i in v["ids"]]}

    def op_BrandGuidelines(self, v):
        return {"brand": {"guidelines": conn(self.state["guidelines"], v["page"], v["limit"])}}

    def op_GuidelineNav(self, v):
        return {"node": {"navigation": conn(self.state["nav"][v["id"]], v["page"], v["limit"])}}

    def op_NavChildren(self, v):
        key, items = self.state["children"].get(v["id"], ("docChildren", []))
        return {"guidelineNavigationItem": {"__typename": "x", key: conn(items, v["page"], v["limit"])}}

    def op_GuidelinePageContent(self, v):
        p = self.state["pages"].get(v["id"])
        if not p:
            return {"guidelinePage": None}
        secs = [{"id": f"s{i}", "elements": conn(els, v["elementsPage"], 100)} for i, els in enumerate(p["sections"])]
        return {"guidelinePage": {"id": p["id"], "title": p["title"], "url": p["url"], "modifiedAt": p["modifiedAt"],
                                  "sections": conn(secs, v["page"], v["limit"])}}

    def op_LibraryPageAssets(self, v):
        return {"node": {"assets": conn([{"id": i} for i in self.state["library_page_assets"].get(v["id"], [])], v["page"], v["limit"])}}

    def op_BrandEssentials(self, v):
        return {"brand": {"essentials": self.state["essentials"]}}
