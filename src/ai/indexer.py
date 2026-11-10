"""Build chunks (with full provenance), the FTS5 lexical index and (optionally) embeddings."""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from src.ai.chunking import Chunk, chunk_markdown, chunk_plain
from src.ai.embeddings import Embedder
from src.ai.extract import extract_text, image_metadata
from src.ai.vectorstore import VectorStore, fts_query, SqliteVectorStore
from src.database.db import Database
from src.exporter.layout import Layout
from src.utils.events import EventBus
from src.utils.files import safe_name, utcnow_iso, write_text

log = logging.getLogger("indexer")


def _cid(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:24]


def _thash(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:16]


class Indexer:
    def __init__(self, db: Database, layout: Layout, bus: EventBus, *, domain: str = "", embedder: Embedder | None = None,
                 store: VectorStore | None = None, ocr: bool = False, cache_dir: Path | None = None) -> None:
        self.db, self.layout, self.bus = db, layout, bus
        self.domain, self.embedder, self.ocr = domain, embedder, ocr
        self.store = store or SqliteVectorStore(db)
        self.cache = cache_dir
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------- sources
    def _base(self, brand: dict[str, Any], **kw: Any) -> dict[str, Any]:
        return {"brand": brand["name"], "brand_id": brand["id"], "frontify_domain": self.domain or None,
                "extracted_at": utcnow_iso(), **kw}

    def _guideline_chunks(self, brand: dict[str, Any]) -> list[Chunk]:
        out: list[Chunk] = []
        for p in self.db.query("SELECT * FROM guideline_pages WHERE brand_id=? AND status='active' AND markdown_path IS NOT NULL", (brand["id"],)):
            f = Path(p["markdown_path"])
            if not f.exists():
                continue
            meta = self._base(brand, kind="guideline_page", source_file=self.layout.rel(f), frontify_id=p["id"], source_url=p["url"],
                              category="guideline", folder=p["path"], title=p["title"])
            for c in chunk_markdown(f.read_text("utf-8"), meta):
                c.metadata["id"] = _cid(brand["id"], "g", p["id"], str(c.metadata["chunk_index"]))
                out.append(c)
        kdir = self.layout.brand_dir(brand["id"]) / "knowledge"
        for name, cat in (("brand_context.md", "brand_context"), ("colors.md", "colors"), ("typography.md", "typography")):
            f = kdir / name
            if f.exists():
                meta = self._base(brand, kind="knowledge", source_file=self.layout.rel(f), frontify_id=brand["id"], source_url=None,
                                  category=cat, folder="knowledge", title=name)
                for c in chunk_markdown(f.read_text("utf-8"), meta):
                    c.metadata["id"] = _cid(brand["id"], "k", name, str(c.metadata["chunk_index"]))
                    out.append(c)
        return out

    def _asset_chunks(self, brand: dict[str, Any], file_meta: dict[str, dict[str, Any]]) -> list[Chunk]:
        out: list[Chunk] = []
        kdir = self.layout.brand_dir(brand["id"]) / "knowledge" / "extracted_text"
        for a in self.db.query("SELECT * FROM assets WHERE brand_id=? AND status='active'", (brand["id"],)):
            raw = json.loads(a["raw"] or "{}")
            local = Path(a["local_path"]) if a["local_path"] else None
            src = self.layout.rel(local) if local else None
            base = self._base(brand, source_file=src, frontify_id=a["id"], source_url=None, category=a["category"],
                              folder=a["folder_path"], title=a["title"], extension=a["extension"], sha256=a["sha256"])
            lines = [f"Asset: {a['title']}", f"Type: {a['category']} ({a['extension'] or 'n/a'}, {a['mime'] or 'unknown mime'})",
                     f"Folder: {a['folder_path']}"]
            for label, val in (("Description", raw.get("description")), ("Alternative text", raw.get("alternativeText")),
                               ("Author", raw.get("author")), ("Created", a["created_at"]), ("Modified", a["modified_at"])):
                if val:
                    lines.append(f"{label}: {val}")
            tags = [t["value"] for t in raw.get("tags") or [] if t]
            if tags:
                lines.append("Tags: " + ", ".join(tags))
            for cm in raw.get("customMetadata") or []:
                val = cm.get("value") if "value" in cm else cm.get("values")
                if val not in (None, "", []):
                    lines.append(f"{(cm.get('property') or {}).get('name')}: {json.dumps(val, ensure_ascii=False) if not isinstance(val, str) else val}")
            dims = {k: raw[k] for k in ("width", "height", "pageCount", "duration") if raw.get(k) is not None}
            if dims:
                lines.append("Dimensions: " + ", ".join(f"{k}={v}" for k, v in dims.items()))
            fm = file_meta.get(a["id"])
            if fm and fm.get("exif"):
                lines.append("EXIF: " + ", ".join(f"{k}={v}" for k, v in list(fm["exif"].items())[:20]))
            card = "\n".join(lines)
            out.append(Chunk(card, {**base, "kind": "asset_metadata", "chunk_index": 0, "chunk_count": 1, "id": _cid(brand["id"], "a", a["id"])}))
            if local and local.exists() and a["download_status"] == "done":
                if a["category"] in ("images", "logos", "icons") and a["id"] not in file_meta:
                    im = image_metadata(local)
                    if im:
                        file_meta[a["id"]] = im
                ex = self._extract(local, a)
                if ex:
                    text, method = ex
                    ep = kdir / f"{safe_name(a['title'] or a['id'])[:80]}-{a['id']}.md"
                    write_text(ep, f"---\nsource_file: {json.dumps(src)}\nfrontify_id: {json.dumps(a['id'])}\nextraction: {method}\n"
                                   f"extracted_at: {utcnow_iso()}\n---\n\n# {a['title']}\n\n{text}\n")
                    for c in chunk_plain(text, {**base, "kind": "asset_text", "extraction": method, "text_file": self.layout.rel(ep)}):
                        c.metadata["id"] = _cid(brand["id"], "t", a["id"], str(c.metadata["chunk_index"]))
                        out.append(c)
        return out

    def _extract(self, local: Path, a: dict[str, Any]) -> tuple[str, str] | None:
        key = f"{a['sha256']}-{int(self.ocr)}"
        cf = self.cache / f"{key}.json" if self.cache and a["sha256"] else None
        if cf and cf.exists():
            d = json.loads(cf.read_text("utf-8"))
            return (d["text"], d["method"]) if d else None
        res = extract_text(local, a["extension"], ocr=self.ocr)
        if cf:
            cf.write_text(json.dumps({"text": res[0], "method": res[1]} if res else None), "utf-8")
        return res

    # ------------------------------------------------------------------ run
    def run(self, brand_ids: set[str] | None = None) -> dict[str, Any]:
        total = 0
        embedded = 0
        all_meta: dict[str, dict[str, Any]] = {}
        for brand in self.db.query("SELECT id,name FROM brands WHERE status='active'"):
            if brand_ids and brand["id"] not in brand_ids:
                continue
            file_meta: dict[str, dict[str, Any]] = {}
            chunks = self._guideline_chunks(brand) + self._asset_chunks(brand, file_meta)
            all_meta.update(file_meta)
            old = {r["id"]: r for r in self.db.query("SELECT id, metadata, vector, dim FROM chunks WHERE brand_id=?", (brand["id"],))}
            self.db.execute("DELETE FROM chunks_fts WHERE id IN (SELECT id FROM chunks WHERE brand_id=?)", (brand["id"],))
            self.db.execute("DELETE FROM chunks WHERE brand_id=?", (brand["id"],))
            rows, fts, to_embed = [], [], []
            for c in chunks:
                cid = c.metadata["id"]
                c.metadata["text_hash"] = _thash(c.text)
                vec, dim = None, None
                o = old.get(cid)
                if o and o["vector"] and json.loads(o["metadata"]).get("text_hash") == c.metadata["text_hash"] \
                        and json.loads(o["metadata"]).get("embedder") == getattr(self.embedder, "name", None):
                    vec, dim = o["vector"], o["dim"]
                elif self.embedder:
                    to_embed.append(c)
                if self.embedder:
                    c.metadata["embedder"] = self.embedder.name
                rows.append((cid, brand["id"], c.text, json.dumps(c.metadata, ensure_ascii=False, default=str), vec, dim))
                fts.append((cid, c.text))
            self.db.executemany("INSERT INTO chunks(id,brand_id,text,metadata,vector,dim) VALUES (?,?,?,?,?,?)", rows)
            self.db.executemany("INSERT INTO chunks_fts(id,text) VALUES (?,?)", fts)
            if self.embedder and to_embed:
                log.info("Embedding %d chunk(s) for %s with %s", len(to_embed), brand["name"], self.embedder.name)
                vecs = self.embedder.embed([c.text for c in to_embed])
                ids = [c.metadata["id"] for c in to_embed]
                SqliteVectorStore(self.db).upsert(ids, vecs, [], [])  # source of truth for vectors
                if self.store.name != "sqlite":
                    self.store.upsert(ids, vecs, [c.text for c in to_embed], [c.metadata for c in to_embed])
                embedded += len(to_embed)
            self._write_jsonl(brand, chunks)
            total += len(chunks)
            self.bus.publish("progress", {"phase": "index", "brand": brand["name"], "chunks": len(chunks)})
        return {"chunks": total, "embedded": embedded, "file_metadata": all_meta}

    def _write_jsonl(self, brand: dict[str, Any], chunks: list[Chunk]) -> None:
        path = self.layout.brand_dir(brand["id"]) / "knowledge" / "chunks.jsonl"
        write_text(path, "".join(json.dumps({"id": c.metadata["id"], "text": c.text, "metadata": c.metadata}, ensure_ascii=False, default=str) + "\n" for c in chunks))


class Searcher:
    """Semantic search when an embedder is configured, otherwise BM25 over FTS5. Hybrid when both exist."""

    def __init__(self, db: Database, embedder: Embedder | None = None, store: VectorStore | None = None) -> None:
        self.db, self.embedder = db, embedder
        self.store = store or SqliteVectorStore(db)

    def search(self, query: str, k: int = 8, brand_id: str | None = None) -> list[dict[str, Any]]:
        scores: dict[str, float] = {}
        mode = "lexical"
        q = fts_query(query)
        if q:
            sql = "SELECT f.id, bm25(chunks_fts) AS s FROM chunks_fts f JOIN chunks c ON c.id=f.id WHERE chunks_fts MATCH ?"
            params: list[Any] = [q]
            if brand_id:
                sql += " AND c.brand_id=?"
                params.append(brand_id)
            for rank, r in enumerate(self.db.query(sql + " ORDER BY s LIMIT ?", params + [k * 3])):
                scores[r["id"]] = scores.get(r["id"], 0) + 1.0 / (60 + rank)
        if self.embedder:
            try:
                vec = self.embedder.embed([query])[0]
                for rank, (cid, _s) in enumerate(self.store.search(vec, k * 3, brand_id)):
                    scores[cid] = scores.get(cid, 0) + 1.0 / (60 + rank)
                mode = "hybrid"
            except Exception as exc:
                log.warning("semantic search failed, using lexical only: %s", exc)
        out = []
        for cid, s in sorted(scores.items(), key=lambda x: -x[1])[:k]:
            row = self.db.one("SELECT id, text, metadata FROM chunks WHERE id=?", (cid,))
            if row:
                out.append({"id": cid, "score": round(s, 5), "mode": mode, "text": row["text"], "metadata": json.loads(row["metadata"])})
        return out
