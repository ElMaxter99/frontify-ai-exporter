"""Embedding providers. ``none`` keeps search lexical (SQLite FTS5)."""
from __future__ import annotations

import logging
from typing import Protocol

import httpx

log = logging.getLogger("embeddings")


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAIEmbedder:
    """OpenAI-compatible ``/v1/embeddings`` endpoint (plain httpx, no SDK needed)."""

    def __init__(self, api_key: str, model: str = "", base_url: str = "https://api.openai.com/v1") -> None:
        if not api_key:
            raise ValueError("OPENAI_API_KEY is not set")
        self.model = model or "text-embedding-3-small"
        self.name = f"openai:{self.model}"
        self._client = httpx.Client(base_url=base_url, headers={"Authorization": f"Bearer {api_key}"}, timeout=120)

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), 64):
            batch = [t[:24000] for t in texts[i:i + 64]]
            for attempt in range(4):
                r = self._client.post("/embeddings", json={"model": self.model, "input": batch})
                if r.status_code in (429, 500, 502, 503):
                    import time

                    time.sleep(2 ** attempt)
                    continue
                r.raise_for_status()
                break
            else:
                r.raise_for_status()
            data = sorted(r.json()["data"], key=lambda d: d["index"])
            out += [d["embedding"] for d in data]
        return out


class LocalEmbedder:
    """sentence-transformers model running locally (pip install sentence-transformers)."""

    def __init__(self, model: str = "") -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError("Local embeddings need `pip install sentence-transformers`") from exc
        self.model_name = model or "sentence-transformers/all-MiniLM-L6-v2"
        self.name = f"local:{self.model_name}"
        self._m = SentenceTransformer(self.model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self._m.encode(texts, batch_size=32, normalize_embeddings=True, show_progress_bar=False)]


def make_embedder(provider: str, model: str = "", openai_key: str = "") -> Embedder | None:
    provider = (provider or "none").lower()
    if provider in ("", "none"):
        return None
    if provider == "openai":
        return OpenAIEmbedder(openai_key, model)
    if provider == "local":
        return LocalEmbedder(model)
    raise ValueError(f"Unknown embeddings provider: {provider}")
