# Frontify AI Exporter

Conecta con tu instancia de **Frontify** (API GraphQL oficial), descubre todo lo que tu token puede ver, **descarga los archivos originales**, exporta las **brand guidelines a Markdown**, conserva **todos los metadatos** y genera una **base de conocimiento lista para IA** (ChatGPT, Claude, Cursor, Codex, agentes) con chunks con procedencia, búsqueda léxica/semántica y soporte para ChromaDB, FAISS, Qdrant y embeddings de OpenAI o locales.

Principio rector: **no perder información** y **nunca sustituir un original por una versión procesada**. Todo lo derivado (Markdown, texto extraído, chunks) vive en `knowledge/` o `guidelines/markdown/` y referencia el original.

## Arranque rápido

```bash
cp .env.example .env        # rellena FRONTIFY_DOMAIN y FRONTIFY_TOKEN
docker compose up --build
```

Abre <http://localhost:8000> → **Dashboard** (estado de conexión) → **Export** → *Scan Frontify* → *Export*.
El resultado queda en `./exports` (volumen del host).

> Nota de verificación: la imagen Docker no pudo construirse en el entorno de desarrollo (sin daemon de Docker). El backend, el frontend y el arranque con `python -m src.cli serve` sí se ejecutaron y probaron; ver [Estado y limitaciones](#estado-y-limitaciones).

### Sin Docker

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
(cd frontend && npm install && npm run build)     # UI compilada en frontend/dist
python -m src.cli serve --port 8000
```

Desarrollo de la UI con recarga: `python -m src.cli serve` + `cd frontend && npm run dev` (proxy a :8000).

### CLI

```bash
python -m src.cli scan                       # solo descubrimiento
python -m src.cli export                     # escaneo + descarga + guidelines + conocimiento + índice (incremental)
python -m src.cli export --force             # re-descarga todo
python -m src.cli export --brand <id> --category documents --category logos
python -m src.cli search "espacio de seguridad del logo" -k 5
```

## Credenciales y seguridad

* El token **solo** viaja por variable de entorno (`FRONTIFY_TOKEN`) o, opcionalmente, se teclea en *Settings* y vive **solo en memoria del servidor** (no se persiste, no se devuelve al navegador, no hay token en el frontend).
* Los logs redactan el token, cabeceras `Bearer` y parámetros de firma de URLs. Las `downloadUrl` firmadas se piden justo antes de descargar, se usan con un cliente HTTP **sin** cabecera de autorización (el token no viaja a CDNs) y **no se guardan** en los JSON exportados.
* Solo se accede a lo que el token autoriza; un asset protegido contra descarga se marca `unavailable` y no se sustituye por un preview.

## Estructura de la exportación

```
exports/
├── manifest.json                     # versión, totales, hashes de los ficheros de conocimiento
├── global/{inventory.json, export_report.json}
└── brands/<marca>/
    ├── assets/{images,logos,icons,videos,audio,documents,fonts,other}/<librería>/<carpetas…>/<original>
    ├── guidelines/
    │   ├── markdown/   # una página .md por página de guideline, jerarquía de navegación y front-matter con procedencia
    │   ├── original/   # JSON crudo de la API, navigation.json, media/ (previews embebidos)
    │   └── pdf/        # README: la API no expone PDF de guidelines (ver limitaciones)
    ├── libraries/      # (reservado; las librerías son el primer nivel bajo assets/<categoría>/)
    ├── metadata/{assets,folders,projects,relationships,essentials}.json
    └── knowledge/{brand_context,brand_guidelines,visual_identity,typography,colors,tone_of_voice,complete_index}.md
                  chunks.jsonl, extracted_text/
```

La estructura se genera dinámicamente según las marcas/librerías/carpetas encontradas. Los ficheros de `knowledge/` se construyen solo con datos reales; si Frontify no tiene datos de un tema, el fichero lo dice explícitamente.

## Sincronización incremental

Cada escaneo compara con la base SQLite (`data/exporter.sqlite3`) y registra en el histórico (`sync_runs`/`changes`) assets **nuevos, modificados, restaurados y eliminados/inaccesibles**, carpetas y páginas de guidelines nuevas/cambiadas y cambios de contenido de documentación (hash del contenido).

* Un asset **no se vuelve a descargar** salvo que cambie `modifiedAt`/`fileCreatedAt`/tamaño/nombre de fichero (los cambios solo de metadatos actualizan metadatos sin re-descargar). Cada descarga se verifica con SHA-256 y tamaño; se detectan duplicados por hash (opcional: hard links).
* Un asset solo se declara eliminado si el contenedor se recorrió **completo** y su total coincide con `assets.total` de Frontify; ante un escaneo incompleto no se borra nada.
* **Reanudación**: el estado es por asset en SQLite y las descargas parciales (`.part`) se retoman con HTTP Range. Relanzar *Export* continúa donde se quedó. Un fallo individual nunca detiene la exportación y aparece en el informe final.

## Preparación para IA

Ver [docs/AI_KNOWLEDGE.md](docs/AI_KNOWLEDGE.md). Resumen: chunking por encabezados con migas de pan, procedencia en cada chunk (marca, fichero origen, ID Frontify, URL, categoría, carpeta, fecha de extracción), extracción de texto de PDF/DOCX/TXT/MD/HTML/CSV/JSON/SVG, OCR opcional, metadatos de imagen (EXIF), índice léxico FTS5 siempre disponible, embeddings opcionales (OpenAI/local) y vector store SQLite/Chroma/FAISS/Qdrant.

## Tests

```bash
pip install -r requirements-dev.txt
pytest            # 22 tests: cliente (reintentos, 429, auth, errores parciales), unidades, integración end-to-end, API
ruff check src tests && mypy src
cd frontend && npm run build   # tsc + vite
```

Los tests de integración usan un **Frontify simulado en proceso** (`tests/fake_frontify.py`, `httpx.MockTransport`) cuyo esquema sigue la referencia oficial. `python -m tests.serve_fake` levanta la app real contra ese simulador (sin red ni credenciales) para probar la UI.

## Estado y limitaciones

**Importante — no validado contra una instancia real de Frontify**: este entorno no dispone de credenciales de Frontify. Las consultas se construyeron campo a campo contra la [referencia GraphQL oficial](https://frontify.github.io/graphql-reference/) y se probaron contra el simulador, pero conviene hacer una primera ejecución real. Para ello hay degradación controlada: si la instancia rechaza un campo opcional del asset, el escáner baja a una consulta mínima y lo registra; las queries de guidelines/essentials (Beta) fallan de forma aislada y quedan reflejadas en el informe sin detener el resto.

Limitaciones conocidas (detalle en [docs/FRONTIFY_API.md](docs/FRONTIFY_API.md)):

* La API GraphQL no expone un **PDF de guidelines** → se exporta Markdown + JSON original; los PDF que existan como assets sí se descargan.
* Los assets referenciados dentro de bloques de guidelines solo exponen `previewUrl` (sin ID): se guardan esos previews y los originales se obtienen del recorrido de librerías.
* `content` de un bloque puede ser `null` para algunos tipos: entonces se conservan sus `settings` crudos en el Markdown y el JSON.
* El tipo `Asset` no tiene permalink: la procedencia usa ID de Frontify + dominio (y URL de la guideline/página cuando existe).
* Logos/iconos se clasifican por heurística de nombre/carpeta (no hay flag en la API). Variantes de assets, revisiones, comentarios, licencias y workflows **no** se exportan todavía.
* Autenticación: se usa `Authorization: Bearer` con un token personal o un access token OAuth 2.0 obtenido fuera de la app; el flujo interactivo de OAuth no está implementado.
* Límites de peticiones: se respetan 429/`Retry-After` con backoff exponencial y concurrencia configurable; los umbrales exactos de Frontify no figuran en la referencia consultada.

Más documentación: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
