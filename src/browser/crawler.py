# SPDX-License-Identifier: Apache-2.0
"""Crawl a Frontify portal in a real browser session (login given by the client) and export what is visible.

Deliberately polite and identifiable:
* one page at a time, fixed delay between navigations and downloads;
* honest User-Agent (the tool's name) — it does not pretend to be a person;
* ``robots.txt`` is respected; skipped URLs are listed in the report;
* analytics/tracking hosts are blocked to reduce load; every request made is counted and reported.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import mimetypes
import re
import urllib.robotparser
from collections import deque
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urldefrag, urlparse

import httpx

from src.assets.classify import category_for
from src.browser.extract_js import EXTRACT
from src.config import normalize_domain
from src.utils.files import human_size, safe_name, sha256_file, slugify, utcnow_iso, write_json, write_text

log = logging.getLogger("browser")

USER_AGENT = "frontify-ai-exporter-browser/1.0 (+https://github.com/ElMaxter99/frontify-ai-exporter)"
FILE_EXT = re.compile(r"\.(pdf|zip|docx?|xlsx?|pptx?|key|ai|eps|psd|indd|idml|svg|png|jpe?g|gif|webp|tiff?|mp4|mov|webm|mp3|wav|ttf|otf|woff2?|csv|json)(\?|$)", re.I)
SKIP_LINK = re.compile(r"logout|log-out|signout|sign-out|/api/|mailto:|tel:|/auth/|/login", re.I)
TRACKERS = re.compile(r"google-analytics|googletagmanager|doubleclick|hotjar|segment\.(io|com)|intercom|sentry\.io|fullstory|mixpanel|"
                      r"amplitude|clarity\.ms|facebook\.net|linkedin\.com/px|hs-scripts|hubspot|datadoghq|newrelic|bugsnag|optimizely", re.I)
CAT_DIR = {"logos": "LOGOS", "images": "IMAGES", "photography": "PHOTOGRAPHY", "videos": "VIDEOS", "icons": "ICONS",
           "illustrations": "ILLUSTRATIONS", "audio": "AUDIO", "other": "OTHER"}
LIMITATIONS = [
    "Browser mode only sees what the logged-in user sees in the rendered page; structured Frontify metadata (tags, custom fields, folders) is not available.",
    "Colours/fonts come from rendered page elements (heuristic) — compare with the guideline text before relying on them.",
    "Original files are only saved when the portal exposes a downloadable link (or --click-downloads triggers a download button) for this user.",
    "Page structure depends on Frontify's HTML, which can change without notice.",
]


def default_state_path(domain: str) -> Path:
    return Path(".browser_state") / f"{safe_name(domain, 'portal')}.json"


class BrowserExporter:
    def __init__(self, url: str, dest: str | Path, *, client_name: str | None = None, state_file: str | Path | None = None,
                 delay: float = 2.0, max_pages: int = 200, max_depth: int = 6, include: str | None = None, exclude: str | None = None,
                 download_files: bool = True, click_downloads: bool = False, max_file_mb: int = 200, headless: bool = True,
                 browser_path: str | None = None, user_agent_suffix: str | None = None) -> None:
        self.start_url = url if re.match(r"^https?://", url, re.I) else f"https://{url}"
        self.domain = normalize_domain(url)
        self.dest = Path(dest).expanduser().resolve()
        self.client_name = safe_name(client_name or self.domain.split(".")[0] or "client", "client")
        self.root = self.dest / self.client_name
        self.state_file = Path(state_file) if state_file else default_state_path(self.domain)
        self.delay, self.max_pages, self.max_depth = max(0.0, delay), max_pages, max_depth
        self.include = re.compile(include) if include else None
        self.exclude = re.compile(exclude) if exclude else None
        self.download_files, self.click_downloads = download_files, click_downloads
        self.max_bytes = max_file_mb * 1024 * 1024
        self.headless, self.browser_path = headless, browser_path
        self.user_agent = USER_AGENT + (f" {user_agent_suffix}" if user_agent_suffix else "")
        self.requests = 0
        self.blocked_trackers = 0
        self.fonts_seen: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------ login
    async def login(self) -> Path:
        """Open a visible browser; the person logs in; the session is saved to ``state_file`` (treat it like a password)."""
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=False, executable_path=self.browser_path)
            ctx = await browser.new_context(user_agent=self.user_agent)
            page = await ctx.new_page()
            await page.goto(self.start_url)
            await asyncio.to_thread(input, "Log in in the browser window, open the portal, then press Enter here to save the session... ")
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            await ctx.storage_state(path=str(self.state_file))
            self.state_file.chmod(0o600)
            await browser.close()
        return self.state_file

    # ---------------------------------------------------------------- helpers
    def _robots(self) -> urllib.robotparser.RobotFileParser | None:
        base = f"{urlparse(self.start_url).scheme}://{urlparse(self.start_url).netloc}"
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = httpx.get(f"{base}/robots.txt", headers={"User-Agent": self.user_agent}, timeout=15, follow_redirects=True)
            self.requests += 1
            if r.status_code != 200:
                return None
            rp.parse(r.text.splitlines())
            return rp
        except httpx.HTTPError:
            return None

    def _in_scope(self, url: str) -> bool:
        p = urlparse(url)
        if p.netloc.lower() != urlparse(self.start_url).netloc.lower() or SKIP_LINK.search(url) or FILE_EXT.search(p.path + "?"):
            return False
        if self.include and not self.include.search(url):
            return False
        return not (self.exclude and self.exclude.search(url))

    async def _route(self, route: Any) -> None:
        if TRACKERS.search(route.request.url):
            self.blocked_trackers += 1
            await route.abort()
        else:
            await route.continue_()

    # ----------------------------------------------------------------- export
    async def export(self) -> dict[str, Any]:
        from playwright.async_api import async_playwright

        if not self.state_file.exists():
            raise FileNotFoundError(f"No saved session at {self.state_file}. Run `python -m src browse-login --url {self.start_url}` first "
                                    "(or pass --state with a Playwright storage-state file).")
        started = utcnow_iso()
        self.root.mkdir(parents=True, exist_ok=True)
        robots = self._robots()
        pages: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        robots_skipped: list[str] = []
        candidates: dict[str, dict[str, Any]] = {}  # url -> {kind, from, text}
        downloaded: list[dict[str, Any]] = []

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=self.headless, executable_path=self.browser_path)
            ctx = await browser.new_context(storage_state=str(self.state_file), user_agent=self.user_agent, accept_downloads=True)
            await ctx.route("**/*", self._route)
            ctx.on("request", lambda _r: setattr(self, "requests", self.requests + 1))
            ctx.on("response", lambda r: self._on_response(r, candidates))
            page = await ctx.new_page()
            queue: deque[tuple[str, int]] = deque([(urldefrag(self.start_url)[0], 0)])
            seen = {queue[0][0]}
            while queue and len(pages) < self.max_pages:
                url, depth = queue.popleft()
                if robots and not robots.can_fetch(self.user_agent, url):
                    robots_skipped.append(url)
                    continue
                try:
                    await page.goto(url, wait_until="networkidle", timeout=45000)
                    if re.search(r"/login|/sign-?in|/auth", urlparse(page.url).path, re.I) and not re.search(r"/login|/sign-?in|/auth", urlparse(url).path, re.I):
                        raise PermissionError("redirected to a login page: the saved session expired — run browse-login again")
                    data = await page.evaluate(EXTRACT)
                    if self.click_downloads and self.download_files:
                        downloaded += await self._click_downloads(page, data, len(pages))
                except PermissionError:
                    await browser.close()
                    raise
                except Exception as exc:
                    log.error("FAILED %s: %s", url, exc)
                    errors.append({"url": url, "reason": f"{type(exc).__name__}: {str(exc).splitlines()[0] if str(exc) else ''}"})
                    await asyncio.sleep(self.delay)
                    continue
                data["depth"] = depth
                pages.append(data)
                log.info("[%d] %s  (%d links, %d images)", len(pages), data["title"], len(data["links"]), len(data["images"]))
                for im in data["images"]:
                    candidates.setdefault(im["src"], {"kind": "image", "from": url, "text": im.get("alt")})
                for d in data["downloads"]:
                    candidates.setdefault(d["href"], {"kind": "download", "from": url, "text": d.get("text")})
                for ln in data["links"]:
                    h = urldefrag(ln["href"])[0]
                    if FILE_EXT.search(urlparse(h).path + "?"):
                        candidates.setdefault(h, {"kind": "download", "from": url, "text": ln.get("text")})
                    elif depth < self.max_depth and h not in seen and self._in_scope(h):
                        seen.add(h)
                        queue.append((h, depth + 1))
                await asyncio.sleep(self.delay)

            if self.download_files:
                downloaded += await self._download_all(ctx, candidates)
            await browser.close()

        report = self._write(pages, downloaded, errors, robots_skipped, started)
        return report

    def _on_response(self, resp: Any, candidates: dict[str, dict[str, Any]]) -> None:
        try:
            if resp.request.resource_type == "font" and resp.ok:
                self.fonts_seen.setdefault(resp.url, {"url": resp.url})
                candidates.setdefault(resp.url, {"kind": "font", "from": resp.frame.url if resp.frame else None, "text": None})
        except Exception:  # never let an event handler break the crawl
            pass

    # -------------------------------------------------------------- downloads
    async def _click_downloads(self, page: Any, data: dict[str, Any], page_no: int) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for c in data.get("clickable", [])[:10]:
            try:
                async with page.expect_download(timeout=15000) as info:
                    await page.locator(f'[data-fx-dl="{c["idx"]}"]').first.click(timeout=5000)
                dl = await info.value
                name = safe_name(dl.suggested_filename or c["text"] or f"download-{page_no}")
                tmp = self.root / "_tmp" / name
                tmp.parent.mkdir(parents=True, exist_ok=True)
                await dl.save_as(str(tmp))
                rec = self._store_file(tmp, name, source=page.url, kind="click-download", text=c["text"])
                if rec:
                    out.append(rec)
            except Exception as exc:
                log.warning("click-download on '%s' produced no file: %s", c.get("text"), type(exc).__name__)
            await asyncio.sleep(self.delay)
        return out

    async def _download_all(self, ctx: Any, candidates: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for url, meta in candidates.items():
            if url.startswith("data:") or TRACKERS.search(url):
                continue
            try:
                resp = await ctx.request.get(url, timeout=60000, max_redirects=5)
                self.requests += 1
                ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
                if not resp.ok or (meta["kind"] == "download" and ctype in ("text/html", "application/xhtml+xml")):
                    continue  # a "download" link that is really a page, or an error
                body = await resp.body()
                if len(body) > self.max_bytes:
                    out.append({"url": url, "status": "skipped", "reason": f"larger than limit ({human_size(len(body))})", **meta})
                    continue
                name = self._filename(url, resp.headers.get("content-disposition"), ctype)
                tmp = self.root / "_tmp" / name
                tmp.parent.mkdir(parents=True, exist_ok=True)
                tmp.write_bytes(body)
                rec = self._store_file(tmp, name, source=url, kind=meta["kind"], text=meta.get("text"), page=meta.get("from"))
                if rec:
                    out.append(rec)
            except Exception as exc:
                out.append({"url": url, "status": "failed", "reason": f"{type(exc).__name__}", **meta})
            await asyncio.sleep(self.delay / 2)
        return out

    @staticmethod
    def _filename(url: str, disposition: str | None, ctype: str) -> str:
        m = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)", disposition or "", re.I)
        name = unquote(m.group(1)) if m else unquote(Path(urlparse(url).path).name)
        name = safe_name(name or "file", "file")
        if "." not in name:
            name += mimetypes.guess_extension(ctype) or ""
        return name

    def _store_file(self, tmp: Path, name: str, *, source: str, kind: str, text: str | None = None, page: str | None = None) -> dict[str, Any] | None:
        digest = sha256_file(tmp)
        ext = Path(name).suffix.lstrip(".").lower()
        cat = "fonts" if kind == "font" else category_for(ext, text, name, name)
        if kind == "image" and cat == "images" and (text or "").strip():
            cat = category_for(ext, None, text, name)
        sub = {"documents": "03_DOCUMENTATION", "fonts": "04_DESIGN_SYSTEM/fonts"}.get(cat) or f"02_ASSETS/{CAT_DIR.get(cat, 'OTHER')}"
        dest = self.root / sub / name
        if dest.exists() and sha256_file(dest) != digest:
            dest = dest.with_name(f"{dest.stem}-{digest[:8]}{dest.suffix}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        if self._digest_seen(digest):
            tmp.unlink(missing_ok=True)
            return {"url": source, "status": "duplicate", "sha256": digest, "kind": kind}
        tmp.replace(dest)
        return {"url": source, "status": "downloaded", "path": dest.relative_to(self.root).as_posix(), "sha256": digest, "size": dest.stat().st_size,
                "category": cat, "kind": kind, "from_page": page, "text": text}

    _digests: set[str] | None = None

    def _digest_seen(self, digest: str) -> bool:
        if self._digests is None:
            self._digests = set()
        if digest in self._digests:
            return True
        self._digests.add(digest)
        return False

    # ----------------------------------------------------------------- output
    def _write(self, pages: list[dict[str, Any]], files: list[dict[str, Any]], errors: list[dict[str, Any]], robots_skipped: list[str],
               started: str) -> dict[str, Any]:
        meta, ai = self.root / "05_METADATA", self.root / "06_AI_KNOWLEDGE"
        now = utcnow_iso()
        page_files: list[tuple[dict[str, Any], str]] = []
        for i, p in enumerate(pages, 1):
            rel = f"01_BRAND_GUIDELINES/{i:03d}-{slugify(p['title'], 'page')[:60]}.md"
            body = (f'---\nsource_url: "{p["url"]}"\ntitle: "{p["title"].replace(chr(34), chr(39))}"\nextracted_at: {now}\nmode: browser\n---\n\n'
                    f"{p['markdown'] or '_Not available (no text found on this page)_'}\n")
            write_text(self.root / rel, body)
            page_files.append((p, rel))
        write_json(meta / "pages.json", [{"url": p["url"], "title": p["title"], "file": rel, "depth": p["depth"], "links": len(p["links"]),
                                          "images": [im["src"] for im in p["images"]], "fonts": p["fonts"]} for p, rel in page_files])
        write_json(meta / "assets.json", files)

        colors: dict[str, dict[str, Any]] = {}
        for p in pages:
            for s in p["swatches"]:
                c = colors.setdefault(s["css"], {"css": s["css"], "labels": set(), "pages": set()})
                if s.get("label"):
                    c["labels"].add(s["label"][:160])
                c["pages"].add(p["url"])
        color_list = [{"css": c["css"], "hex": _to_hex(c["css"]), "labels": sorted(c["labels"])[:3], "pages": len(c["pages"])} for c in colors.values()]
        hex_in_text = sorted({m.upper() for p in pages for m in re.findall(r"#[0-9a-fA-F]{6}\b", p["text_sample"] + p["markdown"])})
        fams: dict[str, int] = {}
        for p in pages:
            for key in ("heading", "body"):
                v = p["fonts"].get(key)
                if v:
                    fams[v] = fams.get(v, 0) + 1
            for f in p["fonts"].get("loaded", []):
                fams.setdefault(f["family"], 0)
        write_json(meta / "colors.json", {"swatches_heuristic": color_list, "hex_values_in_text": hex_in_text})
        write_json(meta / "fonts.json", {"css_font_stacks": fams, "font_files_seen": list(self.fonts_seen)})

        write_text(ai / "BRAND_GUIDELINES.md", "# Guidelines (browser capture)\n\n" + "\n\n---\n\n".join(
            f"<!-- source: {p['url']} -->\n{p['markdown']}" for p, _ in page_files if p["markdown"]) + "\n")
        vi = ["# Visual identity (browser capture)\n",
              "> Read from the rendered portal, not from the API. Colours/fonts are heuristics — verify against the guideline text. Missing data is 'Not available'.\n",
              "## Colours written in the guidelines (HEX)\n", ("\n".join(f"- `{h}`" for h in hex_in_text) or "_Not available_"), "",
              "## Colour swatches detected on pages (heuristic)\n",
              ("\n".join(f"- `{c['hex'] or c['css']}` — {('; '.join(c['labels'])) or 'no label'}" for c in color_list[:60]) or "_Not available_"), "",
              "## Fonts\n", ("\n".join(f"- {f}" for f in fams) or "_Not available_"), "",
              "## Downloaded brand files\n",
              ("\n".join(f"- `{f['path']}` ({f['category']}) — from {f.get('from_page') or f['url']}" for f in files if f["status"] == "downloaded") or "_None_"), ""]
        write_text(ai / "VISUAL_IDENTITY.md", "\n".join(vi))
        write_text(self.root / "README_AI.md",
                   f"# {self.client_name} — export from {self.domain} (browser mode)\n\nCaptured {now} by reading the portal as a logged-in user.\n\n"
                   "- `06_AI_KNOWLEDGE/VISUAL_IDENTITY.md` and `BRAND_GUIDELINES.md`: start here.\n- `01_BRAND_GUIDELINES/`: one Markdown per page with its source URL.\n"
                   "- `05_METADATA/`: pages, assets, colours, fonts (JSON).\n- `EXPORT_REPORT.json`: what was captured, skipped or failed.\n\n"
                   "Rules: use only values found here; if something is \"Not available\", say so and ask; never invent colours, fonts or rules.\n")

        done = [f for f in files if f["status"] == "downloaded"]
        report = {"mode": "browser", "frontify_domain": self.domain, "started_at": started, "finished_at": utcnow_iso(),
                  "settings": {"delay_seconds": self.delay, "max_pages": self.max_pages, "max_depth": self.max_depth, "concurrency": 1,
                              "user_agent": self.user_agent, "download_files": self.download_files, "click_downloads": self.click_downloads},
                  "summary": {"pages_exported": len(pages), "files_downloaded": len(done), "bytes_downloaded": sum(f["size"] for f in done),
                              "files_failed_or_skipped": len([f for f in files if f["status"] in ("failed", "skipped")]),
                              "http_requests_total": self.requests, "tracker_requests_blocked": self.blocked_trackers,
                              "errors": len(errors), "robots_skipped": len(robots_skipped)},
                  "errors": errors, "robots_skipped": robots_skipped[:200], "files": files, "limitations": LIMITATIONS}
        write_json(self.root / "EXPORT_REPORT.json", report)
        manifest = {p.relative_to(self.root).as_posix(): {"bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                    for p in sorted(self.root.rglob("*")) if p.is_file() and "_tmp" not in p.parts and p.name != "manifest.json"}
        write_json(self.root / "manifest.json", {"generator": "frontify-exporter-browser", "generated_at": utcnow_iso(), "files": manifest})
        tmpdir = self.root / "_tmp"
        if tmpdir.exists():
            for leftover in tmpdir.rglob("*"):
                if leftover.is_file():
                    leftover.unlink()
            for d in sorted(tmpdir.rglob("*"), reverse=True):
                d.rmdir()
            tmpdir.rmdir()
        return report


def _to_hex(css: str) -> str | None:
    m = re.match(r"rgba?\((\d+),\s*(\d+),\s*(\d+)", css)
    return "#{:02X}{:02X}{:02X}".format(*map(int, m.groups())) if m else None

