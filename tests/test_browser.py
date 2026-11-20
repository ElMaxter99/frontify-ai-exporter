# SPDX-License-Identifier: Apache-2.0
"""Browser mode against a tiny local 'portal' (cookie-protected pages, robots.txt, a PDF and an SVG)."""
from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

pytest.importorskip("playwright")

PAGES = {
    "/": '<main><h1>Acme Brand</h1><p>Our voice is warm.</p><a href="/colors">Colors</a> <a href="/private">Secret</a> '
         '<a href="/logout">Out</a> <a href="/files/guide.pdf">Download guide</a><img src="/logo.svg" width="120" height="60" alt="Acme logo"></main>',
    "/colors": '<main><h1 style="font-family: Georgia, serif">Colors</h1><p>Primary red is #E30613.</p>'
               '<ul><li>Use red sparingly</li></ul><div style="width:80px;height:80px;background:#e30613"></div></main>',
    "/private": "<main><h1>Do not crawl</h1></main>",
}
SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="120" height="60"><rect width="120" height="60" fill="red"/></svg>'


class Portal(BaseHTTPRequestHandler):
    hits: list[str] = []

    def log_message(self, *a):  # silence
        pass

    def _send(self, code, body, ctype="text/html"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        Portal.hits.append(self.path)
        if self.path == "/robots.txt":
            return self._send(200, b"User-agent: *\nDisallow: /private\n", "text/plain")
        if "session=ok" not in (self.headers.get("Cookie") or ""):
            self.send_response(302)
            self.send_header("Location", "/login")
            self.end_headers()
            return
        if self.path == "/login":
            return self._send(200, b"<h1>Login</h1>")
        if self.path == "/logo.svg":
            return self._send(200, SVG, "image/svg+xml")
        if self.path == "/files/guide.pdf":
            return self._send(200, b"%PDF-1.4 fake", "application/pdf")
        if self.path in PAGES:
            return self._send(200, PAGES[self.path].encode())
        self._send(404, b"nope")


@pytest.fixture
def portal(tmp_path):
    Portal.hits = []
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Portal)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"cookies": [{"name": "session", "value": "ok", "domain": "127.0.0.1", "path": "/", "expires": -1,
                                              "httpOnly": False, "secure": False, "sameSite": "Lax"}], "origins": []}))
    yield f"http://127.0.0.1:{srv.server_address[1]}", state
    srv.shutdown()


async def test_browse_exports_pages_files_and_respects_robots(portal, tmp_path):
    from src.browser.crawler import BrowserExporter

    url, state = portal
    ex = BrowserExporter(url, tmp_path / "EXPORTS", client_name="ACME", state_file=state, delay=0, browser_path=os.getenv("FX_BROWSER_PATH"))
    try:
        rep = await ex.export()
    except Exception as exc:  # no usable browser in this environment
        if "Executable doesn't exist" in str(exc) or "playwright install" in str(exc):
            pytest.skip("Chromium not available")
        raise
    root = tmp_path / "EXPORTS" / "ACME"
    s = rep["summary"]
    assert s["pages_exported"] == 2 and s["errors"] == 0
    assert rep["robots_skipped"] == [f"{url}/private"]
    assert "/private" not in [h for h in Portal.hits if h != "/robots.txt"]       # never requested
    assert "/logout" not in Portal.hits                                            # skipped by scope rules
    md = "\n".join(p.read_text() for p in (root / "01_BRAND_GUIDELINES").glob("*.md"))
    assert "# Acme Brand" in md and "Our voice is warm." in md and "- Use red sparingly" in md
    vi = (root / "06_AI_KNOWLEDGE" / "VISUAL_IDENTITY.md").read_text()
    assert "#E30613" in vi and "Georgia" in vi
    assert (root / "03_DOCUMENTATION" / "guide.pdf").read_bytes().startswith(b"%PDF")
    assert any(f["status"] == "downloaded" and f["category"] in ("logos", "images") for f in rep["files"])
    assert s["http_requests_total"] > 0 and rep["settings"]["concurrency"] == 1
    assert "frontify-ai-exporter-browser" in rep["settings"]["user_agent"]
    assert (root / "manifest.json").exists() and not (root / "_tmp").exists()


async def test_missing_session_gives_clear_error(tmp_path):
    from src.browser.crawler import BrowserExporter

    with pytest.raises(FileNotFoundError, match="browse-login"):
        await BrowserExporter("https://acme.frontify.com", tmp_path, state_file=tmp_path / "none.json").export()
