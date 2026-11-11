<div align="center">

<img src="docs/assets/logo.svg" alt="Frontify Exporter" width="720">

**Exporta todo lo accesible de un Frontify a una carpeta local impecable, lista para alimentar a tu IA.**

[🇬🇧 English](README.md) · 🇪🇸 **Español**

[![CI](https://github.com/ElMaxter99/frontify-ai-exporter/actions/workflows/ci.yml/badge.svg)](https://github.com/ElMaxter99/frontify-ai-exporter/actions/workflows/ci.yml)
[![CodeQL](https://github.com/ElMaxter99/frontify-ai-exporter/actions/workflows/codeql.yml/badge.svg)](https://github.com/ElMaxter99/frontify-ai-exporter/actions/workflows/codeql.yml)
[![Licencia: Apache-2.0](https://img.shields.io/badge/licencia-Apache--2.0-d4af37.svg)](LICENSE)
![Sin relación con Frontify](https://img.shields.io/badge/Frontify-sin%20afiliaci%C3%B3n-8a8fa8)
![Python](https://img.shields.io/badge/Python-3.11%E2%80%933.13-3776AB?logo=python&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-listo-2496ED?logo=docker&logoColor=white)
![Dependabot](https://img.shields.io/badge/Dependabot-activo-025E8C?logo=dependabot&logoColor=white)
![Gratis](https://img.shields.io/badge/precio-gratis-12805c)

[Inicio rápido](#-inicio-rápido) · [Resultado](#-la-carpeta-resultante) · [Para IA](#-pensado-para-ia) · [Fiabilidad](#-fiabilidad) · [Límites](#️-límites-reales-de-la-api) · [Proyecto](#-sobre-este-proyecto)

</div>

---

> ⚖️ **Proyecto comunitario independiente: no está afiliado, respaldado ni patrocinado por Frontify.** Lee el [aviso legal](DISCLAIMER.md).

> 🪧 **La verdad por delante:** son dos scripts que hice para exportar el Frontify de un cliente a una carpeta. Quizá a ti también te sirvan, así que aquí quedan: gratis, con licencia Apache 2.0 y sin promesas de soporte. Úsalos, haz un fork, mejóralos.

## 🎯 ¿Para qué sirve?

Si tú —o tu cliente— tienes un portal de marca en Frontify bien definido, esto genera el **contexto que una IA necesita para respetar la marca**: colores, tipografías, reglas de logo, tono de voz, guidelines y un índice de todos los recursos, todo sacado del propio Frontify (nunca inventado). Pasa la carpeta a ChatGPT, Claude, Cursor, Codex o a tu propio RAG y seguirá los estilos y normas. Paso a paso: [`docs/USE_WITH_AI.md`](docs/USE_WITH_AI.md) · dudas: [`docs/FAQ.md`](docs/FAQ.md).

## ✨ ¿Qué hace?

Introduces la **URL** y un **token de API** y pulsas **EXPORTAR**. La herramienta:

| | |
|---|---|
| 🔎 **Analiza** | marcas, workspaces, librerías, colecciones, carpetas, guidelines y sus páginas |
| 📥 **Descarga** | los **archivos originales** (nunca previews): logos, imágenes, vídeos, PDFs, fuentes, documentos… |
| 📝 **Exporta** | guidelines a **Markdown** (con su jerarquía), textos, descripciones, etiquetas y **todos los metadatos** |
| 🔗 **Conserva** | la ubicación original de cada archivo en Frontify y las relaciones entre recursos |
| 🧠 **Genera** | documentos de contexto para IA escritos **solo con datos reales** (sin inventar) |
| 📊 **Informa** | de lo exportado, lo omitido y lo que falló, con el motivo de cada caso |

100 % local: **sin SaaS, sin cuentas, sin base de datos, sin servicios externos.** Solo sistema de archivos, JSON y Markdown.

## ⚡ Inicio rápido

Necesitas la URL de Frontify (`https://cliente.frontify.com`) y un **token de API** con permiso de lectura sobre el contenido que quieras exportar.

<details open>
<summary><b>🐳 Docker — un comando, sin interfaz</b> (macOS · Linux · Windows)</summary>

Construye, exporta a `./EXPORTS` y elimina el contenedor al terminar.

```bash
# macOS / Linux (o Git Bash / WSL en Windows)
./export.sh --url https://cliente.frontify.com --token TU_TOKEN --name CLIENTE_01
```
```powershell
# Windows (PowerShell)
.\export.ps1 -Url https://cliente.frontify.com -Token TU_TOKEN -Name CLIENTE_01
```

Token y URL también por variables `FRONTIFY_TOKEN` / `FRONTIFY_URL` o un `.env`. `--concurrency N` fija las descargas en paralelo (4 por defecto). Código de salida `0` = sin errores. Si Windows bloquea el script: `powershell -ExecutionPolicy Bypass -File .\export.ps1 …`

</details>

<details>
<summary><b>🖥 Docker — con interfaz web</b></summary>

```bash
docker compose up --build
```
Abre **http://localhost:8765** → URL + token → **ANALIZAR FRONTIFY** → **EXPORTAR TODO**. Resultados en `./EXPORTS`. El puerto solo escucha en `localhost`.

</details>

<details>
<summary><b>🐍 Python — sin Docker</b></summary>

```bash
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m src                                      # interfaz en http://127.0.0.1:8765
# sin interfaz:
FRONTIFY_TOKEN=… python -m src export --url https://cliente.frontify.com --dest EXPORTS --name CLIENTE_01
```

</details>

## 🗂 La carpeta resultante

Una carpeta por cliente, organizada automáticamente (solo se crean las categorías con contenido):

```
EXPORTS/CLIENTE_01/
├── 📘 README_AI.md              ← por dónde empezar (humanos e IA)
├── 📊 EXPORT_REPORT.json        ← totales, errores y motivos, recursos inaccesibles
├── 🔐 manifest.json             ← cada fichero con tamaño y SHA-256
├── 01_BRAND_GUIDELINES/<marca>/ ← un .md por página de guideline + _original/ + _media/
├── 02_ASSETS/
│   ├── LOGOS/ IMAGES/ PHOTOGRAPHY/ VIDEOS/ ICONS/ ILLUSTRATIONS/ AUDIO/ OTHER/
│   └── …/<marca>/<librería>/<carpetas originales…>/<archivo original>
├── 03_DOCUMENTATION/            ← PDFs, DOCX… + _extracted_text/
├── 04_DESIGN_SYSTEM/            ← fuentes descargables + Brand Essentials (JSON)
├── 05_METADATA/<marca>/         ← assets · folders · projects · relationships · essentials (JSON)
└── 06_AI_KNOWLEDGE/             ← los documentos para IA 👇
```

🔗 **Nunca se pierde la relación con Frontify:** la ruta original (librería / carpeta / ID) de cada archivo está en `05_METADATA/<marca>/assets.json` y en `ASSET_INDEX.md`.

## 🧠 Pensado para IA

`06_AI_KNOWLEDGE/` se genera a partir de datos reales de la API:

| Documento | Contenido |
|---|---|
| `BRAND_OVERVIEW.md` | Resumen de la marca: librerías, colecciones, guidelines, totales |
| `VISUAL_IDENTITY.md` | Logotipos, **colores** (HEX/Pantone) y **tipografías** |
| `BRAND_GUIDELINES.md` | Todas las guidelines en Markdown, en el orden de Frontify |
| `ASSET_INDEX.md` | Índice de recursos: nombre, descripción, etiquetas, ruta al original |
| `DESIGN_SYSTEM.md` | Colores, tipografías y documentación de diseño disponible |
| `CONTENT_INDEX.md` | Índice de todo lo exportado, con el estado de cada documento |

**Reglas de oro:** los originales jamás se sustituyen por resúmenes · si un dato no existe, el documento dice *“Not available”* en vez de inventarlo · todo lleva su fuente (URL / ID de Frontify).

## 🌐 Modo navegador (sin token de API)

Si solo tienes un **login** del portal del cliente, léelo como lo ves en el navegador. Una página cada vez, con pausa entre páginas, User-Agent honesto, `robots.txt` respetado, hosts de tracking bloqueados y cada petición contada en `EXPORT_REPORT.json`.

```bash
pip install -r requirements-browser.txt && python -m playwright install chromium
python -m src browse-login --url https://cliente.frontify.com     # inicias sesión una vez en una ventana visible → guarda .browser_state/ (privado, como una contraseña)
python -m src browse --url https://cliente.frontify.com --name CLIENTE_01 --delay 3 [--click-downloads] [--no-files]
```

Misma carpeta de salida (`01_BRAND_GUIDELINES`, `02_ASSETS`, `06_AI_KNOWLEDGE`…). Límites: sin metadatos estructurados (etiquetas, campos personalizados), colores/fuentes heurísticos y los archivos originales solo se guardan donde el portal ofrezca descarga a tu usuario. Aún no probado contra un portal real (sí contra uno local simulado). Avisa al cliente antes de ejecutarlo.

## 🛡 Fiabilidad

- ♻️ **Reanudable** — relanza y continúa; las descargas parciales se retoman (HTTP Range).
- 🧬 **Incremental** — no vuelve a bajar lo que no cambió; si un archivo cambió, la versión anterior se conserva en `_previous_versions/`.
- ✅ **Integridad** — tamaño + SHA-256 por archivo; **duplicados** detectados (se conservan y se anotan).
- 🚦 **Resiliente** — paginación completa, reintentos con backoff (429/5xx/red), concurrencia configurable. **Un fallo nunca detiene el resto.**
- 🔒 **Seguro** — el token vive en memoria o en tu entorno, se oculta de los logs y nunca va al CDN. La interfaz solo escucha en `127.0.0.1`. Se respetan los permisos de Frontify.

## ⚠️ Límites reales de la API

También se listan en cada `EXPORT_REPORT.json`:

- 🎨 **Design tokens y componentes** — la API GraphQL pública de Frontify no los ofrece. `DESIGN_SYSTEM.md` usa Brand Essentials (colores, tipografías) y páginas de guidelines.
- 📄 **PDF de guidelines** — no existe en la API → Markdown + JSON original (los PDFs que sean *assets* sí se descargan).
- 🖼 Los assets incrustados en bloques de guidelines solo exponen una previsualización (sin ID).
- 🏷 Logos / fotografía / iconos / ilustraciones se clasifican por nombre y carpeta (no hay campo en la API).
- 🚫 No se exportan variantes, revisiones, comentarios, licencias ni workflows.

> 🧪 **Estado de verificación:** las consultas siguen la [referencia oficial](https://frontify.github.io/graphql-reference/) y los tests corren contra un Frontify **simulado**. **Todavía no se ha ejecutado contra una instancia real**: tu primera ejecución es la prueba definitiva; los fallos se reportan, nunca se ocultan. Detalle: [`docs/FRONTIFY_API.md`](docs/FRONTIFY_API.md).

## 📚 Sobre este proyecto

<details>
<summary><b>Cómo se hizo</b></summary>

Construido en una sesión de programación en pareja con un asistente de IA (Claude Code) y luego simplificado a lo realmente necesario. Historia completa: [`docs/HOW_IT_WAS_MADE.md`](docs/HOW_IT_WAS_MADE.md) · [`docs/USE_WITH_AI.md`](docs/USE_WITH_AI.md) · [`docs/FAQ.md`](docs/FAQ.md) · arquitectura: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

</details>

<details>
<summary><b>Uso gratuito · licencia · garantía</b></summary>

Publicado bajo [licencia Apache 2.0](LICENSE) (ver [`NOTICE`](NOTICE) y [`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md)): úsalo, cópialo, modifícalo y redistribúyelo, incluso comercialmente, conservando los avisos. Frente a MIT añade una cesión explícita de patentes y deja claro que no concede derechos de marca, algo adecuado para una herramienta que menciona el producto de otra empresa. **Se ofrece “tal cual”, sin garantía de ningún tipo**, y sin promesa de soporte ni mantenimiento más allá de lo que haga la automatización. Eres responsable del uso que hagas.

</details>

<details>
<summary><b>Legal y uso responsable</b></summary>

- **No está afiliado, respaldado ni patrocinado por Frontify.** “Frontify” es una marca de su titular, usada aquí solo para describir la compatibilidad.
- Úsalo **únicamente en cuentas de Frontify propias o con autorización expresa para exportarlas**. Solo accede a lo que tu token permite y no evita ningún permiso ni protección de descarga.
- El contenido exportado (recursos de marca, guidelines, fuentes) pertenece a sus titulares: revisa contratos con clientes, licencias y datos personales antes de compartirlo o enviarlo a servicios de IA de terceros.
- Mantén los tokens en secreto y revócalos cuando ya no los necesites.
- Texto completo: [`DISCLAIMER.md`](DISCLAIMER.md) (ES/EN).

</details>

<details>
<summary><b>Contribuir · seguridad · automatización</b></summary>

- 🤝 Issues y PRs bienvenidos → [`CONTRIBUTING.md`](CONTRIBUTING.md) · [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)
- 🔐 Vulnerabilidades → [`SECURITY.md`](SECURITY.md) (reporte privado)
- 🤖 Se mantiene solo: **CI** (lint + tipos + tests en Python 3.11–3.13 + build de Docker), **CodeQL**, **Dependabot** (pip, Actions, Docker; auto-merge de minor/patch con CI en verde), **release-please** (changelog y versiones desde Conventional Commits) y limpieza de issues inactivos.
- 🧪 Desarrollo: `pip install -r requirements-dev.txt && pytest && ruff check src tests && mypy src` · `python -m tests.serve_fake` levanta la UI contra un Frontify simulado (token `test-token-123456`).

</details>

<div align="center"><sub>Hecho para que cualquier IA entienda tu marca sin perder contexto. ✦ <a href="LICENSE">Apache-2.0</a> · <a href="DISCLAIMER.md">Aviso legal</a></sub></div>
