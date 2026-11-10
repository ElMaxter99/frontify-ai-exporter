"""Command line interface: ``python -m src.cli {serve,scan,export,search,status}``."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from src.config import RuntimeConfig, Settings
from src.database.db import Database
from src.exporter.pipeline import ExportOptions, Pipeline
from src.utils.events import EventBus
from src.utils.logging import register_secret, setup_logging


def _ctx():
    base = Settings()
    bus = EventBus()
    setup_logging(base.log_level, bus)
    db = Database(base.db_path)
    cfg = RuntimeConfig(base, db.get_settings())
    register_secret(cfg.token)
    register_secret(cfg.openai_key)
    return cfg, db, bus


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="frontify-ai-exporter")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="start the web UI + API")
    s.add_argument("--host", default="0.0.0.0")
    s.add_argument("--port", type=int, default=8000)
    for name in ("scan", "export"):
        p = sub.add_parser(name)
        p.add_argument("--brand", action="append", help="brand id (repeatable)")
        p.add_argument("--category", action="append", help="images|logos|icons|videos|audio|documents|fonts|other")
        if name == "export":
            p.add_argument("--force", action="store_true", help="re-download everything")
            p.add_argument("--no-index", action="store_true")
            p.add_argument("--no-download", action="store_true")
    q = sub.add_parser("search")
    q.add_argument("query")
    q.add_argument("-k", type=int, default=5)
    sub.add_parser("status")
    a = ap.parse_args(argv)

    if a.cmd == "serve":
        import uvicorn

        uvicorn.run("src.api.app:app_factory", factory=True, host=a.host, port=a.port)
        return 0
    cfg, db, bus = _ctx()
    if a.cmd == "status":
        print(json.dumps({"brands": db.scalar("SELECT count(*) FROM brands"), "assets": db.scalar("SELECT count(*) FROM assets"),
                          "chunks": db.scalar("SELECT count(*) FROM chunks")}, indent=2))
        return 0
    if a.cmd == "search":
        from src.ai.embeddings import make_embedder
        from src.ai.indexer import Searcher

        emb = make_embedder(str(cfg.get("embeddings_provider")), str(cfg.get("embeddings_model")), cfg.openai_key)
        for r in Searcher(db, emb).search(a.query, a.k):
            m = r["metadata"]
            print(f"[{r['score']}] {m.get('brand')} · {m.get('title')} · {m.get('source_file')} (id {m.get('frontify_id')})\n{r['text'][:300]}\n")
        return 0
    if not cfg.domain or not cfg.token:
        print("Set FRONTIFY_DOMAIN and FRONTIFY_TOKEN (see .env.example)", file=sys.stderr)
        return 2
    if a.cmd == "scan":
        opts = ExportOptions(brand_ids=set(a.brand or []) or None, download=False, guidelines=False, knowledge=False, index=False, kind="scan")
    else:
        opts = ExportOptions(brand_ids=set(a.brand or []) or None, categories=set(a.category or []) or None, force=a.force,
                             download=not a.no_download, index=not a.no_index)
    report = asyncio.run(Pipeline(cfg, db, bus).run(opts))
    print(json.dumps(report.get("totals"), indent=2))
    print(f"Report: {Path(cfg.export_path / 'global' / 'export_report.json')}")
    return 1 if report.get("failed_assets") else 0


if __name__ == "__main__":
    raise SystemExit(main())
