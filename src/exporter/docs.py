"""05_METADATA and 06_AI_KNOWLEDGE + README_AI.md, written ONLY from data actually returned by Frontify."""
from __future__ import annotations

import re
from typing import Any

from src.exporter.extract import image_metadata
from src.exporter.layout import Layout
from src.guidelines.markdown import strip_front_matter
from src.utils.files import human_size, utcnow_iso, write_json, write_text

NA = "_Not available: Frontify did not return this information for this brand with the current token._"
KEYWORDS = {
    "visual": ["logo", "identity", "identidad", "visual", "imagery", "photo", "fotograf", "icon", "iconograf", "illustrat", "ilustra", "layout", "grid", "symbol", "brand mark"],
    "design": ["component", "token", "style", "spacing", "grid", "button", "ui ", "pattern", "design system", "digital", "web", "interface", "layout"],
}
VISUAL_CATS = ["logos", "images", "photography", "icons", "illustrations", "videos", "audio"]


def _match(page: dict[str, Any], key: str) -> bool:
    return any(k in page["path"].lower() for k in KEYWORDS[key])


def render_colors(ess: dict[str, Any] | None) -> str | None:
    pals = ((ess or {}).get("colorPalettes") or {}).get("items") or []
    if not pals:
        return None
    out: list[str] = []
    for pal in pals:
        out.append(f"#### {pal.get('name')}")
        if pal.get("description"):
            out.append(pal["description"])
        out.append("\n| Color | HEX | Pantone | Pantone Coated | Pantone Uncoated | Description |\n|---|---|---|---|---|---|")
        for c in ((pal.get("colors") or {}).get("items")) or []:
            rep = c.get("representations") or {}
            vals = [((rep.get(k) or {}).get("value")) or "—" for k in ("hex", "pantone", "pantoneCoated", "pantoneUncoated")]
            desc = (c.get("description") or "").replace("\n", " ")
            out.append(f"| {c.get('name')} | " + " | ".join(vals) + f" | {desc} |")
        out.append("")
    return "\n".join(out)


def render_fonts(ess: dict[str, Any] | None) -> str | None:
    fams = ((ess or {}).get("fontFamilies") or {}).get("items") or []
    if not fams:
        return None
    out = []
    for f in fams:
        styles = ", ".join(f"{s['name']} ({s['weight']}{', italic' if s.get('isItalic') else ''})" for s in f.get("fontStyles") or [])
        out.append(f"- **{f.get('name')}** — CSS name `{f.get('cssName')}`, provider {f.get('provider')}" + (f"; styles: {styles}" if styles else ""))
    return "\n".join(out)


class DocWriter:
    def __init__(self, layout: Layout, inv: dict[str, Any], assets: dict[str, dict[str, Any]], pages: list[dict[str, Any]],
                 text_files: dict[str, str], *, client_name: str, domain: str) -> None:
        self.l, self.inv, self.res, self.pages, self.text = layout, inv, assets, pages, text_files
        self.client_name, self.domain = client_name, domain
        self.now = utcnow_iso()

    # ----------------------------------------------------------------- helpers
    def _asset_status(self, aid: str) -> str:
        r = self.res.get(aid) or {}
        return r.get("path") or f"NOT EXPORTED ({r.get('status', 'not attempted')}: {r.get('reason') or 'n/a'})"

    def _page_text(self, p: dict[str, Any]) -> str | None:
        f = p.get("file")
        if f and (self.l.root / f).exists():
            return re.sub(r"^# .*\n", "", strip_front_matter((self.l.root / f).read_text("utf-8")), count=1).strip()
        return None

    def _header(self, title: str) -> str:
        return f"# {title}\n\n> Client: **{self.client_name}** · Source: {self.domain} · Generated {self.now} from data returned by the Frontify API. Nothing here is invented; missing data is stated explicitly.\n\n"

    # --------------------------------------------------------------- metadata
    def write_metadata(self) -> None:
        meta = self.l.dir("meta")
        write_json(meta / "api_capabilities.json", self.inv.get("api_capabilities"))
        for b in self.inv["brands"]:
            d = meta / self.l.brand(b["id"])
            recs = []
            for a in b["assets"]:
                r = self.res.get(a["id"]) or {}
                fm = None
                if r.get("path") and a.get("category") in ("images", "logos", "photography", "icons", "illustrations"):
                    fm = image_metadata(self.l.root / r["path"])
                recs.append({
                    "frontify_id": a["id"], "title": a.get("title"), "filename": a.get("filename"), "extension": a.get("extension"),
                    "mime_type": a.get("mime"), "size_bytes": a.get("size"), "category": a.get("category"), "frontify_type": a.get("__typename"),
                    "frontify_location": {"container": a.get("container_name"), "container_id": a["container_id"], "folder_id": a.get("folder_id"), "folder_path": a.get("folder_path")},
                    "created_at": a.get("createdAt"), "modified_at": a.get("modifiedAt"), "file_created_at": a.get("fileCreatedAt"),
                    "description": a.get("description"), "alternative_text": a.get("alternativeText"), "author": a.get("author"),
                    "creator": a.get("creator"), "modifier": a.get("modifier"), "tags": a.get("tags"), "custom_metadata": a.get("customMetadata"),
                    "external_id": a.get("externalId"), "expires_at": a.get("expiresAt"), "frontify_status": a.get("status"),
                    "dimensions": {k: a[k] for k in ("width", "height", "pageCount", "duration", "bitrate") if a.get(k) is not None},
                    "export": {"status": r.get("status", "not attempted"), "local_path": r.get("path"), "sha256": r.get("sha256"),
                               "duplicate_of": r.get("duplicate_of"), "reason": r.get("reason"), "extracted_text": self.text.get(a["id"])},
                    "file_metadata": fm, "frontify_raw": a})
            write_json(d / "assets.json", recs)
            write_json(d / "folders.json", b["folders"])
            write_json(d / "projects.json", {"libraries_and_workspaces": b["containers"], "collections": [{k: v for k, v in c.items() if k != "asset_ids"} | {"asset_count": len(c["asset_ids"])} for c in b["collections"]],
                                             "guidelines": b["guideline_list"], "guideline_pages": b["nav"]})
            rel: list[dict[str, str]] = []
            rel += [{"src_type": "folder", "src_id": f["id"], "rel": "child_of", "dst_type": "folder" if f["parent_id"] else "container", "dst_id": f["parent_id"] or f["container_id"]} for f in b["folders"]]
            rel += [{"src_type": "asset", "src_id": a["id"], "rel": "in_folder" if a.get("folder_id") else "in_container", "dst_type": "folder" if a.get("folder_id") else "container", "dst_id": a.get("folder_id") or a["container_id"]} for a in b["assets"]]
            rel += [{"src_type": "collection", "src_id": c["id"], "rel": "contains", "dst_type": "asset", "dst_id": i} for c in b["collections"] for i in c["asset_ids"]]
            rel += [{"src_type": "asset", "src_id": s, "rel": "related_to", "dst_type": "asset", "dst_id": t} for s, ts in b["related"].items() for t in ts]
            rel += [{"src_type": "guideline_page", "src_id": p, "rel": "shows", "dst_type": "asset", "dst_id": i} for p, ids in b["library_page_assets"].items() for i in ids]
            rel += [{"src_type": "guideline_page", "src_id": n["id"], "rel": "child_of", "dst_type": "guideline_page", "dst_id": n["parent_id"]} for n in b["nav"] if n["parent_id"]]
            write_json(d / "relationships.json", rel)
            if b.get("essentials"):
                write_json(d / "essentials.json", b["essentials"])
                write_json(self.l.dir("design") / self.l.brand(b["id"]) / "brand_essentials.json", b["essentials"])

    # --------------------------------------------------------------------- AI
    def write_ai(self, report_summary: dict[str, Any]) -> None:
        ai = self.l.dir("ai")
        write_text(ai / "BRAND_OVERVIEW.md", self._overview())
        write_text(ai / "VISUAL_IDENTITY.md", self._visual())
        write_text(ai / "BRAND_GUIDELINES.md", self._guidelines())
        write_text(ai / "ASSET_INDEX.md", self._asset_index())
        write_text(ai / "DESIGN_SYSTEM.md", self._design())
        write_text(ai / "CONTENT_INDEX.md", self._content_index())
        write_text(self.l.root / "README_AI.md", self._readme(report_summary))

    def _overview(self) -> str:
        out = [self._header("Brand overview")]
        for b in self.inv["brands"]:
            cats: dict[str, int] = {}
            for a in b["assets"]:
                cats[a["category"]] = cats.get(a["category"], 0) + 1
            out.append(f"## {b['name']}\n\n- Frontify brand id: `{b['id']}`" + (f"\n- Slug: `{b['slug']}`" if b.get("slug") else ""))
            out.append(f"- Assets: {len(b['assets'])} ({human_size(sum(int(a.get('size') or 0) for a in b['assets']))}); by type: " + (", ".join(f"{k} {v}" for k, v in sorted(cats.items())) or "none"))
            out.append("\n### Libraries and workspaces\n")
            out += [f"- {c['kind']} **{c['name']}**" + (f" — {c['expected_assets']} assets" if c.get("expected_assets") is not None else "") + ("" if c.get("complete") else " _(crawl incomplete, see EXPORT_REPORT.json)_") for c in b["containers"]] or ["- none accessible"]
            if b["collections"]:
                out.append("\n### Collections\n")
                out += [f"- **{c['name']}** — {len(c['asset_ids'])} assets" for c in b["collections"]]
            out.append("\n### Brand guidelines\n")
            for g in b["guideline_list"]:
                n = sum(1 for p in b["nav"] if p["guideline_id"] == g["id"] and p["kind"] in ("DocumentPage", "CoverPage", "DocumentLibrary"))
                out.append(f"- **{g.get('name')}** — {g.get('url') or 'no url'} ({n} pages)")
            if not b["guideline_list"]:
                out.append(NA)
            tops = [p for p in b["nav"] if p["kind"] != "Guideline" and p["path"].count("/") == 1]
            if tops:
                out.append("\n### Top-level structure of the guidelines\n")
                out += [f"- {p['title']} ({p['kind']})" for p in tops]
            out.append("")
        return "\n".join(out)

    def _visual(self) -> str:
        out = [self._header("Visual identity")]
        for b in self.inv["brands"]:
            ess = b.get("essentials")
            out.append(f"## {b['name']}\n\n### Colors\n")
            out.append(render_colors(ess) or NA)
            out.append("\n### Typography\n")
            out.append(render_fonts(ess) or NA)
            fonts = [a for a in b["assets"] if a["category"] == "fonts"]
            if fonts:
                out.append("\nFont files exported:\n" + "\n".join(f"- {a['title']} → `{self._asset_status(a['id'])}`" for a in fonts))
            out.append("\n### Logos\n")
            logos = [a for a in b["assets"] if a["category"] == "logos"]
            out += [f"- **{a['title']}** ({a.get('extension')}) — {a.get('description') or 'no description'} → `{self._asset_status(a['id'])}`" for a in logos] or [NA]
            out.append("\n### Guideline pages about visual identity\n")
            pages = [p for p in self.pages if p["brand_id"] == b["id"] and _match(p, "visual") and self._page_text(p)]
            for p in pages:
                out.append(f"#### {p['title']}\n\n*Source: {p.get('url') or p['id']} — `{p['file']}`*\n\n{self._page_text(p)}\n")
            if not pages:
                out.append(NA + " (no guideline page matched logo/identity/imagery/icon/layout keywords)")
        return "\n".join(out) + "\n"

    def _guidelines(self) -> str:
        out = [self._header("Brand guidelines (all exported pages)")]
        for b in self.inv["brands"]:
            out.append(f"## {b['name']}\n")
            pages = [p for p in self.pages if p["brand_id"] == b["id"] and self._page_text(p) is not None]
            order = {n["id"]: i for i, n in enumerate(b["nav"])}
            for p in sorted(pages, key=lambda p: order.get(p["id"], 0)):
                lvl = min(3 + max(p["path"].count("/") - 1, 0), 6)
                out.append(f"{'#' * lvl} {p['title']}\n\n*Source: {p.get('url') or p['id']} — file `{p['file']}`*\n\n{self._page_text(p)}\n")
            if not pages:
                out.append(NA + "\n")
        return "\n".join(out)

    def _asset_index(self) -> str:
        out = [self._header("Asset index")]
        for b in self.inv["brands"]:
            out.append(f"## {b['name']}\n")
            for cat in VISUAL_CATS + ["documents", "fonts", "other"]:
                items = sorted((a for a in b["assets"] if a["category"] == cat), key=lambda a: (a["folder_path"], a.get("title") or ""))
                if not items:
                    continue
                out.append(f"### {cat} ({len(items)})\n")
                for a in items:
                    tags = ", ".join(t["value"] for t in a.get("tags") or [] if t)
                    dims = f" · {a['width']}×{a['height']}px" if a.get("width") and a.get("height") else ""
                    out.append(f"- **{a.get('title')}** (`{a.get('extension') or ''}`{dims}, {human_size(a.get('size'))})  \n  Original: `{self._asset_status(a['id'])}`  \n"
                               f"  Frontify location: {a['folder_path']} · id `{a['id']}`"
                               + (f"  \n  Description: {a['description']}" if a.get("description") else "") + (f"  \n  Tags: {tags}" if tags else ""))
                out.append("")
            if not b["assets"]:
                out.append(NA + "\n")
        return "\n".join(out)

    def _design(self) -> str:
        caps = self.inv.get("api_capabilities") or {}
        out = [self._header("Design system")]
        out.append("**API capability check.** Frontify's official GraphQL API exposes Brand Essentials (colors, font families) but "
                   + ("also these token/component related queries: " + ", ".join(caps["design_tokens_or_components_queries"]) if caps.get("design_tokens_or_components_queries") else
                      "no design-token or component queries (none were found" + (" in schema introspection" if caps.get("introspection") else " in the official reference") + "). "
                      "Tokens and components can therefore only be reported through the guideline pages below.") + "\n")
        for b in self.inv["brands"]:
            out.append(f"## {b['name']}\n\n### Colors (Brand Essentials)\n\n{render_colors(b.get('essentials')) or NA}\n\n### Font families (Brand Essentials)\n\n{render_fonts(b.get('essentials')) or NA}\n")
            pages = [p for p in self.pages if p["brand_id"] == b["id"] and _match(p, "design") and self._page_text(p)]
            out.append("### Design documentation found in guidelines\n")
            for p in pages:
                out.append(f"#### {p['title']}\n\n*Source: {p.get('url') or p['id']} — `{p['file']}`*\n\n{self._page_text(p)}\n")
            if not pages:
                out.append(NA)
        return "\n".join(out) + "\n"

    def _content_index(self) -> str:
        out = [self._header("Content index")]
        out.append("## Guideline pages\n")
        for p in sorted(self.pages, key=lambda p: (p["brand_id"], p["path"])):
            out.append(f"- [{p['status']}] **{p['title']}** · {p['path']} · `{p.get('file') or '—'}`" + (f" · {p['url']}" if p.get("url") else "") + (f" — {p['reason']}" if p.get("reason") else ""))
        if not self.pages:
            out.append(NA)
        out.append("\n## Document files\n")
        n = 0
        for b in self.inv["brands"]:
            for a in b["assets"]:
                if a["category"] == "documents":
                    n += 1
                    t = self.text.get(a["id"])
                    out.append(f"- **{a['title']}** → `{self._asset_status(a['id'])}`" + (f" · extracted text: `{t}`" if t else " · no text extracted"))
        if not n:
            out.append(NA)
        out.append("\n## Metadata files\n")
        for b in self.inv["brands"]:
            m = self.l.rel(self.l.dir("meta") / self.l.brand(b["id"]))
            out.append(f"- {b['name']}: `{m}/assets.json`, `folders.json`, `projects.json`, `relationships.json`" + (", `essentials.json`" if b.get("essentials") else ""))
        return "\n".join(out) + "\n"

    def _readme(self, s: dict[str, Any]) -> str:
        brands = ", ".join(f"{b['name']}" for b in self.inv["brands"]) or "none"
        return f"""# {self.client_name} — Frontify export (AI guide)

Exported from `{self.domain}` on {self.now}. Brands: {brands}.

**Rules for any AI reading this folder**
1. Files in `02_ASSETS`, `03_DOCUMENTATION` and `04_DESIGN_SYSTEM/FONTS` are the **untouched originals** downloaded from Frontify. Everything else is derived text.
2. Facts must come from these files. Where a document says "Not available", Frontify returned nothing: do not guess.
3. Every asset's original Frontify location (library / folder path / id) is in `05_METADATA/<brand>/assets.json` and in `ASSET_INDEX.md`.

## Where to look
| Need | Read |
|---|---|
| Who/what is this brand | `06_AI_KNOWLEDGE/BRAND_OVERVIEW.md` |
| Logos, colors, typography | `06_AI_KNOWLEDGE/VISUAL_IDENTITY.md` |
| Rules, usage, tone, messaging | `06_AI_KNOWLEDGE/BRAND_GUIDELINES.md` (per page: `01_BRAND_GUIDELINES/`) |
| Find a specific file | `06_AI_KNOWLEDGE/ASSET_INDEX.md` |
| Components / tokens / styles | `06_AI_KNOWLEDGE/DESIGN_SYSTEM.md` |
| Everything exported | `06_AI_KNOWLEDGE/CONTENT_INDEX.md` |
| What failed / was inaccessible | `EXPORT_REPORT.json` |
| File checksums | `manifest.json` |

## Folder map
- `01_BRAND_GUIDELINES/<brand>/…` guideline pages as Markdown (Frontify navigation order, front-matter with source URL and id); `_original/` raw API JSON; `_media/` previews of images embedded in pages.
- `02_ASSETS/<TYPE>/<brand>/<library>/<folders…>/` LOGOS, IMAGES, PHOTOGRAPHY, VIDEOS, ICONS, ILLUSTRATIONS, AUDIO, OTHER.
- `03_DOCUMENTATION/<brand>/…` document files (PDF, DOCX…) and `_extracted_text/`.
- `04_DESIGN_SYSTEM/` font files and Brand Essentials JSON.
- `05_METADATA/` assets, folders, projects, relationships (JSON).
- `06_AI_KNOWLEDGE/` the generated overview documents above.

## This export
Assets found {s['assets_found']} · downloaded {s['assets_downloaded']} · unchanged/skipped {s['assets_unchanged']} · failed {s['assets_failed']} · not available {s['assets_unavailable']} · guideline pages exported {s['guideline_pages_exported']}/{s['guideline_pages_found']}.
"""
