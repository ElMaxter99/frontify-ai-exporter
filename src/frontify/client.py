# SPDX-License-Identifier: Apache-2.0
"""Single entry point for every request made to Frontify.

* GraphQL endpoint: ``https://<domain>/graphql`` (official Frontify GraphQL API)
* Auth: ``Authorization: Bearer <token>`` (personal access token or OAuth2 access token)
* ``X-Frontify-Beta: enabled`` is sent because guideline/essentials fields are flagged Beta
* Retries with exponential backoff + jitter on 429/5xx/network errors (honours ``Retry-After``)
* Partial GraphQL errors (e.g. one field forbidden) are recorded and the data returned
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx

from src.utils.logging import register_secret

log = logging.getLogger("frontify.client")

USER_AGENT = "frontify-ai-exporter/0.1"
_OP_NAME = re.compile(r"\s*query\s+(\w+)")


class FrontifyError(Exception):
    """Base error."""


class FrontifyAuthError(FrontifyError):
    """401/403 or UNAUTHENTICATED: bad/expired token or missing permissions."""


class FrontifyGraphQLError(FrontifyError):
    def __init__(self, errors: list[dict[str, Any]], operation: str | None = None) -> None:
        self.errors = errors
        self.operation = operation
        msgs = "; ".join(str(e.get("message")) for e in errors[:3])
        super().__init__(f"GraphQL error in {operation or 'query'}: {msgs}")

    @property
    def is_validation(self) -> bool:
        """True when the *query itself* is invalid for the schema (unknown field, etc.)."""
        for e in self.errors:
            code = (e.get("extensions") or {}).get("code", "")
            msg = str(e.get("message", ""))
            if code in ("GRAPHQL_VALIDATION_FAILED", "BAD_USER_INPUT") or "Cannot query field" in msg \
                    or "Unknown type" in msg or "Unknown argument" in msg or "cannot be spread" in msg:
                return True
        return False


class FrontifyClient:
    def __init__(
        self,
        domain: str,
        token: str,
        *,
        timeout: float = 60.0,
        max_retries: int = 5,
        concurrency: int = 4,
        transport: httpx.AsyncBaseTransport | None = None,
        base_url: str | None = None,
    ) -> None:
        if not domain:
            raise FrontifyError("Frontify domain is not configured")
        if not token:
            raise FrontifyAuthError("Frontify token is not configured")
        register_secret(token)
        self.domain = domain
        self.endpoint = f"{base_url.rstrip('/')}/graphql" if base_url else f"https://{domain}/graphql"
        self.max_retries = max_retries
        self._sem = asyncio.Semaphore(max(1, concurrency))
        self.request_count = 0
        self.partial_errors: list[dict[str, Any]] = []
        self._http = httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(timeout, connect=15.0),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
                "X-Frontify-Beta": "enabled",
            },
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> FrontifyClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    # ------------------------------------------------------------------ core
    async def execute(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        *,
        operation: str | None = None,
        tolerate_partial: bool = True,
    ) -> dict[str, Any]:
        """Run a query and return ``data``. Raises on transport/auth/validation errors."""
        payload: dict[str, Any] = {"query": query, "variables": variables or {}}
        m = _OP_NAME.match(query)
        if m:  # operationName must match the document's own operation name
            operation = m.group(1)
            payload["operationName"] = operation
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                async with self._sem:
                    self.request_count += 1
                    resp = await self._http.post(self.endpoint, json=payload)
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_exc = exc
                await self._backoff(attempt, None, f"network error {type(exc).__name__}")
                continue

            if resp.status_code in (401, 403):
                raise FrontifyAuthError(f"Frontify rejected the credentials (HTTP {resp.status_code})")
            if resp.status_code == 429 or resp.status_code >= 500:
                last_exc = FrontifyError(f"HTTP {resp.status_code}")
                await self._backoff(attempt, resp.headers.get("Retry-After"), f"HTTP {resp.status_code}")
                continue
            if resp.status_code >= 400 and not resp.content:
                raise FrontifyError(f"HTTP {resp.status_code} from Frontify")
            try:
                body = resp.json()
            except ValueError as exc:
                raise FrontifyError(f"Non-JSON response (HTTP {resp.status_code})") from exc

            errors = body.get("errors") or []
            data = body.get("data")
            if any((e.get("extensions") or {}).get("code") == "UNAUTHENTICATED" for e in errors):
                raise FrontifyAuthError("Frontify reports UNAUTHENTICATED")
            if any(_is_rate_limited(e) for e in errors):
                last_exc = FrontifyGraphQLError(errors, operation)
                await self._backoff(attempt, None, "GraphQL rate limit")
                continue
            if errors and (data is None or not tolerate_partial):
                raise FrontifyGraphQLError(errors, operation)
            if errors:
                for e in errors:
                    self.partial_errors.append({"operation": operation, **e})
                    log.warning("partial GraphQL error in %s: %s (path=%s)", operation, e.get("message"), e.get("path"))
            return data or {}
        raise FrontifyError(f"Giving up after {self.max_retries + 1} attempts: {last_exc}")

    async def _backoff(self, attempt: int, retry_after: str | None, why: str) -> None:
        if attempt >= self.max_retries:
            return
        delay = min(60.0, (2 ** attempt) * 0.5) * (0.75 + random.random() / 2)
        if retry_after:
            try:
                delay = max(delay, min(120.0, float(retry_after)))
            except ValueError:
                pass
        log.warning("%s; retrying in %.1fs (attempt %d/%d)", why, delay, attempt + 1, self.max_retries)
        await asyncio.sleep(delay)

    # ------------------------------------------------------------ pagination
    async def paginate(
        self,
        query: str,
        path: list[str],
        variables: dict[str, Any] | None = None,
        *,
        page_size: int = 50,
        operation: str | None = None,
        on_page: Callable[[dict[str, Any]], None] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield every item of a paginated connection.

        ``query`` must declare ``$page: Int!`` and ``$limit: Int!``; ``path`` locates the
        connection (``total/page/limit/hasNextPage/items``) inside ``data``.
        """
        page = 1
        while True:
            data = await self.execute(query, {**(variables or {}), "page": page, "limit": page_size}, operation=operation)
            conn: Any = data
            for key in path:
                conn = conn.get(key) if isinstance(conn, dict) else None
            if not isinstance(conn, dict):
                return
            if on_page:
                on_page(conn)
            for item in conn.get("items") or []:
                if item is not None:
                    yield item
            if not conn.get("hasNextPage"):
                return
            page += 1

    async def collect(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return [i async for i in self.paginate(*args, **kwargs)]


def _is_rate_limited(err: dict[str, Any]) -> bool:
    code = str((err.get("extensions") or {}).get("code", "")).upper()
    return code in ("RATE_LIMITED", "TOO_MANY_REQUESTS") or "rate limit" in str(err.get("message", "")).lower()
