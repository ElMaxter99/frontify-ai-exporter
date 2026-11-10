# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import httpx
import pytest

from src.frontify.client import FrontifyAuthError, FrontifyClient, FrontifyError, FrontifyGraphQLError
from src.utils.logging import redact


def make(handler, **kw):
    return FrontifyClient("acme.frontify.com", "secret-token-xyz", transport=httpx.MockTransport(handler), max_retries=3, **kw)


async def test_retries_on_5xx_and_429_then_succeeds():
    calls = {"n": 0}

    def h(req):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503)
        if calls["n"] == 2:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"data": {"ok": True}})

    async with make(h) as c:
        assert await c.execute("query Q { ok }") == {"ok": True}
    assert calls["n"] == 3


async def test_auth_error_is_not_retried():
    calls = {"n": 0}

    def h(req):
        calls["n"] += 1
        return httpx.Response(401)

    async with make(h) as c:
        with pytest.raises(FrontifyAuthError):
            await c.execute("query Q { ok }")
    assert calls["n"] == 1


async def test_gives_up_after_max_retries():
    async with make(lambda r: httpx.Response(500)) as c:
        with pytest.raises(FrontifyError, match="Giving up"):
            await c.execute("query Q { ok }")


async def test_partial_errors_return_data_and_are_recorded():
    def h(req):
        return httpx.Response(200, json={"data": {"a": 1}, "errors": [{"message": "forbidden field", "path": ["b"]}]})

    async with make(h) as c:
        assert await c.execute("query Q { a b }") == {"a": 1}
        assert c.partial_errors and c.partial_errors[0]["message"] == "forbidden field"


async def test_validation_error_detected():
    def h(req):
        return httpx.Response(200, json={"errors": [{"message": 'Cannot query field "x" on type "Y"', "extensions": {"code": "GRAPHQL_VALIDATION_FAILED"}}]})

    async with make(h) as c:
        with pytest.raises(FrontifyGraphQLError) as ei:
            await c.execute("query Q { x }")
    assert ei.value.is_validation


async def test_headers_and_operation_name_and_pagination():
    seen = []

    def h(req):
        import json

        body = json.loads(req.content)
        seen.append((req.headers["authorization"], req.headers["x-frontify-beta"], body["operationName"]))
        p = body["variables"]["page"]
        return httpx.Response(200, json={"data": {"x": {"hasNextPage": p < 3, "items": [{"id": p}, None]}}})

    async with make(h) as c:
        items = await c.collect("query MyOp($page: Int!, $limit: Int!) { x }", ["x"])
    assert [i["id"] for i in items] == [1, 2, 3]
    assert seen[0] == ("Bearer secret-token-xyz", "enabled", "MyOp")


def test_secrets_are_redacted_from_logs():
    FrontifyClient("d.frontify.com", "supersecrettoken123", transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    assert "supersecrettoken123" not in redact("Authorization: Bearer supersecrettoken123 and x supersecrettoken123")
    assert "abc123" not in redact("https://cdn/x?X-Amz-Signature=abc123&a=1")
