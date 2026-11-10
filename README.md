# Frontify Exporter

Herramienta **local** para exportar todo lo accesible de un Frontify a una carpeta organizada por cliente y lista para alimentar herramientas de IA. Sin base de datos, sin servicios externos, sin cuentas: una página local + el sistema de archivos (JSON y Markdown).

## Un solo comando (sin interfaz, con Docker)

Construye la imagen, exporta, deja todo en `./EXPORTS` y elimina el contenedor al terminar.

```bash
# macOS / Linux (o Git Bash / WSL en Windows)
./export.sh --url https://cliente.frontify.com --token TU_TOKEN --name CLIENTE_01
# o con variables de entorno / .env:  FRONTIFY_URL=... FRONTIFY_TOKEN=... ./export.sh
```
```powershell
# Windows (PowerShell)
.\export.ps1 -Url https://cliente.frontify.com -Token TU_TOKEN -Name CLIENTE_01
```

El token se pasa por entorno al contenedor (no queda en la línea de comandos del contenedor). Código de salida 0 = sin errores; distinto de 0 = hubo fallos (detalle en `EXPORT_REPORT.json`). Opciones: `--concurrency N` / `-Concurrency N`.

## Uso con Docker (recomendado: funciona igual en Windows, macOS y Linux)

```bash
docker compose up --build
```

Abre <http://localhost:8765>, rellena URL y token, pulsa **EXPORTAR TODO**. Los resultados aparecen en la carpeta `./EXPORTS` junto al `docker-compose.yml` (en Linux, con tu usuario como propietario). El puerto solo se publica en `localhost`. Opcional: `FRONTIFY_URL` / `FRONTIFY_TOKEN` en el entorno o en un `.env` para pre-rellenar el formulario.

En Docker el destino es siempre `./EXPORTS` (el selector de carpeta se desactiva) y "Abrir carpeta" te indica la ruta en vez de abrirla. Modo sin interfaz:
`docker compose run --rm -e FRONTIFY_TOKEN=… frontify-exporter python -m src export --url https://cliente.frontify.com --dest /exports --name CLIENTE_01`

> La imagen no se ha podido construir en el entorno de desarrollo (sin daemon de Docker); la lógica específica (destino bloqueado, entrypoint) está probada por separado.

## Uso sin Docker

```bash
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m src                                      # abre http://127.0.0.1:8765
```

1. Introduce la **URL de Frontify** y el **API token** (token personal o access token OAuth2 con acceso de lectura).
2. Elige la **carpeta de destino** (y, opcionalmente, el nombre de la carpeta del cliente; por defecto el subdominio).
3. **ANALIZAR FRONTIFY** (opcional, no escribe nada): cuenta marcas, librerías, carpetas, archivos y páginas, y avisa de zonas no accesibles.
4. **EXPORTAR TODO**: descarga los originales, exporta guidelines y metadatos y genera los documentos para IA.
5. **Abrir carpeta exportada** al terminar. El detalle de lo exportado y de lo fallido está en `EXPORT_REPORT.json`.

También sin interfaz: `FRONTIFY_TOKEN=… python -m src export --url https://cliente.frontify.com --dest EXPORTS --name CLIENTE_01`.

El token solo se mantiene en memoria durante la ejecución (o se lee de `FRONTIFY_TOKEN`); nunca se guarda en disco, no se devuelve al navegador y se redacta de los logs. La UI escucha solo en `127.0.0.1`.

## Carpeta resultante

```
EXPORTS/CLIENTE_01/
├── README_AI.md                  # cómo navegar la exportación (para humanos e IA)
├── EXPORT_REPORT.json            # totales, no exportados + motivo, inaccesibles, duplicados, limitaciones
├── manifest.json                 # todos los ficheros con tamaño y SHA-256
├── export.log
├── 01_BRAND_GUIDELINES/<marca>/  # una página .md por página de guideline (jerarquía de Frontify); _original/ JSON crudo; _media/
├── 02_ASSETS/{LOGOS,IMAGES,PHOTOGRAPHY,VIDEOS,ICONS,ILLUSTRATIONS,AUDIO,OTHER}/<marca>/<librería>/<carpetas…>/<original>
├── 03_DOCUMENTATION/<marca>/…    # PDF/DOCX/… originales + _extracted_text/
├── 04_DESIGN_SYSTEM/             # fuentes descargables + Brand Essentials (JSON)
├── 05_METADATA/<marca>/          # assets.json, folders.json, projects.json, relationships.json, essentials.json
└── 06_AI_KNOWLEDGE/              # BRAND_OVERVIEW, VISUAL_IDENTITY, BRAND_GUIDELINES, ASSET_INDEX, DESIGN_SYSTEM, CONTENT_INDEX (.md)
```

Solo se crean las carpetas/categorías con contenido real. **La relación con Frontify nunca se pierde**: la ruta original (librería/carpeta/ID) de cada archivo está en `05_METADATA/<marca>/assets.json` y en `ASSET_INDEX.md`; los `.md` de guidelines llevan URL e ID en su front-matter. Los documentos de `06_AI_KNOWLEDGE` se generan solo con datos devueltos por la API; lo que falta se indica como *Not available*. Los originales nunca se sustituyen por resúmenes.

## Fiabilidad

* Paginación completa; descargas concurrentes configurables; reintentos con backoff (429/5xx/red, respeta `Retry-After`).
* URLs de descarga firmadas pedidas justo antes de descargar; el token no se envía al CDN; **nunca** se sustituye un original por un preview (si no hay original: `unavailable` en el informe).
* Verificación de tamaño y SHA-256; duplicados detectados (se conservan ambos, se anotan en el informe).
* **Reanudación**: `.export_state.json` en la carpeta del cliente + descargas parciales `.part` con HTTP Range. Volver a pulsar *Exportar* continúa y **no re-descarga lo que no cambió** (huella `modifiedAt`/tamaño/nombre, comprobando el fichero en disco). Si un archivo cambió en Frontify, la versión anterior se conserva en `_previous_versions/`.
* Un fallo individual nunca detiene la exportación. Si un contenedor no se puede recorrer completo (permisos), se informa (`scan_errors`, comparando con `assets.total` de Frontify).

## Limitaciones reales de la API (documentadas en cada informe)

* **Design tokens y componentes**: la API GraphQL oficial no ofrece consultas para ellos (el análisis lo comprueba con introspección cuando está activa). `DESIGN_SYSTEM.md` usa Brand Essentials (colores, tipografías) y las páginas de guidelines de diseño.
* Sin PDF de guidelines (Markdown + JSON); los assets dentro de bloques solo exponen `previewUrl`; el `content` de algunos bloques es nulo (se conservan sus `settings` crudos).
* Logos/fotografía/iconos/ilustraciones se clasifican por nombre/carpeta (no hay flag en la API).
* No se exportan variantes, revisiones, comentarios, licencias ni workflows.
* Detalle de consultas y campos verificados: [docs/FRONTIFY_API.md](docs/FRONTIFY_API.md).

## Estado de verificación (honestidad)

Las consultas se escribieron campo a campo contra la [referencia oficial](https://frontify.github.io/graphql-reference/) y los 20 tests (cliente, exportación completa, reintentos, reanudación, cambios, UI/API) corren contra un **Frontify simulado en proceso** (`tests/fake_frontify.py`). **No se ha probado contra una instancia real de Frontify** (no hay credenciales en este entorno): el criterio "conectar una instancia real" queda pendiente de tu primera ejecución. Hay degradación controlada si una instancia rechaza un campo opcional, y todo error de acceso queda en el informe en lugar de ocultarse. Prueba la UI sin credenciales con `python -m tests.serve_fake`.

```bash
pip install -r requirements-dev.txt && pytest && ruff check src tests && mypy src
```
