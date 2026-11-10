"""Sync history and change reporting."""
from __future__ import annotations

import json
from typing import Any

from src.database.db import Database


def list_runs(db: Database, limit: int = 30) -> list[dict[str, Any]]:
    out = []
    for r in db.query("SELECT * FROM sync_runs ORDER BY id DESC LIMIT ?", (limit,)):
        summary = json.loads(r["summary"]) if r["summary"] else {}
        counts = {}
        for c in db.query("SELECT entity, change, count(*) n FROM changes WHERE run_id=? GROUP BY entity, change", (r["id"],)):
            counts.setdefault(c["entity"], {})[c["change"]] = c["n"]
        out.append({"id": r["id"], "kind": r["kind"], "started_at": r["started_at"], "finished_at": r["finished_at"],
                    "status": r["status"], "changes": counts, "duration_seconds": summary.get("duration_seconds"),
                    "downloads": summary.get("downloads"), "totals": summary.get("totals")})
    return out


def run_changes(db: Database, run_id: int, limit: int = 500) -> list[dict[str, Any]]:
    return db.query("SELECT entity, entity_id, change, name, brand_id FROM changes WHERE run_id=? ORDER BY id LIMIT ?", (run_id, limit))


def last_sync(db: Database) -> dict[str, Any] | None:
    return db.one("SELECT id, kind, started_at, finished_at, status FROM sync_runs WHERE status IN ('completed') ORDER BY id DESC LIMIT 1")
