"""Persistence operations with change detection (new / modified / unchanged / deleted)."""
from __future__ import annotations

import json
from typing import Any

from src.database.db import Database
from src.utils.files import sha1_text, utcnow_iso


class Repo:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ------------------------------------------------------------------ runs
    def start_run(self, kind: str) -> int:
        self.db.execute("INSERT INTO sync_runs(kind, started_at, status) VALUES (?,?,?)", (kind, utcnow_iso(), "running"))
        return int(self.db.scalar("SELECT max(id) FROM sync_runs"))

    def finish_run(self, run_id: int, status: str, summary: dict[str, Any]) -> None:
        self.db.execute(
            "UPDATE sync_runs SET finished_at=?, status=?, summary=? WHERE id=?",
            (utcnow_iso(), status, json.dumps(summary, default=str), run_id),
        )

    def record_change(self, run_id: int, entity: str, entity_id: str, change: str, name: str, brand_id: str) -> None:
        self.db.execute(
            "INSERT INTO changes(run_id, entity, entity_id, change, name, brand_id) VALUES (?,?,?,?,?,?)",
            (run_id, entity, entity_id, change, name, brand_id),
        )

    # ---------------------------------------------------------------- brands
    def upsert_brand(self, b: dict[str, Any], seen: str) -> str:
        row = self.db.one("SELECT id FROM brands WHERE id=?", (b["id"],))
        self.db.execute(
            """INSERT INTO brands(id,name,slug,avatar,raw,first_seen,last_seen,status) VALUES (?,?,?,?,?,?,?,'active')
               ON CONFLICT(id) DO UPDATE SET name=excluded.name, slug=excluded.slug, avatar=excluded.avatar,
               raw=excluded.raw, last_seen=excluded.last_seen, status='active'""",
            (b["id"], b.get("name"), b.get("slug"), b.get("avatar"), json.dumps(b, default=str), seen, seen),
        )
        return "unchanged" if row else "new"

    def upsert_container(self, brand_id: str, kind: str, c: dict[str, Any], seen: str) -> str:
        row = self.db.one("SELECT id FROM containers WHERE id=?", (c["id"],))
        self.db.execute(
            """INSERT INTO containers(id,brand_id,kind,name,raw,first_seen,last_seen,status) VALUES (?,?,?,?,?,?,?,'active')
               ON CONFLICT(id) DO UPDATE SET name=excluded.name, raw=excluded.raw, last_seen=excluded.last_seen, status='active'""",
            (c["id"], brand_id, kind, c.get("name"), json.dumps(c, default=str), seen, seen),
        )
        return "unchanged" if row else "new"

    def upsert_folder(self, brand_id: str, container_id: str, parent_id: str | None, f: dict[str, Any], path: str, seen: str) -> str:
        row = self.db.one("SELECT modified_at, path FROM folders WHERE id=?", (f["id"],))
        self.db.execute(
            """INSERT INTO folders(id,brand_id,container_id,parent_id,name,path,created_at,modified_at,raw,first_seen,last_seen,status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,'active')
               ON CONFLICT(id) DO UPDATE SET parent_id=excluded.parent_id, name=excluded.name, path=excluded.path,
               created_at=excluded.created_at, modified_at=excluded.modified_at, raw=excluded.raw,
               last_seen=excluded.last_seen, status='active'""",
            (f["id"], brand_id, container_id, parent_id, f.get("name"), path, f.get("createdAt"), f.get("modifiedAt"),
             json.dumps(f, default=str), seen, seen),
        )
        if not row:
            return "new"
        return "modified" if (row["modified_at"], row["path"]) != (f.get("modifiedAt"), path) else "unchanged"

    # ---------------------------------------------------------------- assets
    def upsert_asset(self, brand_id: str, container_id: str, folder_id: str | None, folder_path: str,
                     a: dict[str, Any], category: str, mime: str | None, seen: str) -> str:
        """Returns new | modified | unchanged. ``modified`` resets the download when the *file* changed."""
        size = int(a["size"]) if a.get("size") not in (None, "") else None
        # What identifies the bytes: modification time + size + filename. Metadata-only edits do not re-download.
        file_fp = sha1_text(a.get("modifiedAt"), a.get("fileCreatedAt"), size, a.get("filename"), a.get("extension"))
        meta = {k: v for k, v in a.items() if k not in ("downloadUrl", "previewUrl", "thumbnailUrl")}
        fp = sha1_text(json.dumps(meta, sort_keys=True, default=str), folder_path)
        raw = json.dumps(a, default=str)
        row = self.db.one("SELECT fingerprint, file_fingerprint, download_status, status FROM assets WHERE id=?", (a["id"],))
        if row is None:
            self.db.execute(
                """INSERT INTO assets(id,brand_id,container_id,folder_id,folder_path,title,filename,extension,mime,size,typename,
                   category,created_at,modified_at,fingerprint,file_fingerprint,raw,status,download_status,first_seen,last_seen)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'active','pending',?,?)""",
                (a["id"], brand_id, container_id, folder_id, folder_path, a.get("title"), a.get("filename"),
                 a.get("extension"), mime, size, a.get("__typename"), category, a.get("createdAt"), a.get("modifiedAt"),
                 fp, file_fp, raw, seen, seen),
            )
            return "new"
        file_changed = row["file_fingerprint"] != file_fp
        reset = ", download_status='pending', error=NULL, attempts=0" if file_changed else ""
        self.db.execute(
            f"""UPDATE assets SET brand_id=?,container_id=?,folder_id=?,folder_path=?,title=?,filename=?,extension=?,mime=?,size=?,
                typename=?,category=?,created_at=?,modified_at=?,fingerprint=?,file_fingerprint=?,raw=?,status='active',
                last_seen=?{reset} WHERE id=?""",
            (brand_id, container_id, folder_id, folder_path, a.get("title"), a.get("filename"), a.get("extension"), mime,
             size, a.get("__typename"), category, a.get("createdAt"), a.get("modifiedAt"), fp, file_fp, raw, seen, a["id"]),
        )
        if row["status"] == "deleted":
            return "restored"
        return "modified" if (row["fingerprint"] != fp) else "unchanged"

    def mark_missing(self, table: str, brand_id: str, container_id: str, seen: str) -> list[dict[str, Any]]:
        """Items of a *fully scanned* container not seen in this run are inaccessible/deleted."""
        assert table in ("assets", "folders")
        label = "title" if table == "assets" else "name"
        gone = self.db.query(
            f"SELECT id, {label} AS name FROM {table} WHERE container_id=? AND status='active' AND last_seen<?",
            (container_id, seen),
        )
        if gone:
            self.db.execute(
                f"UPDATE {table} SET status='deleted' WHERE container_id=? AND status='active' AND last_seen<?",
                (container_id, seen),
            )
        return gone

    def set_container_scan(self, container_id: str, expected: int | None, complete: bool) -> None:
        self.db.execute("UPDATE containers SET expected_assets=?, scan_complete=? WHERE id=?",
                        (expected, 1 if complete else 0, container_id))

    # ------------------------------------------------------------ guidelines
    def upsert_guideline_page(self, p: dict[str, Any], seen: str) -> str:
        row = self.db.one("SELECT modified_at, title, path FROM guideline_pages WHERE id=?", (p["id"],))
        self.db.execute(
            """INSERT INTO guideline_pages(id,brand_id,guideline_id,parent_id,title,url,kind,path,position,hidden,raw,
               first_seen,last_seen,status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'active')
               ON CONFLICT(id) DO UPDATE SET parent_id=excluded.parent_id,title=excluded.title,url=excluded.url,kind=excluded.kind,
               path=excluded.path,position=excluded.position,hidden=excluded.hidden,raw=excluded.raw,last_seen=excluded.last_seen,
               status='active'""",
            (p["id"], p["brand_id"], p["guideline_id"], p.get("parent_id"), p.get("title"), p.get("url"), p["kind"],
             p["path"], p.get("position", 0), 1 if p.get("hidden") else 0, json.dumps(p.get("raw", {}), default=str), seen, seen),
        )
        if not row:
            return "new"
        return "modified" if (row["title"], row["path"]) != (p.get("title"), p["path"]) else "unchanged"

    def set_page_content(self, page_id: str, modified_at: str | None, content_hash: str, md_path: str | None, status: str, error: str | None = None) -> str:
        row = self.db.one("SELECT content_hash FROM guideline_pages WHERE id=?", (page_id,))
        self.db.execute(
            "UPDATE guideline_pages SET modified_at=?, content_hash=?, markdown_path=?, export_status=?, error=? WHERE id=?",
            (modified_at, content_hash, md_path, status, error, page_id),
        )
        prev = row["content_hash"] if row else None
        if prev is None:
            return "new"
        return "unchanged" if prev == content_hash else "modified"

    # --------------------------------------------------------- relationships
    def add_relationships(self, rows: list[tuple[str, str, str, str, str, str]]) -> None:
        self.db.executemany(
            "INSERT OR IGNORE INTO relationships(src_type,src_id,rel,dst_type,dst_id,brand_id) VALUES (?,?,?,?,?,?)", rows)
