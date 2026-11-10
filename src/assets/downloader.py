"""Concurrent, resumable, integrity-checked download of ORIGINAL asset files.

* Fresh signed ``downloadUrl`` values are requested right before downloading (they expire).
* Never uses previews/thumbnails: if Frontify gives no original URL the asset is marked
  ``unavailable`` (e.g. download-protected) instead of silently substituting a preview.
* Per-asset failures never stop the run. Partial files (``.part``) are resumed with HTTP Range.
* Downloads use a separate HTTP client that does NOT send the Frontify token to CDN hosts.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Any

import httpx

from src.database.repo import Repo
from src.exporter.layout import Layout
from src.frontify import queries as Q
from src.frontify.client import FrontifyClient, FrontifyError
from src.utils.events import EventBus
from src.utils.files import sha256_file, utcnow_iso

log = logging.getLogger("downloader")


class TransientDownload(Exception):
    pass


class ExpiredUrl(Exception):
    pass


class AssetDownloader:
    def __init__(self, client: FrontifyClient, repo: Repo, bus: EventBus, layout: Layout, *, concurrency: int = 4,
                 dedupe_hardlinks: bool = False, transport: httpx.AsyncBaseTransport | None = None,
                 retries: int = 3) -> None:
        self.client, self.repo, self.bus, self.layout = client, repo, bus, layout
        self.concurrency = max(1, concurrency)
        self.dedupe_hardlinks = dedupe_hardlinks
        self.retries = retries
        self._http = httpx.AsyncClient(transport=transport, follow_redirects=True,
                                       timeout=httpx.Timeout(120.0, connect=20.0),
                                       headers={"User-Agent": "frontify-ai-exporter/0.1"})
        self.stats = {"downloaded": 0, "skipped_unchanged": 0, "failed": 0, "unavailable": 0, "bytes": 0, "duplicates": 0}
        self._cancel = asyncio.Event()
        self._taken: set[str] = set()

    def cancel(self) -> None:
        self._cancel.set()

    async def aclose(self) -> None:
        await self._http.aclose()

    # --------------------------------------------------------------- selection
    def select(self, brand_ids: set[str] | None, categories: set[str] | None, force: bool) -> list[dict[str, Any]]:
        rows = self.repo.db.query("SELECT * FROM assets WHERE status='active' ORDER BY brand_id, folder_path, title")
        out = []
        for r in rows:
            if brand_ids and r["brand_id"] not in brand_ids:
                continue
            if categories and r["category"] not in categories:
                continue
            if force or r["download_status"] in ("pending", "failed") or not self._intact(r):
                out.append(r)
            else:
                self.stats["skipped_unchanged"] += 1
        return out

    @staticmethod
    def _intact(r: dict[str, Any]) -> bool:
        if r["download_status"] != "done" or not r["local_path"]:
            return r["download_status"] in ("unavailable", "skipped")
        p = Path(r["local_path"])
        return p.exists() and (r["size"] is None or p.stat().st_size == r["size"] or bool(r["sha256"]))

    # --------------------------------------------------------------------- run
    async def run(self, brand_ids: set[str] | None = None, categories: set[str] | None = None, force: bool = False) -> dict[str, Any]:
        todo = self.select(brand_ids, categories, force)
        total = len(todo)
        log.info("Downloading %d asset(s) (%d unchanged, skipped)", total, self.stats["skipped_unchanged"])
        self._taken = {r["local_path"] for r in self.repo.db.query("SELECT local_path FROM assets WHERE local_path IS NOT NULL")}
        sem = asyncio.Semaphore(self.concurrency)
        done = 0

        async def one(row: dict[str, Any], url: str | None) -> None:
            nonlocal done
            async with sem:
                if self._cancel.is_set():
                    return
                try:
                    await self._download_asset(row, url)
                except Exception as exc:  # isolate: one asset must never stop the export
                    self._fail(row, f"{type(exc).__name__}: {exc}")
                done += 1
                self.bus.publish("progress", {"phase": "download", "done": done, "total": total, **self.stats})

        for i in range(0, total, 25):
            if self._cancel.is_set():
                break
            batch = todo[i:i + 25]
            urls = await self._fresh_urls([r["id"] for r in batch])
            await asyncio.gather(*(one(r, urls.get(r["id"])) for r in batch))
        return {**self.stats, "attempted": total}

    async def _fresh_urls(self, ids: list[str]) -> dict[str, str | None]:
        try:
            data = await self.client.execute(Q.ASSETS_BY_IDS_DOWNLOAD, {"ids": ids}, operation="AssetDownloadUrls")
        except FrontifyError as exc:
            log.error("could not obtain download URLs for a batch of %d: %s", len(ids), exc)
            return {}
        return {a["id"]: a.get("downloadUrl") for a in data.get("assets") or [] if a}

    # ---------------------------------------------------------------- one file
    async def _download_asset(self, row: dict[str, Any], url: str | None) -> None:
        if not url:
            self.repo.db.execute(
                "UPDATE assets SET download_status='unavailable', error=? WHERE id=?",
                ("Frontify returned no original file URL (download-protected, embedded content or no permission)", row["id"]))
            self.stats["unavailable"] += 1
            log.warning("asset %s '%s': no original file available", row["id"], row["title"])
            return
        # An asset keeps its path across re-downloads (the changed file replaces the old one atomically).
        dest = Path(row["local_path"]) if row["local_path"] else self.layout.asset_path(row, self._taken)
        self._taken.add(str(dest))
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_name(dest.name + ".part")
        last: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                size = await self._fetch(url, part)
                break
            except ExpiredUrl as exc:
                last = exc
                fresh = (await self._fresh_urls([row["id"]])).get(row["id"])
                if not fresh:
                    raise
                url = fresh
            except (TransientDownload, httpx.TransportError) as exc:
                last = exc
                await asyncio.sleep(min(30, 2 ** attempt))
        else:
            raise RuntimeError(f"download failed after {self.retries} attempts: {last}")

        expected = row["size"]
        if expected and size < expected:
            part.unlink(missing_ok=True)
            raise RuntimeError(f"incomplete download: got {size} of {expected} bytes")
        note = None
        if expected and size != expected:
            note = f"size differs from metadata ({size} vs {expected})"
            log.warning("asset %s: %s", row["id"], note)
        digest = await asyncio.to_thread(sha256_file, part)
        os.replace(part, dest)
        dup = self.repo.db.one("SELECT id, local_path FROM assets WHERE sha256=? AND id<>? AND local_path IS NOT NULL", (digest, row["id"]))
        dup_id = dup["id"] if dup else None
        if dup and self.dedupe_hardlinks and Path(dup["local_path"]).exists() and dup["local_path"] != str(dest):
            try:
                tmp = dest.with_name(dest.name + ".lnk")
                os.link(dup["local_path"], tmp)
                os.replace(tmp, dest)
            except OSError:
                pass
        if dup:
            self.stats["duplicates"] += 1
        self.repo.db.execute(
            """UPDATE assets SET download_status='done', local_path=?, sha256=?, downloaded_at=?, duplicate_of=?, error=?, size=COALESCE(size,?)
               WHERE id=?""", (str(dest), digest, utcnow_iso(), dup_id, note, size, row["id"]))
        self.stats["downloaded"] += 1
        self.stats["bytes"] += size

    async def _fetch(self, url: str, part: Path) -> int:
        offset = part.stat().st_size if part.exists() else 0
        headers = {"Range": f"bytes={offset}-"} if offset else {}
        async with self._http.stream("GET", url, headers=headers) as resp:
            if resp.status_code in (401, 403, 410):
                raise ExpiredUrl(f"HTTP {resp.status_code}")
            if resp.status_code == 416:  # range not satisfiable -> file already complete or part is bogus
                part.unlink(missing_ok=True)
                raise TransientDownload("416 on resume, restarting")
            if resp.status_code == 429 or resp.status_code >= 500:
                raise TransientDownload(f"HTTP {resp.status_code}")
            resp.raise_for_status()
            mode = "ab" if resp.status_code == 206 and offset else "wb"
            if mode == "wb":
                offset = 0
            written = offset
            with open(part, mode) as f:
                async for chunk in resp.aiter_bytes(1 << 16):
                    f.write(chunk)
                    written += len(chunk)
            return written

    def _fail(self, row: dict[str, Any], msg: str) -> None:
        log.error("asset %s '%s' failed: %s", row["id"], row["title"], msg)
        msg = re.sub(r"https?://\S+", "<url>", msg)
        self.repo.db.execute("UPDATE assets SET download_status='failed', error=?, attempts=attempts+1 WHERE id=?", (msg[:500], row["id"]))
        self.stats["failed"] += 1
