"""Filesystem helpers: slugs, safe names, hashing, atomic JSON writes."""
from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from datetime import UTC
from pathlib import Path
from typing import Any

_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def slugify(value: str, default: str = "item") -> str:
    v = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    v = re.sub(r"[^a-zA-Z0-9]+", "-", v).strip("-").lower()
    return v or default


def safe_name(value: str, default: str = "unnamed", max_len: int = 150) -> str:
    """Filesystem safe version of a name that keeps readability and unicode."""
    v = _ILLEGAL.sub("_", value or "").strip().strip(".")
    v = re.sub(r"\s+", " ", v)
    if not v or v in (".", ".."):
        v = default
    if len(v) > max_len:
        stem, dot, ext = v.rpartition(".")
        v = (stem[: max_len - len(ext) - 1] + "." + ext) if dot and len(ext) <= 10 else v[:max_len]
    return v


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def sha1_text(*parts: Any) -> str:
    return hashlib.sha1("\x1f".join("" if p is None else str(p) for p in parts).encode()).hexdigest()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    os.replace(tmp, path)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def human_size(n: float | None) -> str:
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def utcnow_iso() -> str:
    from datetime import datetime

    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def utcnow_precise() -> str:
    """Microsecond ISO timestamp: used as a scan token (strictly increasing between runs)."""
    from datetime import datetime

    return datetime.now(UTC).isoformat(timespec="microseconds")
