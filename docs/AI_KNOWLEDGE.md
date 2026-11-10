# Base de conocimiento para IA

## Qué se genera por marca (`brands/<marca>/knowledge/`)

| Fichero | Contenido |
|---|---|
| `brand_context.md` | Resumen factual: IDs, librerías/workspaces, guidelines, categorías y totales |
| `brand_guidelines.md` | Todas las páginas de guidelines concatenadas en el orden de navegación |
| `visual_identity.md`, `typography.md`, `colors.md`, `tone_of_voice.md` | Páginas cuyo **ruta de navegación** coincide con palabras clave (ES/EN, listadas en cada fichero) + datos de *Brand Essentials* (paletas con HEX/Pantone, familias tipográficas). Si no hay datos, el fichero lo indica |
| `complete_index.md` | Árbol de páginas y assets con rutas locales e IDs |
| `chunks.jsonl` | Un chunk por línea, listo para cualquier vector DB |
| `extracted_text/` | Texto extraído de PDF/DOCX/TXT/MD/HTML/CSV/JSON/SVG (y OCR si se activa) |

## Procedencia de cada chunk

`brand, brand_id, frontify_domain, kind (guideline_page | asset_metadata | asset_text | knowledge), source_file, frontify_id, source_url, category, folder, title, extracted_at, heading_path, chunk_index, chunk_count, text_hash` (+ `sha256`, `extension`, `extraction` en assets).

## Chunking

Por secciones de encabezado Markdown, con migas (`Marca > Sección > Subsección`) antepuestas al texto, tamaño ~1800 caracteres y solapamiento 200 en textos largos. Cada asset genera además una "ficha" con descripción, texto alternativo, etiquetas, campos personalizados, dimensiones y EXIF, de modo que incluso imágenes sin texto son recuperables por sus metadatos de Frontify.

## Embeddings y búsqueda

* `EMBEDDINGS_PROVIDER=none` (por defecto): búsqueda léxica BM25 con SQLite FTS5.
* `openai`: `/v1/embeddings` (`OPENAI_API_KEY`, modelo por defecto `text-embedding-3-small`).
* `local`: `sentence-transformers` (`pip install sentence-transformers`).
* Con embeddings activos la búsqueda es **híbrida** (RRF entre vectorial y léxica). Los vectores se reutilizan entre exportaciones si el texto no cambió.

Vector stores (`VECTOR_STORE`): `sqlite` (integrado, coseno con numpy), `chroma`, `faiss`, `qdrant` (instalar el paquete opcional correspondiente; ver `requirements-optional.txt` o `EXTRAS` en el Dockerfile). Si el store elegido no está disponible se usa SQLite y se informa en el informe.

## Usar la carpeta con herramientas de IA

* Cursor/Codex/Claude Code: apunta al directorio `exports/brands/<marca>/knowledge/` (o referencia `brand_guidelines.md`).
* ChatGPT/Claude proyectos: sube los `.md` de `knowledge/` y `guidelines/markdown/`.
* RAG propio: importa `chunks.jsonl` (los metadatos ya traen la procedencia) a tu vector DB, o usa `GET /api/search?q=…`.

Los originales **nunca** se modifican: todo el contenido derivado está separado y referencia al original por ruta e ID.
