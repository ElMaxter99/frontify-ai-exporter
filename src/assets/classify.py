"""Asset categorisation and MIME detection (heuristic; Frontify exposes no logo/icon flag on Asset)."""
from __future__ import annotations

import mimetypes
import re

IMAGE_EXT = {"png", "jpg", "jpeg", "webp", "gif", "tif", "tiff", "bmp", "heic", "heif", "avif", "psd", "ai", "eps", "raw"}
VIDEO_EXT = {"mp4", "mov", "avi", "mkv", "webm", "m4v", "wmv", "mpg", "mpeg"}
AUDIO_EXT = {"mp3", "wav", "aac", "flac", "ogg", "m4a", "aiff"}
DOC_EXT = {"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "md", "rtf", "csv", "key", "pages", "numbers",
           "odt", "ods", "odp", "indd", "idml", "html", "htm", "json", "xml", "zip"}
FONT_EXT = {"ttf", "otf", "woff", "woff2", "eot"}

_LOGO = re.compile(r"\blogo|logotype|wordmark|brandmark|emblem", re.IGNORECASE)
_ICON = re.compile(r"\bicon|pictogram|glyph", re.IGNORECASE)
_PHOTO = re.compile(r"photo|fotograf|imagery|picture|portrait", re.I)
_ILLUS = re.compile(r"illustrat|ilustra|artwork", re.I)

CATEGORIES = ["logos", "images", "photography", "videos", "icons", "illustrations", "audio", "documents", "fonts", "other"]


def _hint(text: str) -> str | None:
    if _LOGO.search(text):
        return "logos"
    if _ICON.search(text):
        return "icons"
    if _ILLUS.search(text):
        return "illustrations"
    if _PHOTO.search(text):
        return "photography"
    return None


def category_for(extension: str | None, path: str | None = None, title: str | None = None, filename: str | None = None) -> str:
    """Frontify has no logo/icon flag on assets, so images are classified heuristically:
    the asset's own name wins, then its library/folder path. Everything else images -> ``images``."""
    ext = (extension or "").lower().lstrip(".")
    if ext in VIDEO_EXT:
        return "videos"
    if ext in AUDIO_EXT:
        return "audio"
    if ext in FONT_EXT:
        return "fonts"
    if ext in IMAGE_EXT or ext == "svg":
        return _hint(f"{title or ''} {filename or ''}") or _hint(path or "") or "images"
    if ext in DOC_EXT:
        return "documents"
    return "other"


def mime_for(filename: str | None, extension: str | None) -> str | None:
    name = filename or (f"x.{extension}" if extension else "")
    mt, _ = mimetypes.guess_type(name)
    if mt:
        return mt
    ext = (extension or "").lower()
    return {"webp": "image/webp", "heic": "image/heic", "avif": "image/avif", "woff2": "font/woff2"}.get(ext)
