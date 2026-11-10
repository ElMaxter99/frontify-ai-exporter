from __future__ import annotations

import pytest

from src.config import RuntimeConfig, Settings
from src.database.db import Database
from src.exporter.pipeline import Pipeline
from src.utils.events import EventBus
from tests.fake_frontify import TOKEN, FakeFrontify


@pytest.fixture
def fake() -> FakeFrontify:
    return FakeFrontify()


@pytest.fixture
def env(tmp_path, fake):
    base = Settings(_env_file=None, frontify_domain="acme.frontify.com", frontify_token=TOKEN, export_dir=str(tmp_path / "exports"),
                    data_dir=str(tmp_path / "data"), page_size=2, max_retries=2, download_concurrency=3, api_concurrency=3)
    db = Database(base.db_path)
    cfg = RuntimeConfig(base, {})
    bus = EventBus()
    pipe = Pipeline(cfg, db, bus, api_transport=fake.transport, download_transport=fake.transport)
    return cfg, db, bus, pipe


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    import asyncio

    real = asyncio.sleep

    async def fast(delay, *a, **k):  # keep tests quick
        await real(0)
    monkeypatch.setattr("src.frontify.client.asyncio.sleep", fast)
    monkeypatch.setattr("src.assets.downloader.asyncio.sleep", fast)
