# SPDX-License-Identifier: Apache-2.0
"""``python -m src`` opens the UI; ``python -m src export --url … --dest …`` runs headless."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import threading
import webbrowser

from src.exporter.progress import Progress
from src.exporter.run import Exporter
from src.utils.logging import setup_logging


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="frontify-exporter")
    sub = ap.add_subparsers(dest="cmd")
    ui = sub.add_parser("ui", help="open the local interface (default)")
    ui.add_argument("--port", type=int, default=8765)
    ui.add_argument("--host", default="127.0.0.1")
    ui.add_argument("--no-browser", action="store_true")
    for name in ("analyze", "export"):
        p = sub.add_parser(name)
        p.add_argument("--url", required=True)
        p.add_argument("--dest", default="EXPORTS")
        p.add_argument("--name", help="client folder name (default: subdomain)")
        p.add_argument("--concurrency", type=int, default=4)
        p.add_argument("--token", help="API token (prefer the FRONTIFY_TOKEN environment variable)")
    for name, hlp in (("browse-login", "log in once in a visible browser and save the session"),
                      ("browse", "export by reading the portal in a browser with the saved session (no API token)")):
        p = sub.add_parser(name, help=hlp)
        p.add_argument("--url", required=True)
        p.add_argument("--state", help="session file (default: .browser_state/<domain>.json)")
        p.add_argument("--browser-path", help="Chromium/Chrome executable (default: Playwright's)")
        if name == "browse":
            p.add_argument("--dest", default="EXPORTS")
            p.add_argument("--name", help="client folder name (default: subdomain)")
            p.add_argument("--delay", type=float, default=2.0, help="seconds between pages (default 2)")
            p.add_argument("--max-pages", type=int, default=200)
            p.add_argument("--max-depth", type=int, default=6)
            p.add_argument("--include", help="only follow URLs matching this regex")
            p.add_argument("--exclude", help="never follow URLs matching this regex")
            p.add_argument("--no-files", action="store_true", help="pages only: do not download images/files")
            p.add_argument("--click-downloads", action="store_true", help="also click visible 'Download' buttons (off by default)")
            p.add_argument("--max-file-mb", type=int, default=200)
            p.add_argument("--headed", action="store_true", help="show the browser window")
            p.add_argument("--user-agent-suffix", help="appended to the honest User-Agent, e.g. your company name")
    a = ap.parse_args(argv)
    if a.cmd in (None, "ui"):
        import uvicorn

        port = getattr(a, "port", 8765)
        if not getattr(a, "no_browser", False):
            threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
        uvicorn.run("src.app:app_factory", factory=True, host=getattr(a, "host", "127.0.0.1"), port=port, log_level="warning")
        return 0
    setup_logging("INFO")
    if a.cmd in ("browse-login", "browse"):
        try:
            from src.browser.crawler import BrowserExporter
        except ImportError:  # pragma: no cover
            print("Browser mode needs Playwright: pip install -r requirements-browser.txt", file=sys.stderr)
            return 2
        bx = BrowserExporter(a.url, getattr(a, "dest", "EXPORTS"), client_name=getattr(a, "name", None), state_file=a.state, browser_path=a.browser_path,
                             **({} if a.cmd == "browse-login" else dict(
                                 delay=a.delay, max_pages=a.max_pages, max_depth=a.max_depth, include=a.include, exclude=a.exclude,
                                 download_files=not a.no_files, click_downloads=a.click_downloads, max_file_mb=a.max_file_mb,
                                 headless=not a.headed, user_agent_suffix=a.user_agent_suffix)))
        if a.cmd == "browse-login":
            print(f"Session saved to {asyncio.run(bx.login())} (keep it private, like a password).")
            return 0
        try:
            rep = asyncio.run(bx.export())
        except (FileNotFoundError, PermissionError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(rep["summary"], indent=2))
        print(f"Folder: {bx.root}")
        return 1 if rep["summary"]["errors"] else 0
    ex = Exporter(a.url, a.token or os.getenv("FRONTIFY_TOKEN", ""), a.dest, client_name=a.name, concurrency=a.concurrency, progress=Progress())
    if a.cmd == "analyze":
        print(json.dumps(asyncio.run(ex.analyze()), indent=2, default=str))
        return 0
    report = asyncio.run(ex.export())
    print(json.dumps(report.get("summary"), indent=2))
    print(f"Folder: {ex.client_dir}")
    return 1 if (report.get("summary") or {}).get("errors") else 0


if __name__ == "__main__":
    sys.exit(main())
