# SPDX-License-Identifier: Apache-2.0
"""Client folder layout (01_ … 06_) and persisted resume state (a single JSON file)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from src.utils.files import safe_name, write_json

DIRS = {"guidelines": "01_BRAND_GUIDELINES", "assets": "02_ASSETS", "docs": "03_DOCUMENTATION",
        "design": "04_DESIGN_SYSTEM", "meta": "05_METADATA", "ai": "06_AI_KNOWLEDGE"}
CAT_DIR = {"logos": "LOGOS", "images": "IMAGES", "photography": "PHOTOGRAPHY", "videos": "VIDEOS", "icons": "ICONS",
           "illustrations": "ILLUSTRATIONS", "audio": "AUDIO", "other": "OTHER"}


class Layout:
    def __init__(self, client_dir: Path, brands: list[dict[str, Any]]) -> None:
        self.root = client_dir
        self._slugs: dict[str, str] = {}
        used: set[str] = set()
        for b in brands:
            s = safe_name(b.get("name") or b["id"], "brand")
            if s.lower() in used:
                s = f"{s}-{b['id']}"
            used.add(s.lower())
            self._slugs[b["id"]] = s

    def brand(self, brand_id: str) -> str:
        return self._slugs.get(brand_id, safe_name(brand_id))

    def dir(self, key: str) -> Path:
        return self.root / DIRS[key]

    def rel(self, p: Path) -> str:
        try:
            return p.relative_to(self.root).as_posix()
        except ValueError:
            return str(p)

    def asset_path(self, a: dict[str, Any], brand_id: str, taken: set[str]) -> Path:
        parts = [safe_name(x, "folder") for x in (a.get("folder_path") or "").split("/") if x]
        cat = a.get("category") or "other"
        if cat == "documents":
            base = self.dir("docs") / self.brand(brand_id)
        elif cat == "fonts":
            base = self.dir("design") / "FONTS" / self.brand(brand_id)
        else:
            base = self.dir("assets") / CAT_DIR.get(cat, "OTHER") / self.brand(brand_id)
        name = safe_name(a.get("filename") or "", "")
        if not name:
            ext = (a.get("extension") or "").lstrip(".")
            title = a.get("title") or a["id"]
            name = safe_name(title if not ext or title.lower().endswith("." + ext.lower()) else f"{title}.{ext}")
        path = base.joinpath(*parts, name)
        if str(path) in taken:
            stem, dot, ext = name.rpartition(".")
            path = base.joinpath(*parts, safe_name(f"{stem}__{a['id']}.{ext}" if dot else f"{name}__{a['id']}"))
        return path


class State:
    """Resume/change-detection memory stored in ``<client>/.export_state.json`` (no database)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.data: dict[str, Any] = {"assets": {}, "pages": {}}
        if path.exists():
            try:
                self.data = json.loads(path.read_text("utf-8"))
                self.data.setdefault("assets", {})
                self.data.setdefault("pages", {})
            except ValueError:
                pass

    @property
    def assets(self) -> dict[str, Any]:
        return self.data["assets"]

    @property
    def pages(self) -> dict[str, Any]:
        return self.data["pages"]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        write_json(self.path, self.data)


def replace_atomic(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    os.replace(src, dst)
