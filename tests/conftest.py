# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import pytest

from src.exporter.run import Exporter
from tests.fake_frontify import TOKEN, FakeFrontify


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    import asyncio

    real = asyncio.sleep

    async def fast(delay, *a, **k):
        await real(0)
    monkeypatch.setattr("src.frontify.client.asyncio.sleep", fast)
    monkeypatch.setattr("src.exporter.download.asyncio.sleep", fast)


@pytest.fixture
def fake() -> FakeFrontify:
    return FakeFrontify()


@pytest.fixture
def make_exporter(tmp_path, fake):
    def make(**kw):
        return Exporter("https://Acme.frontify.com/", TOKEN, tmp_path / "EXPORTS", client_name=kw.pop("name", "CLIENTE_01"),
                        concurrency=3, page_size=2, api_transport=fake.transport, download_transport=fake.transport, **kw)
    return make
