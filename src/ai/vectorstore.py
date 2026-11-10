"""Vector store adapters: built-in SQLite (numpy cosine), ChromaDB, FAISS, Qdrant.
Chunks + FTS5 lexical index always live in SQLite; vector stores are additional/optional."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from src.database.db import Database

log = logging.getLogger("vectorstore")


class VectorStore(Protocol):
    name: str

    def upsert(self, ids: list[str], vectors: list[list[float]], texts: list[str], metas: list[dict[str, Any]]) -> None: ...
    def search(self, vector: list[float], k: int, brand_id: str | None) -> list[tuple[str, float]]: ...
    def reset(self, brand_id: str | None) -> None: ...


def _unit(m: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(m, axis=-1, keepdims=True)
    n[n == 0] = 1
    return m / n


class SqliteVectorStore:
    name = "sqlite"

    def __init__(self, db: Database) -> None:
        self.db = db

    def upsert(self, ids, vectors, texts, metas) -> None:  # noqa: ANN001
        rows = [(i, np.asarray(v, dtype=np.float32).tobytes(), len(v)) for i, v in zip(ids, vectors)]
        self.db.executemany("UPDATE chunks SET vector=?, dim=? WHERE id=?", [(b, d, i) for i, b, d in rows])

    def search(self, vector, k, brand_id):  # noqa: ANN001
        sql = "SELECT id, vector FROM chunks WHERE vector IS NOT NULL" + (" AND brand_id=?" if brand_id else "")
        rows = self.db.query(sql, (brand_id,) if brand_id else ())
        if not rows:
            return []
        q = _unit(np.asarray(vector, dtype=np.float32)[None, :])[0]
        dim = len(q)
        rows = [r for r in rows if len(r["vector"]) == dim * 4]
        if not rows:
            return []
        mat = _unit(np.vstack([np.frombuffer(r["vector"], dtype=np.float32) for r in rows]))
        scores = mat @ q
        top = np.argsort(-scores)[:k]
        return [(rows[i]["id"], float(scores[i])) for i in top]

    def reset(self, brand_id) -> None:  # noqa: ANN001
        self.db.execute("UPDATE chunks SET vector=NULL, dim=NULL" + (" WHERE brand_id=?" if brand_id else ""), (brand_id,) if brand_id else ())


class ChromaVectorStore:
    name = "chroma"

    def __init__(self, path: Path) -> None:
        import chromadb

        self.col = chromadb.PersistentClient(path=str(path / "chroma")).get_or_create_collection("frontify", metadata={"hnsw:space": "cosine"})

    def upsert(self, ids, vectors, texts, metas) -> None:  # noqa: ANN001
        flat = [{k: (v if isinstance(v, (str, int, float, bool)) else json.dumps(v)) for k, v in m.items() if v is not None} for m in metas]
        for i in range(0, len(ids), 500):
            self.col.upsert(ids=ids[i:i + 500], embeddings=vectors[i:i + 500], documents=texts[i:i + 500], metadatas=flat[i:i + 500])

    def search(self, vector, k, brand_id):  # noqa: ANN001
        r = self.col.query(query_embeddings=[vector], n_results=k, where={"brand_id": brand_id} if brand_id else None)
        return [(i, 1 - d) for i, d in zip(r["ids"][0], r["distances"][0])]

    def reset(self, brand_id) -> None:  # noqa: ANN001
        self.col.delete(where={"brand_id": brand_id}) if brand_id else self.col.delete(where={})


class FaissVectorStore:
    """Flat inner-product index persisted next to the DB; rebuilt from SQLite vectors."""

    name = "faiss"

    def __init__(self, path: Path, db: Database) -> None:
        import faiss  # noqa: F401

        self.path, self.db = path / "faiss.index", db
        self.ids: list[str] = []
        self.index = None

    def _rebuild(self, dim: int) -> None:
        import faiss

        rows = self.db.query("SELECT id, vector FROM chunks WHERE vector IS NOT NULL AND dim=?", (dim,))
        self.index = faiss.IndexFlatIP(dim)
        self.ids = [r["id"] for r in rows]
        if rows:
            self.index.add(_unit(np.vstack([np.frombuffer(r["vector"], dtype=np.float32) for r in rows])))
        faiss.write_index(self.index, str(self.path))

    def upsert(self, ids, vectors, texts, metas) -> None:  # noqa: ANN001
        SqliteVectorStore(self.db).upsert(ids, vectors, texts, metas)  # vectors stay the source of truth
        self._rebuild(len(vectors[0]))

    def search(self, vector, k, brand_id):  # noqa: ANN001
        if self.index is None:
            self._rebuild(len(vector))
        q = _unit(np.asarray(vector, dtype=np.float32)[None, :])
        scores, idx = self.index.search(q, k * 4 if brand_id else k)
        hits = [(self.ids[i], float(s)) for s, i in zip(scores[0], idx[0]) if i >= 0]
        if brand_id:
            ok = {r["id"] for r in self.db.query("SELECT id FROM chunks WHERE brand_id=?", (brand_id,))}
            hits = [h for h in hits if h[0] in ok][:k]
        return hits

    def reset(self, brand_id) -> None:  # noqa: ANN001
        SqliteVectorStore(self.db).reset(brand_id)
        self.index = None


class QdrantVectorStore:
    name = "qdrant"

    def __init__(self, url: str) -> None:
        from qdrant_client import QdrantClient

        self.c = QdrantClient(url=url)
        self.coll = "frontify"

    @staticmethod
    def _pid(i: str) -> str:
        import uuid

        return str(uuid.uuid5(uuid.NAMESPACE_URL, i))

    def upsert(self, ids, vectors, texts, metas) -> None:  # noqa: ANN001
        from qdrant_client.models import Distance, PointStruct, VectorParams

        if not self.c.collection_exists(self.coll):
            self.c.create_collection(self.coll, vectors_config=VectorParams(size=len(vectors[0]), distance=Distance.COSINE))
        pts = [PointStruct(id=self._pid(i), vector=v, payload={**m, "chunk_id": i, "text": t}) for i, v, t, m in zip(ids, vectors, texts, metas)]
        for j in range(0, len(pts), 256):
            self.c.upsert(self.coll, points=pts[j:j + 256])

    def search(self, vector, k, brand_id):  # noqa: ANN001
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        flt = Filter(must=[FieldCondition(key="brand_id", match=MatchValue(value=brand_id))]) if brand_id else None
        res = self.c.query_points(self.coll, query=vector, limit=k, query_filter=flt).points
        return [(p.payload["chunk_id"], p.score) for p in res]

    def reset(self, brand_id) -> None:  # noqa: ANN001
        if self.c.collection_exists(self.coll) and not brand_id:
            self.c.delete_collection(self.coll)


def make_store(kind: str, db: Database, data_dir: Path, qdrant_url: str = "") -> VectorStore:
    kind = (kind or "sqlite").lower()
    if kind == "sqlite":
        return SqliteVectorStore(db)
    if kind == "chroma":
        return ChromaVectorStore(data_dir)
    if kind == "faiss":
        return FaissVectorStore(data_dir, db)
    if kind == "qdrant":
        return QdrantVectorStore(qdrant_url)
    raise ValueError(f"Unknown vector store: {kind}")


def fts_query(text: str) -> str:
    words = re.findall(r"\w+", text, flags=re.UNICODE)
    return " OR ".join(f'"{w}"' for w in words[:24])
