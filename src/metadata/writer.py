"""Write per-brand metadata JSON (assets/folders/projects/relationships) and global inventory."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.database.db import Database
from src.exporter.layout import Layout
from src.utils.files import utcnow_iso, write_json


def _load(raw: str | None) -> Any:
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return None


def asset_record(r: dict[str, Any], layout: Layout, file_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = _load(r["raw"]) or {}
    local = Path(r["local_path"]) if r["local_path"] else None
    return {
        "frontify_id": r["id"], "title": r["title"], "filename": r["filename"], "extension": r["extension"],
        "mime_type": r["mime"], "size_bytes": r["size"], "category": r["category"], "frontify_type": r["typename"],
        "created_at": r["created_at"], "modified_at": r["modified_at"], "folder_path": r["folder_path"],
        "folder_id": r["folder_id"], "container_id": r["container_id"],
        "description": raw.get("description"), "alternative_text": raw.get("alternativeText"), "author": raw.get("author"),
        "creator": raw.get("creator"), "modifier": raw.get("modifier"), "tags": raw.get("tags"),
        "custom_metadata": raw.get("customMetadata"), "external_id": raw.get("externalId"),
        "expires_at": raw.get("expiresAt"), "status_frontify": raw.get("status"),
        "dimensions": {k: raw.get(k) for k in ("width", "height", "pageCount", "duration", "bitrate") if raw.get(k) is not None},
        "source_urls": {k: raw.get(k) for k in ("previewUrl", "thumbnailUrl") if raw.get(k)},
        "export": {
            "status": r["status"], "download_status": r["download_status"], "local_path": layout.rel(local) if local else None,
            "sha256": r["sha256"], "downloaded_at": r["downloaded_at"], "duplicate_of": r["duplicate_of"], "error": r["error"],
        },
        "file_metadata": file_meta or None,
        "raw_frontify": {k: v for k, v in raw.items() if k != "downloadUrl"},  # signed URL = temporary credential
    }


def write_brand_metadata(db: Database, layout: Layout, brand_id: str, file_meta: dict[str, dict[str, Any]] | None = None) -> dict[str, int]:
    out = layout.brand_dir(brand_id) / "metadata"
    assets = db.query("SELECT * FROM assets WHERE brand_id=? ORDER BY folder_path, title", (brand_id,))
    write_json(out / "assets.json", [asset_record(a, layout, (file_meta or {}).get(a["id"])) for a in assets])
    folders = db.query("SELECT id,container_id,parent_id,name,path,created_at,modified_at,status FROM folders WHERE brand_id=? ORDER BY path", (brand_id,))
    write_json(out / "folders.json", folders)
    containers = db.query("SELECT id,kind,name,expected_assets,scan_complete,status FROM containers WHERE brand_id=? ORDER BY kind,name", (brand_id,))
    guidelines = db.query("SELECT id,guideline_id,parent_id,title,url,kind,path,position,hidden,modified_at,export_status,status "
                          "FROM guideline_pages WHERE brand_id=? ORDER BY guideline_id,path", (brand_id,))
    collections = db.query("SELECT id,library_id,name FROM collections WHERE brand_id=?", (brand_id,))
    write_json(out / "projects.json", {"libraries_and_workspaces": containers, "collections": collections, "guidelines": guidelines})
    rels = db.query("SELECT src_type,src_id,rel,dst_type,dst_id FROM relationships WHERE brand_id=? ORDER BY src_type,src_id,rel", (brand_id,))
    structural = [{"src_type": "folder", "src_id": f["id"], "rel": "child_of", "dst_type": "folder" if f["parent_id"] else "container",
                   "dst_id": f["parent_id"] or f["container_id"]} for f in folders]
    structural += [{"src_type": "asset", "src_id": a["id"], "rel": "in_folder" if a["folder_id"] else "in_container",
                    "dst_type": "folder" if a["folder_id"] else "container", "dst_id": a["folder_id"] or a["container_id"]} for a in assets]
    structural += [{"src_type": "guideline_page", "src_id": g["id"], "rel": "child_of", "dst_type": "guideline_page", "dst_id": g["parent_id"]}
                   for g in guidelines if g["parent_id"]]
    write_json(out / "relationships.json", structural + rels)
    ess = db.one("SELECT raw FROM essentials WHERE brand_id=?", (brand_id,))
    if ess:
        write_json(out / "essentials.json", _load(ess["raw"]))
    return {"assets": len(assets), "folders": len(folders), "relationships": len(structural) + len(rels), "guideline_pages": len(guidelines)}


def build_inventory(db: Database, layout: Layout) -> dict[str, Any]:
    brands = db.query("SELECT id,name,slug,status FROM brands ORDER BY name")
    inv = []
    for b in brands:
        st = db.one("""SELECT count(*) n, coalesce(sum(size),0) bytes,
                   sum(download_status='done') done, sum(download_status='failed') failed,
                   sum(download_status='pending') pending, sum(download_status='unavailable') unavailable
                   FROM assets WHERE brand_id=? AND status='active'""", (b["id"],)) or {}
        cats = {r["category"]: r["n"] for r in db.query("SELECT category, count(*) n FROM assets WHERE brand_id=? AND status='active' GROUP BY category", (b["id"],))}
        inv.append({**b, "dir": layout.rel(layout.brand_dir(b["id"])), "assets": st, "assets_by_category": cats,
                    "folders": db.scalar("SELECT count(*) FROM folders WHERE brand_id=? AND status='active'", (b["id"],)),
                    "guideline_pages": db.scalar("SELECT count(*) FROM guideline_pages WHERE brand_id=? AND status='active'", (b["id"],))})
    return {"generated_at": utcnow_iso(), "brands": inv}
