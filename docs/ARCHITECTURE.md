# Architecture

```
src/
├── frontify/client.py     all GraphQL traffic: retries, backoff, 429/Retry-After, pagination, partial errors
├── frontify/queries.py    named GraphQL documents (fields checked against the official reference)
├── exporter/scan.py       discovery (brands → libraries/workspaces → folders → assets, collections, guidelines, essentials), in memory
├── exporter/download.py   concurrent, resumable (.part + Range), SHA-256, duplicates, keeps previous versions
├── exporter/guidelines.py guideline pages → Markdown + raw JSON (+ embedded previews)
├── exporter/docs.py       05_METADATA and 06_AI_KNOWLEDGE + README_AI.md (real data only)
├── exporter/run.py        orchestration (analyze / export), report + manifest
├── exporter/layout.py     01_…06_ folder layout and the JSON resume state
├── exporter/progress.py   live counters/log tail for the UI
├── app.py  cli.py         local FastAPI UI (127.0.0.1) and CLI
└── ui/index.html          single static page, no build step
```

Flow: `scan → download → guidelines → extract document text → metadata + AI docs → report + manifest`.

Design rules: no database (state is `.export_state.json` in the client folder), no mandatory external services, originals are never replaced, anything missing is reported rather than invented.
