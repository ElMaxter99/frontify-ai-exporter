"""Text and metadata extraction from downloaded originals. Originals are only READ, never modified."""
from __future__ import annotations

import csv
import html
import json
import logging
import re
from pathlib import Path
from typing import Any

log = logging.getLogger("extract")

TEXT_EXT = {"txt", "md", "markdown", "csv", "json", "xml", "svg", "html", "htm", "rtf", "yml", "yaml"}
MAX_CHARS = 2_000_000


def extract_text(path: Path, extension: str | None, ocr: bool = False) -> tuple[str, str] | None:
    """Returns (text, method) or None when nothing could be extracted."""
    ext = (extension or path.suffix).lower().lstrip(".")
    try:
        if ext == "pdf":
            return _pdf(path)
        if ext == "docx":
            return _docx(path)
        if ext in ("html", "htm"):
            return _strip_tags(path.read_text("utf-8", errors="replace")), "html"
        if ext == "svg":
            return _svg_text(path.read_text("utf-8", errors="replace")), "svg-text"
        if ext == "csv":
            with open(path, newline="", encoding="utf-8", errors="replace") as f:
                return "\n".join(", ".join(r) for r in csv.reader(f))[:MAX_CHARS], "csv"
        if ext == "json":
            return json.dumps(json.loads(path.read_text("utf-8", errors="replace")), indent=1, ensure_ascii=False)[:MAX_CHARS], "json"
        if ext in TEXT_EXT:
            return path.read_text("utf-8", errors="replace")[:MAX_CHARS], "text"
        if ocr and ext in ("png", "jpg", "jpeg", "tif", "tiff", "bmp", "webp", "gif"):
            return _ocr(path)
    except Exception as exc:
        log.warning("text extraction failed for %s: %s", path.name, exc)
    return None


def _pdf(path: Path) -> tuple[str, str] | None:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = []
    for i, page in enumerate(reader.pages, 1):
        t = (page.extract_text() or "").strip()
        if t:
            pages.append(f"[page {i}]\n{t}")
    text = "\n\n".join(pages)[:MAX_CHARS]
    return (text, "pdf-text") if text.strip() else None


def _docx(path: Path) -> tuple[str, str] | None:
    import docx

    d = docx.Document(str(path))
    lines = [p.text for p in d.paragraphs if p.text.strip()]
    for t in d.tables:
        for row in t.rows:
            lines.append(" | ".join(c.text.strip() for c in row.cells))
    text = "\n".join(lines)[:MAX_CHARS]
    return (text, "docx") if text.strip() else None


def _ocr(path: Path) -> tuple[str, str] | None:
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        log.warning("OCR requested but pytesseract is not installed")
        return None
    text = pytesseract.image_to_string(Image.open(path)).strip()
    return (text, "ocr") if text else None


def _strip_tags(s: str) -> str:
    s = re.sub(r"(?is)<(script|style).*?</\1>", " ", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    return re.sub(r"[ \t]+", " ", html.unescape(s)).strip()[:MAX_CHARS]


def _svg_text(s: str) -> str:
    texts = re.findall(r"(?is)<(?:text|title|desc|tspan)[^>]*>(.*?)</(?:text|title|desc|tspan)>", s)
    return " ".join(_strip_tags(t) for t in texts).strip()


def image_metadata(path: Path) -> dict[str, Any] | None:
    """Pixel size, mode, DPI and EXIF (readable tags only)."""
    try:
        from PIL import ExifTags, Image
    except ImportError:
        return None
    try:
        with Image.open(path) as im:
            meta: dict[str, Any] = {"format": im.format, "width": im.width, "height": im.height, "mode": im.mode}
            if im.info.get("dpi"):
                meta["dpi"] = [float(x) for x in im.info["dpi"]]
            exif = getattr(im, "getexif", lambda: None)()
            if exif:
                tags = {ExifTags.TAGS.get(k, str(k)): v for k, v in exif.items()}
                meta["exif"] = {k: (v if isinstance(v, (int, float, str)) else str(v)) for k, v in tags.items()
                                if k not in ("MakerNote", "UserComment") and len(str(v)) < 300}
            return meta
    except Exception:
        return None
