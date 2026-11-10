"""Convert a fetched guideline page (sections/elements) into Markdown. Pure functions, no I/O."""
from __future__ import annotations

import json
from typing import Any

MAX_SETTINGS_JSON = 20000


def _front_matter(fields: dict[str, Any]) -> str:
    lines = ["---"]
    for k, v in fields.items():
        if v is None or v == "":
            continue
        lines.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
    lines.append("---")
    return "\n".join(lines)


def render_block(block: dict[str, Any], media: dict[str, list[str]] | None = None) -> str:
    """One GuidelinePageBlock (any block type implementing GuidelinePageBlockInterface)."""
    btype = ((block.get("type") or {}).get("name")) or block.get("__typename", "block")
    out = [f"<!-- block id={block.get('id')} type={btype} -->"]
    content = (block.get("content") or "").strip()
    if content:
        out.append(content)
    else:
        settings = block.get("settings")
        if settings:
            dumped = json.dumps(settings, ensure_ascii=False, indent=2)
            if len(dumped) > MAX_SETTINGS_JSON:
                dumped = dumped[:MAX_SETTINGS_JSON] + "\n… (truncated; full settings in guidelines/original/*.json)"
            out.append(f"*{btype} block (no text content exposed by the API). Raw settings:*\n\n```json\n{dumped}\n```")
    for rel in (media or {}).get(block.get("id", ""), []):
        out.append(f"![{btype} asset preview]({rel})")
    return "\n\n".join(out)


def render_page(meta: dict[str, Any], sections: list[list[dict[str, Any]]], *, brand: str, brand_id: str,
                path: str, extracted_at: str, media: dict[str, list[str]] | None = None) -> str:
    parts = [
        _front_matter({
            "title": meta.get("title"), "brand": brand, "brand_id": brand_id, "frontify_id": meta.get("id"),
            "source_url": meta.get("url"), "guideline_path": path, "modified_at": meta.get("modifiedAt"),
            "extracted_at": extracted_at, "source": "frontify-guideline",
        }),
        f"# {meta.get('title') or 'Untitled'}",
    ]
    for elements in sections:
        for el in elements:
            if not el:
                continue
            t = el.get("__typename")
            if t == "GuidelinePageHeading":
                parts.append(f"## {el.get('title') or ''}".rstrip())
            elif t == "GuidelinePageBlockReference":
                inner = el.get("block") or {}
                parts.append(f"<!-- reference id={el.get('id')} -->\n" + render_block(inner, media))
            else:
                parts.append(render_block(el, media))
    return "\n\n".join(parts).rstrip() + "\n"


def render_library_page(meta: dict[str, Any], assets: list[dict[str, Any]], *, brand: str, brand_id: str,
                        path: str, extracted_at: str) -> str:
    parts = [
        _front_matter({"title": meta.get("title"), "brand": brand, "brand_id": brand_id, "frontify_id": meta.get("id"),
                       "source_url": meta.get("url"), "guideline_path": path, "extracted_at": extracted_at,
                       "source": "frontify-guideline-library-page"}),
        f"# {meta.get('title') or 'Library'}",
        f"This guideline page presents {len(assets)} asset(s) from a Frontify library.",
        "",
    ]
    for a in assets:
        rel = f" — `{a['rel_path']}`" if a.get("rel_path") else ""
        desc = f": {a['description']}" if a.get("description") else ""
        parts.append(f"- **{a.get('title')}** (Frontify asset `{a['id']}`){rel}{desc}")
    return "\n".join(parts).rstrip() + "\n"


def strip_front_matter(md: str) -> str:
    if md.startswith("---\n"):
        end = md.find("\n---", 4)
        if end != -1:
            return md[end + 4:].lstrip("\n")
    return md
