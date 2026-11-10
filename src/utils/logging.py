"""Logging with secret redaction and fan-out to the realtime event bus."""
from __future__ import annotations

import logging
import re
import threading

_SECRETS: set[str] = set()
_lock = threading.Lock()
_BEARER = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{8,}")
_SIGNED = re.compile(r"(?i)((?:signature|token|x-amz-signature|sig|key)=)[^&\s\"']+")


def register_secret(value: str | None) -> None:
    if value and len(value) >= 6:
        with _lock:
            _SECRETS.add(value)


def redact(text: str) -> str:
    with _lock:
        secrets = list(_SECRETS)
    for s in secrets:
        text = text.replace(s, "***")
    text = _BEARER.sub(r"\1***", text)
    return _SIGNED.sub(r"\1***", text)


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = redact(record.getMessage())
            record.args = ()
        except Exception:  # pragma: no cover - never break logging
            pass
        return True


class BusHandler(logging.Handler):
    """Mirrors log records into the EventBus so the UI can tail them."""

    def __init__(self, bus) -> None:
        super().__init__(level=logging.INFO)
        self.bus = bus

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.bus.publish("log", {"level": record.levelname, "logger": record.name, "message": record.getMessage()})
        except Exception:  # pragma: no cover
            pass


def setup_logging(level: str = "INFO", bus=None) -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())
    for h in list(root.handlers):
        if getattr(h, "_fae", False):
            root.removeHandler(h)
    stream = logging.StreamHandler()
    stream.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    stream._fae = True  # type: ignore[attr-defined]
    stream.addFilter(RedactingFilter())
    root.addHandler(stream)
    if bus is not None:
        bh = BusHandler(bus)
        bh._fae = True  # type: ignore[attr-defined]
        bh.addFilter(RedactingFilter())
        root.addHandler(bh)
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
