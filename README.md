<div align="center">

<img src="docs/assets/logo.svg" alt="Frontify Exporter" width="720">

**Export everything accessible in a Frontify to a clean local folder, ready to feed your AI.**

🇬🇧 **English** · [🇪🇸 Español](README.es.md)

[![CI](https://github.com/ElMaxter99/frontify-ai-exporter/actions/workflows/ci.yml/badge.svg)](https://github.com/ElMaxter99/frontify-ai-exporter/actions/workflows/ci.yml)
[![CodeQL](https://github.com/ElMaxter99/frontify-ai-exporter/actions/workflows/codeql.yml/badge.svg)](https://github.com/ElMaxter99/frontify-ai-exporter/actions/workflows/codeql.yml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-d4af37.svg)](LICENSE)
![Not affiliated with Frontify](https://img.shields.io/badge/Frontify-unaffiliated-8a8fa8)
![Python](https://img.shields.io/badge/Python-3.11%E2%80%933.13-3776AB?logo=python&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)
![Dependabot](https://img.shields.io/badge/Dependabot-enabled-025E8C?logo=dependabot&logoColor=white)
![Free](https://img.shields.io/badge/price-free-12805c)

[Quick start](#-quick-start) · [Output](#-the-output-folder) · [For AI](#-built-for-ai) · [Reliability](#-reliability) · [Limits](#️-real-api-limits) · [Project](#-about-this-project)

</div>

---

> ⚖️ **Independent community project — not affiliated with, endorsed by or sponsored by Frontify.** See the [disclaimer](DISCLAIMER.md).

> 🪧 **The honest pitch:** two small scripts I wrote to export a client's Frontify to a folder. They might be useful to you too, so here they are — free, Apache-2.0 licensed, no support promises. Use them, fork them, improve them.

## 🎯 What is it for?

If you — or your client — have a well-defined Frontify brand portal, this generates the **context an AI needs to respect the brand**: colors, typography, logo rules, tone of voice, guidelines and an index of every asset, all taken from Frontify itself (never invented). Drop the folder into ChatGPT, Claude, Cursor, Codex or your own RAG and it will follow the styles and rules. Step-by-step: [`docs/USE_WITH_AI.md`](docs/USE_WITH_AI.md) · questions: [`docs/FAQ.md`](docs/FAQ.md).

## ✨ What it does

Enter the **URL** and an **API token**, hit **EXPORT**. It:

| | |
|---|---|
| 🔎 **Analyzes** | brands, workspaces, libraries, collections, folders, guidelines and their pages |
| 📥 **Downloads** | the **original files** (never previews): logos, images, videos, PDFs, fonts, documents… |
| 📝 **Exports** | guidelines to **Markdown** (hierarchy kept), texts, descriptions, tags and **all metadata** |
| 🔗 **Keeps** | each file's original location in Frontify and the relations between resources |
| 🧠 **Generates** | AI context documents written **only from real data** (nothing invented) |
| 📊 **Reports** | what was exported, skipped or failed — with the reason for each |

100 % local: **no SaaS, no accounts, no database, no external services.** Just the file system, JSON and Markdown.

## ⚡ Quick start

You need a Frontify URL (`https://client.frontify.com`) and an **API token** with read access to the content you want.

<details open>
<summary><b>🐳 Docker — one command, no UI</b> (macOS · Linux · Windows)</summary>

Builds, exports into `./EXPORTS`, and removes the container when done.

```bash
# macOS / Linux (or Git Bash / WSL on Windows)
./export.sh --url https://client.frontify.com --token YOUR_TOKEN --name CLIENT_01
```
```powershell
# Windows (PowerShell)
.\export.ps1 -Url https://client.frontify.com -Token YOUR_TOKEN -Name CLIENT_01
```

Token/URL can also come from `FRONTIFY_TOKEN` / `FRONTIFY_URL` env vars or a `.env` file. `--concurrency N` sets parallel downloads (default 4). Exit code `0` = no errors. If Windows blocks the script: `powershell -ExecutionPolicy Bypass -File .\export.ps1 …`

</details>

<details>
<summary><b>🖥 Docker — with the web UI</b></summary>

```bash
docker compose up --build
```
Open **http://localhost:8765** → URL + token → **ANALYZE** → **EXPORT ALL**. Results land in `./EXPORTS`. The port is bound to `localhost` only.

</details>

<details>
<summary><b>🐍 Python — no Docker</b></summary>

```bash
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m src                                      # UI at http://127.0.0.1:8765
# headless:
FRONTIFY_TOKEN=… python -m src export --url https://client.frontify.com --dest EXPORTS --name CLIENT_01
```

</details>

## 🗂 The output folder

One folder per client, organised automatically (only categories with content are created):

```
EXPORTS/CLIENT_01/
├── 📘 README_AI.md              ← where to start (humans & AI)
├── 📊 EXPORT_REPORT.json        ← totals, errors + reasons, inaccessible resources
├── 🔐 manifest.json             ← every file with size and SHA-256
├── 01_BRAND_GUIDELINES/<brand>/ ← one .md per guideline page + _original/ + _media/
├── 02_ASSETS/
│   ├── LOGOS/ IMAGES/ PHOTOGRAPHY/ VIDEOS/ ICONS/ ILLUSTRATIONS/ AUDIO/ OTHER/
│   └── …/<brand>/<library>/<original folders…>/<original file>
├── 03_DOCUMENTATION/            ← PDFs, DOCX… + _extracted_text/
├── 04_DESIGN_SYSTEM/            ← downloadable fonts + Brand Essentials (JSON)
├── 05_METADATA/<brand>/         ← assets · folders · projects · relationships · essentials (JSON)
└── 06_AI_KNOWLEDGE/             ← the AI documents 👇
```

🔗 **The link to Frontify is never lost:** each file's original path (library / folder / ID) is in `05_METADATA/<brand>/assets.json` and `ASSET_INDEX.md`.

## 🧠 Built for AI

`06_AI_KNOWLEDGE/` is generated from real API data:

| Document | Content |
|---|---|
| `BRAND_OVERVIEW.md` | Brand summary: libraries, collections, guidelines, totals |
| `VISUAL_IDENTITY.md` | Logos, **colors** (HEX/Pantone) and **typography** |
| `BRAND_GUIDELINES.md` | All guidelines in Markdown, in Frontify order |
| `ASSET_INDEX.md` | Resource index: name, description, tags, path to the original |
| `DESIGN_SYSTEM.md` | Colors, fonts and available design documentation |
| `CONTENT_INDEX.md` | Index of everything exported, with each document's status |

**Golden rules:** originals are never replaced by summaries · missing data reads *"Not available"* instead of being invented · everything carries its source (Frontify URL / ID).

## 🌐 Browser mode (no API token)

If you only have a **login** to the client's portal, read it the way you see it in a browser. One page at a time, with a pause between pages, an honest User-Agent, `robots.txt` respected, tracker hosts blocked, and every request counted in `EXPORT_REPORT.json`.

```bash
pip install -r requirements-browser.txt && python -m playwright install chromium
python -m src browse-login --url https://client.frontify.com     # log in once in a visible window → saves .browser_state/ (private, like a password)
python -m src browse --url https://client.frontify.com --name CLIENT_01 --delay 3 [--click-downloads] [--no-files]
```

Same output folder (`01_BRAND_GUIDELINES`, `02_ASSETS`, `06_AI_KNOWLEDGE`…). Limits: no structured metadata (tags, custom fields), colours/fonts are heuristics, and original files are saved only where the portal offers a download for your user. Not yet run against a real portal (tested against a local simulated one). Tell the client before running it.

## 🛡 Reliability

- ♻️ **Resumable** — re-run and it continues; partial downloads resume (HTTP Range).
- 🧬 **Incremental** — unchanged files aren't downloaded again; if a file changed, the old version is kept in `_previous_versions/`.
- ✅ **Integrity** — size + SHA-256 per file; **duplicates** detected (kept and reported).
- 🚦 **Resilient** — full pagination, retries with backoff (429/5xx/network), configurable concurrency. **One failure never stops the rest.**
- 🔒 **Safe** — the token lives in memory or your environment, is redacted from logs and never sent to the CDN. The UI listens on `127.0.0.1` only. Frontify permissions are respected.

## ⚠️ Real API limits

Also listed in every `EXPORT_REPORT.json`:

- 🎨 **Design tokens & components** — not offered by Frontify's public GraphQL API. `DESIGN_SYSTEM.md` uses Brand Essentials (colors, fonts) and guideline pages.
- 📄 **Guideline PDF** — doesn't exist in the API → Markdown + original JSON (PDFs that are *assets* are downloaded).
- 🖼 Assets embedded in guideline blocks only expose a preview (no ID).
- 🏷 Logos / photography / icons / illustrations are classified by name and folder (no API flag).
- 🚫 Variants, revisions, comments, licenses and workflows are not exported.

> 🧪 **Verification status:** queries follow the [official reference](https://frontify.github.io/graphql-reference/) and the test suite runs against a **simulated** Frontify. It has **not yet been run against a real instance** — your first run is the real test; failures are reported, never hidden. Details: [`docs/FRONTIFY_API.md`](docs/FRONTIFY_API.md).

## 📚 About this project

<details>
<summary><b>How it was made</b></summary>

Built in a pair-programming session with an AI assistant (Claude Code), then simplified to what's really needed. Full story: [`docs/HOW_IT_WAS_MADE.md`](docs/HOW_IT_WAS_MADE.md) · [`docs/USE_WITH_AI.md`](docs/USE_WITH_AI.md) · [`docs/FAQ.md`](docs/FAQ.md) · architecture: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

</details>

<details>
<summary><b>Free to use · license · warranty</b></summary>

Released under the [Apache License 2.0](LICENSE) (see [`NOTICE`](NOTICE) and [`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md)): use it, copy it, modify it and redistribute it, even commercially, keeping the notices. Compared with MIT it adds an explicit patent grant and states that no trademark rights are granted — a good fit for a tool that mentions another company's product. **It is provided "as is", without warranty of any kind**, and without any promise of support or maintenance beyond what the automation provides. You are responsible for how you use it.

</details>

<details>
<summary><b>Legal & responsible use</b></summary>

- **Not affiliated with, endorsed or sponsored by Frontify.** "Frontify" is a trademark of its owner, used here only to describe compatibility.
- Use it **only on Frontify accounts you own or are explicitly authorised to export**. It only accesses what your token is allowed to access and does not bypass any permission or download protection.
- Exported content (brand assets, guidelines, fonts) belongs to its rights holders — mind client contracts, licences and personal data before sharing or feeding it to third-party AI services.
- Keep tokens secret; revoke them when no longer needed.
- Full text: [`DISCLAIMER.md`](DISCLAIMER.md) (EN/ES).

</details>

<details>
<summary><b>Contributing · security · automation</b></summary>

- 🤝 Issues and PRs welcome → [`CONTRIBUTING.md`](CONTRIBUTING.md) · [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)
- 🔐 Vulnerabilities → [`SECURITY.md`](SECURITY.md) (private report)
- 🤖 Self-maintaining: **CI** (lint + types + tests on Python 3.11–3.13 + Docker build), **CodeQL**, **Dependabot** (pip, Actions, Docker; minor/patch auto-merge after green CI), **release-please** (changelog + versions from Conventional Commits), stale-issue cleanup.
- 🧪 Dev: `pip install -r requirements-dev.txt && pytest && ruff check src tests && mypy src` · `python -m tests.serve_fake` runs the UI against a fake Frontify (token `test-token-123456`).

</details>

<div align="center"><sub>Made so any AI can understand your brand without losing context. ✦ <a href="LICENSE">Apache-2.0</a> · <a href="DISCLAIMER.md">Disclaimer</a></sub></div>
