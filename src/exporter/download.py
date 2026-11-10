# SPDX-License-Identifier: Apache-2.0
"""Concurrent, resumable, integrity-checked download of ORIGINAL files.

* Fresh signed ``downloadUrl`` per batch (they expire). Previews/thumbnails are never used as substitutes.
* A file is only re-downloaded when its Frontify fingerprint changed; if it changed, the old file is kept in
  ``_previous_versions/`` instead of being silently overwritten.
* One failing file never stops the export. Partial ``.part`` files are resumed with HTTP Range.
* The CDN client does NOT receive the Frontify token.
"""
from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any

import httpx

from src.exporter.layout import Layout, State, replace_atomic
from src.exporter.progress import Progress
from src.frontify import queries as Q
from src.frontify.client import FrontifyClient, FrontifyError
from src.utils.files import sha256_file

log = logging.getLogger("download")


class _Transient(Exception):
    pass


class _Expired(Exception):
    pass


class Downloader:
    def __init__(self, client: FrontifyClient, layout: Layout, state: State, progress: Progress, *, concurrency: int = 4,
                 retries: int = 3, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.client, self.layout, self.state, self.progress = client, layout, state, progress
        self.concurrency, self.retries = max(1, concurrency), retries
        self._http = httpx.AsyncClient(transport=transport, follow_redirects=True, timeout=httpx.Timeout(120.0, connect=20.0),
                                       headers={"User-Agent": "frontify-exporter/1.0"})
        self.results: dict[str, dict[str, Any]] = {}
        self._taken: set[str] = {str(layout.root / e["path"]) for e in state.assets.values() if e.get("path")}
        self._sha: dict[str, str] = {e["sha256"]: i for i, e in state.assets.items() if e.get("sha256")}
        self.cancelled = False

    async def aclose(self) -> None:
        await self._http.aclose()

    async def run(self, assets: list[tuple[str, dict[str, Any]]]) -> dict[str, dict[str, Any]]:
        """``assets``: (brand_id, asset record). Returns per-asset result keyed by asset id."""
        todo: list[tuple[str, dict[str, Any]]] = []
        for brand_id, a in assets:
            e = self.state.assets.get(a["id"])
            p = self.layout.root / e["path"] if e and e.get("path") else None
            if e and e.get("fp") == a["fingerprint"] and p and p.exists() and (e.get("size") in (None, p.stat().st_size)):
                self.results[a["id"]] = {"status": "unchanged", "path": e["path"], "sha256": e.get("sha256"), "duplicate_of": e.get("duplicate_of"),
                                         "reason": "already exported and unchanged in Frontify (verified on disk)"}
                self.progress.skipped += 1
            else:
                todo.append((brand_id, a))
        self.progress.to_download = len(todo)
        self.progress.processed = 0
        log.info("%d file(s) to download, %d unchanged and skipped", len(todo), self.progress.skipped)
        sem = asyncio.Semaphore(self.concurrency)

        async def one(brand_id: str, a: dict[str, Any], url: str | None) -> None:
            async with sem:
                if self.cancelled:
                    return
                try:
                    await self._one(brand_id, a, url)
                except Exception as exc:  # isolate failures
                    msg = re.sub(r"https?://\S+", "<url>", (str(exc).splitlines() or [""])[0])
                    log.error("FAILED %s: %s", a.get("title"), msg)
                    self.results[a["id"]] = {"status": "failed", "reason": f"{type(exc).__name__}: {msg}"}
                    self.progress.errors += 1
                self.progress.processed += 1

        for i in range(0, len(todo), 25):
            if self.cancelled:
                break
            batch = todo[i:i + 25]
            urls = await self._urls([a["id"] for _, a in batch])
            await asyncio.gather(*(one(b, a, urls.get(a["id"])) for b, a in batch))
            self.state.save()
        self.state.save()
        return self.results

    async def _urls(self, ids: list[str]) -> dict[str, str | None]:
        try:
            data = await self.client.execute(Q.ASSETS_BY_IDS_DOWNLOAD, {"ids": ids})
        except FrontifyError as exc:
            log.error("could not get download URLs for %d assets: %s", len(ids), exc)
            return {}
        return {a["id"]: a.get("downloadUrl") for a in data.get("assets") or [] if a}

    async def _one(self, brand_id: str, a: dict[str, Any], url: str | None) -> None:
        if not url:
            self.results[a["id"]] = {"status": "unavailable", "reason": "Frontify returned no original-file URL (download-protected, "
                                     "embedded content or insufficient permission); a preview was NOT substituted"}
            log.warning("NOT AVAILABLE %s", a.get("title"))
            self.progress.errors += 1
            return
        prev = self.state.assets.get(a["id"])
        dest = self.layout.root / prev["path"] if prev and prev.get("path") else self.layout.asset_path(a, brand_id, self._taken)
        self._taken.add(str(dest))
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_name(dest.name + ".part")
        last: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                size = await self._fetch(url, part)
                break
            except _Expired as exc:
                last = exc
                url = (await self._urls([a["id"]])).get(a["id"]) or ""
                if not url:
                    raise
            except (_Transient, httpx.TransportError) as exc:
                last = exc
                await asyncio.sleep(min(30, 2 ** attempt))
        else:
            raise RuntimeError(f"failed after {self.retries} attempts: {last}")
        expected = a.get("size")
        if expected and size < int(expected):
            part.unlink(missing_ok=True)
            raise RuntimeError(f"incomplete download ({size} of {expected} bytes)")
        digest = await asyncio.to_thread(sha256_file, part)
        if dest.exists() and prev and prev.get("sha256") and prev["sha256"] != digest:  # changed upstream: keep the old version
            old = self.layout.root / "_previous_versions" / self.layout.rel(dest)
            replace_atomic(dest, old.with_name(f"{old.name}.{prev['sha256'][:8]}"))
        replace_atomic(part, dest)
        dup = self._sha.get(digest)
        dup = dup if dup and dup != a["id"] else None
        self._sha.setdefault(digest, a["id"])
        rel = self.layout.rel(dest)
        self.state.assets[a["id"]] = {"fp": a["fingerprint"], "size": size, "sha256": digest, "path": rel, "duplicate_of": dup}
        note = f"size differs from Frontify metadata ({size} vs {expected})" if expected and size != int(expected) else None
        self.results[a["id"]] = {"status": "downloaded", "path": rel, "sha256": digest, "size": size, "duplicate_of": dup, "reason": note}
        self.progress.downloaded += 1
        self.progress.bytes += size

    async def _fetch(self, url: str, part: Path) -> int:
        offset = part.stat().st_size if part.exists() else 0
        headers = {"Range": f"bytes={offset}-"} if offset else {}
        async with self._http.stream("GET", url, headers=headers) as r:
            if r.status_code in (401, 403, 410):
                raise _Expired(f"HTTP {r.status_code}")
            if r.status_code == 416:
                part.unlink(missing_ok=True)
                raise _Transient("416 on resume")
            if r.status_code == 429 or r.status_code >= 500:
                raise _Transient(f"HTTP {r.status_code}")
            r.raise_for_status()
            resume = r.status_code == 206 and offset
            written = offset if resume else 0
            with open(part, "ab" if resume else "wb") as f:
                async for chunk in r.aiter_bytes(1 << 16):
                    f.write(chunk)
                    written += len(chunk)
            return written
