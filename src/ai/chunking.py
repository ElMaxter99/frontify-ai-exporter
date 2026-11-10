"""Markdown-aware chunking that preserves heading context and provenance."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


@dataclass
class Chunk:
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


def _split_long(text: str, size: int, overlap: int) -> list[str]:
    if len(text) <= size:
        return [text]
    out, i = [], 0
    while i < len(text):
        end = min(len(text), i + size)
        if end < len(text):  # prefer to cut at paragraph / sentence / space
            for sep in ("\n\n", "\n", ". ", " "):
                cut = text.rfind(sep, i + size // 2, end)
                if cut != -1:
                    end = cut + len(sep)
                    break
        out.append(text[i:end].strip())
        if end >= len(text):
            break
        i = max(end - overlap, i + 1)
    return [o for o in out if o]


def strip_front_matter(md: str) -> str:
    if md.startswith("---\n"):
        end = md.find("\n---", 4)
        if end != -1:
            return md[end + 4:].lstrip("\n")
    return md


def chunk_markdown(md: str, base_meta: dict[str, Any], size: int = 1800, overlap: int = 200) -> list[Chunk]:
    """Split by heading sections first, then by size. Each chunk keeps its heading breadcrumb."""
    md = strip_front_matter(md)
    sections: list[tuple[list[str], list[str]]] = []
    stack: list[tuple[int, str]] = []
    buf: list[str] = []
    for line in md.splitlines():
        m = HEADING.match(line)
        if m:
            if buf:
                sections.append(([h for _, h in stack], buf))
                buf = []
            level = len(m.group(1))
            stack = [s for s in stack if s[0] < level] + [(level, m.group(2).strip())]
        else:
            buf.append(line)
    if buf:
        sections.append(([h for _, h in stack], buf))
    chunks: list[Chunk] = []
    for headings, lines in sections:
        body = "\n".join(lines).strip()
        if not body:
            continue
        crumb = " > ".join(headings)
        for part in _split_long(body, size, overlap):
            text = f"{crumb}\n\n{part}" if crumb else part
            chunks.append(Chunk(text, {**base_meta, "heading_path": crumb}))
    for i, c in enumerate(chunks):
        c.metadata["chunk_index"] = i
        c.metadata["chunk_count"] = len(chunks)
    return chunks


def chunk_plain(text: str, base_meta: dict[str, Any], size: int = 1800, overlap: int = 200) -> list[Chunk]:
    parts = _split_long(text.strip(), size, overlap) if text.strip() else []
    return [Chunk(p, {**base_meta, "chunk_index": i, "chunk_count": len(parts)}) for i, p in enumerate(parts)]
