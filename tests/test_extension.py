# SPDX-License-Identifier: Apache-2.0
"""Chrome extension: JS stays in sync with the Python extractor, and an end-to-end capture -> ZIP run in real Chromium."""
from __future__ import annotations

import io
import json
import os
import shutil
import zipfile
from pathlib import Path

import pytest

from src.browser.extract_js import EXTRACT

EXT = Path(__file__).resolve().parent.parent / "extension"


def test_extract_js_in_sync():
    assert (EXT / "lib" / "extract.js").read_text().endswith("(" + EXTRACT.strip() + ")();\n")


def test_manifest_is_mv3_and_minimal():
    m = json.loads((EXT / "manifest.json").read_text())
    assert m["manifest_version"] == 3
    assert "<all_urls>" not in json.dumps(m) and "https://*/*" not in m.get("host_permissions", [])  # broad access is optional + on demand only


async def test_capture_and_export_zip_in_real_chromium(tmp_path):
    pytest.importorskip("playwright")
    import threading

    from playwright.async_api import async_playwright

    from tests.test_browser import Portal, ThreadingHTTPServer  # reuse the local simulated portal

    chrome = os.getenv("FX_BROWSER_PATH")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Portal)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    ext = tmp_path / "ext"
    shutil.copytree(EXT, ext)
    man = json.loads((ext / "manifest.json").read_text())
    man["host_permissions"].append("http://127.0.0.1/*")  # test only: skip the runtime permission prompt
    (ext / "manifest.json").write_text(json.dumps(man))
    try:
        async with async_playwright() as pw:
            try:
                ctx = await pw.chromium.launch_persistent_context(
                    str(tmp_path / "profile"), executable_path=chrome, headless=False, accept_downloads=True,
                    args=["--headless=new", f"--disable-extensions-except={ext}", f"--load-extension={ext}", "--no-sandbox"])
            except Exception as exc:
                pytest.skip(f"Chromium with extensions not available: {str(exc)[:80]}")
            await ctx.add_cookies([{"name": "session", "value": "ok", "url": base}])
            sw = ctx.service_workers[0] if ctx.service_workers else await ctx.wait_for_event("serviceworker")
            ext_id = sw.url.split("/")[2]
            page = await ctx.new_page()

            async def capture() -> None:
                tab_id = await sw.evaluate("async () => (await chrome.tabs.query({url: 'http://127.0.0.1/*'}))[0].id")
                pop = await ctx.new_page()
                await pop.goto(f"chrome-extension://{ext_id}/popup.html?tab={tab_id}")
                await pop.click("#cap")
                await pop.locator("#log", has_text="✓").wait_for()
                await pop.close()

            await page.goto(base + "/")
            await capture()
            await page.goto(base + "/colors")
            await capture()

            pop = await ctx.new_page()
            await pop.goto(f"chrome-extension://{ext_id}/popup.html")
            await pop.fill("#delay", "0")
            async with pop.expect_download() as dl:
                await pop.click("#exp")
            path = await (await dl.value).path()
            z = zipfile.ZipFile(io.BytesIO(Path(path).read_bytes()))
            names = z.namelist()
            md = "\n".join(z.read(n).decode() for n in names if n.startswith("01_BRAND_GUIDELINES/"))
            assert "# Acme Brand" in md and "Primary red is #E30613." in md
            assert "03_DOCUMENTATION/guide.pdf" in names and z.read("03_DOCUMENTATION/guide.pdf").startswith(b"%PDF")
            assert any(n.startswith("02_ASSETS/") and n.endswith("logo.svg") for n in names)
            vi = z.read("06_AI_KNOWLEDGE/VISUAL_IDENTITY.md").decode()
            assert "#E30613" in vi and "Georgia" in vi
            assert json.loads(z.read("EXPORT_REPORT.json"))["summary"]["pages_captured"] == 2
            assert z.testzip() is None
            await ctx.close()
    finally:
        srv.shutdown()
