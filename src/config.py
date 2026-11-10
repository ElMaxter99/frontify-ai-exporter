"""Application configuration.

Secrets (Frontify token, OpenAI key) come from the environment only. Non-secret
options can additionally be overridden at runtime from the UI; those overrides are
stored in the ``settings`` table and never include credentials.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Keys the UI is allowed to override (non secret).
RUNTIME_KEYS: dict[str, type] = {
    "frontify_domain": str,
    "export_dir": str,
    "download_concurrency": int,
    "api_concurrency": int,
    "page_size": int,
    "embeddings_provider": str,
    "embeddings_model": str,
    "vector_store": str,
    "qdrant_url": str,
    "ocr_enabled": bool,
    "include_related_assets": bool,
    "dedupe_hardlinks": bool,
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    frontify_domain: str = ""
    frontify_token: SecretStr = SecretStr("")
    export_dir: str = "./exports"
    data_dir: str = "./data"
    download_concurrency: int = 4
    api_concurrency: int = 4
    page_size: int = 50
    request_timeout: float = 60.0
    max_retries: int = 5
    embeddings_provider: str = "none"
    embeddings_model: str = ""
    openai_api_key: SecretStr = SecretStr("")
    vector_store: str = "sqlite"
    qdrant_url: str = "http://localhost:6333"
    ocr_enabled: bool = False
    include_related_assets: bool = True
    dedupe_hardlinks: bool = False
    log_level: str = "INFO"
    web_dist: str = "./frontend/dist"

    @property
    def db_path(self) -> Path:
        return Path(self.data_dir) / "exporter.sqlite3"


def normalize_domain(value: str) -> str:
    """``https://Acme.frontify.com/foo`` -> ``acme.frontify.com``."""
    v = value.strip()
    v = re.sub(r"^https?://", "", v, flags=re.IGNORECASE)
    return v.split("/")[0].strip().lower()


class RuntimeConfig:
    """Env settings + DB overrides + in-memory (never persisted) token override."""

    def __init__(self, base: Settings, overrides: dict[str, Any] | None = None) -> None:
        self.base = base
        self.overrides: dict[str, Any] = dict(overrides or {})
        self._token_override: str | None = None

    def get(self, key: str) -> Any:
        if key in self.overrides and self.overrides[key] not in (None, ""):
            return self.overrides[key]
        return getattr(self.base, key)

    def set_overrides(self, values: dict[str, Any]) -> dict[str, Any]:
        clean: dict[str, Any] = {}
        for k, v in values.items():
            typ = RUNTIME_KEYS.get(k)
            if typ is None:
                continue
            if typ is bool:
                v = v if isinstance(v, bool) else str(v).lower() in ("1", "true", "yes", "on")
            elif typ is int:
                v = max(1, int(v))
            else:
                v = str(v).strip()
            if k == "frontify_domain":
                v = normalize_domain(v)
            clean[k] = v
        self.overrides.update(clean)
        return clean

    def set_session_token(self, token: str | None) -> None:
        self._token_override = token or None

    @property
    def token(self) -> str:
        return self._token_override or self.base.frontify_token.get_secret_value()

    @property
    def openai_key(self) -> str:
        return self.base.openai_api_key.get_secret_value()

    @property
    def domain(self) -> str:
        return normalize_domain(str(self.get("frontify_domain")))

    @property
    def export_path(self) -> Path:
        return Path(str(self.get("export_dir"))).resolve()

    def public(self) -> dict[str, Any]:
        """Settings safe to send to the browser (no secrets)."""
        out = {k: self.get(k) for k in RUNTIME_KEYS}
        out["has_token"] = bool(self.token)
        out["token_source"] = "session" if self._token_override else ("env" if self.token else "none")
        out["has_openai_key"] = bool(self.openai_key)
        return out
