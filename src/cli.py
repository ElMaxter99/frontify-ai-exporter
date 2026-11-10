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
    a = ap.parse_args(argv)
    if a.cmd in (None, "ui"):
        import uvicorn

        port = getattr(a, "port", 8765)
        if not getattr(a, "no_browser", False):
            threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
        uvicorn.run("src.app:app_factory", factory=True, host=getattr(a, "host", "127.0.0.1"), port=port, log_level="warning")
        return 0
    setup_logging("INFO")
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
