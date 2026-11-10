"""Deterministic export folder layout."""
from __future__ import annotations

from pathlib import Path

from src.database.db import Database
from src.utils.files import safe_name, slugify

ASSET_CATEGORIES = ["images", "logos", "icons", "videos", "audio", "documents", "fonts", "other"]


class Layout:
    def __init__(self, db: Database, root: Path) -> None:
        self.db, self.root = db, root
        self._slugs: dict[str, str] = {}

    def brand_slug(self, brand_id: str) -> str:
        if not self._slugs:
            used: set[str] = set()
            for b in self.db.query("SELECT id, name, slug FROM brands ORDER BY first_seen, id"):
                base = slugify(b["slug"] or b["name"] or "", default="brand")
                s = base if base not in used else f"{base}-{b['id']}"
                used.add(s)
                self._slugs[b["id"]] = s
        return self._slugs.get(brand_id) or slugify(brand_id)

    def brand_dir(self, brand_id: str) -> Path:
        return self.root / "brands" / self.brand_slug(brand_id)

    def rel(self, path: Path) -> str:
        try:
            return path.relative_to(self.root).as_posix()
        except ValueError:
            return str(path)

    def asset_path(self, asset: dict, taken: set[str]) -> Path:
        parts = [safe_name(p, "folder") for p in (asset.get("folder_path") or "").split("/") if p]
        name = safe_name(asset.get("filename") or "", "")
        if not name:
            ext = (asset.get("extension") or "").lstrip(".")
            name = safe_name((asset.get("title") or asset["id"]) + (f".{ext}" if ext and not (asset.get("title") or "").lower().endswith("." + ext.lower()) else ""))
        base = self.brand_dir(asset["brand_id"]) / "assets" / (asset.get("category") or "other")
        path = base.joinpath(*parts, name)
        if str(path) in taken:
            stem, dot, ext = name.rpartition(".")
            alt = f"{stem}__{asset['id']}.{ext}" if dot else f"{name}__{asset['id']}"
            path = base.joinpath(*parts, safe_name(alt))
        return path
