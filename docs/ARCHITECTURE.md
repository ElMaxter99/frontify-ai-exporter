# Arquitectura

```
src/
├── frontify/   client.py (GraphQL, reintentos, paginación) · queries.py (documentos nombrados)
├── exporter/   scanner.py (descubrimiento + detección de cambios) · pipeline.py (orquestación, informe, manifest) · layout.py
├── assets/     downloader.py (concurrente, Range, SHA-256, duplicados) · classify.py
├── guidelines/ exporter.py (páginas → Markdown/JSON, media) · markdown.py (render puro)
├── metadata/   writer.py (assets/folders/projects/relationships.json, inventario)
├── ai/         extract.py · chunking.py · embeddings.py · vectorstore.py · indexer.py (+Searcher) · knowledge.py
├── database/   db.py (SQLite, esquema) · repo.py (upserts con detección new/modified/unchanged/deleted)
├── sync/       history.py (histórico y cambios)
├── workers/    jobs.py (un job a la vez, progreso, cancelación, persistencia)
├── api/        app.py (FastAPI + SSE + estáticos del frontend)
├── utils/      logging (redacción de secretos) · events (bus de eventos) · files
└── cli.py
frontend/       React + TypeScript + Tailwind (Dashboard, Explorer, Export, Search, Settings)
```

## Flujo de un export

`scan` → `download` → `guidelines` → `knowledge` + `index` → `metadata` → `manifest/informe`.

1. **Scan**: marcas → librerías/workspaces → recorrido BFS de carpetas (concurrente) → assets (con `upsert_asset`: `new/modified/unchanged/restored`). Cada contenedor guarda `expected_assets` y `scan_complete`; solo si está completo se marcan como `deleted` los no vistos. Después: colecciones, relacionados, essentials y estructura de guidelines.
2. **Download**: selección de pendientes/fallidos/cambiados; URLs firmadas frescas por lotes de 25; `.part` + Range; verificación de tamaño y SHA‑256; fallos aislados por asset.
3. **Guidelines**: contenido de cada página (paginación anidada de secciones/elementos), hash del contenido → `new/modified/unchanged`.
4. **Knowledge/Index**: ver [AI_KNOWLEDGE.md](AI_KNOWLEDGE.md).
5. **Metadata/Report**: JSON por marca, `global/inventory.json`, `global/export_report.json` (totales, cambios, fallidos, no disponibles, errores parciales), `manifest.json`.

## Persistencia (SQLite)

`brands, containers, folders, assets, guideline_pages, collections, essentials, relationships, sync_runs, changes, jobs, settings, chunks, chunks_fts`. Los ajustes editables desde la UI se guardan en `settings` (nunca credenciales).

## Concurrencia

`asyncio` + `httpx`. `API_CONCURRENCY` limita peticiones GraphQL simultáneas (semáforo en el cliente); `DOWNLOAD_CONCURRENCY` limita descargas. El indexado/embeddings corren en un hilo (`asyncio.to_thread`).

## Tiempo real

`EventBus` (logs + progreso + jobs) → `GET /api/events` (Server‑Sent Events) → la UI.
