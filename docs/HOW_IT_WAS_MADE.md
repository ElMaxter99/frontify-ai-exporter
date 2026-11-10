# How this was made / Cómo se hizo

> 🇬🇧 English first, 🇪🇸 español debajo.

## 🇬🇧 English

**Transparency:** this project was built in a pair-programming session between its maintainer and an AI coding assistant (Claude Code). The maintainer set the goals and constraints; the assistant researched, wrote and tested the code. Everything is reviewable in the Git history.

1. **API research.** The official [GraphQL reference](https://frontify.github.io/graphql-reference/) was read type by type (assets, folders, guidelines, brand essentials) so that every query field exists. Findings are in [`FRONTIFY_API.md`](FRONTIFY_API.md).
2. **First version = too big.** An initial design had a database, vector stores, a React dashboard and background jobs. 
3. **Radical simplification.** It was reduced to what is needed: one local page (or one script), the file system, JSON and Markdown. The solid parts (API client, queries, Markdown rendering, text extraction) were kept.
4. **Reliability by design.** Pagination, retries, resume, hashes, duplicates, "never overwrite originals silently", "one failure never stops the run", honest reporting.
5. **Testing without credentials.** A fake Frontify (`tests/fake_frontify.py`, `httpx.MockTransport`) mimics the documented schema; the suite covers the full export, incremental runs, resume, failures and the UI API.
6. **Packaging.** Docker + one-command scripts for macOS/Linux/Windows, then repository automation (CI, CodeQL, Dependabot, releases).

**Honest status:** never run against a *real* Frontify instance (no credentials were available). Two assumptions are unconfirmed: the `https://<domain>/graphql` endpoint and the `X-Frontify-Beta` header. Real-world feedback is welcome.

## 🇪🇸 Español

**Transparencia:** este proyecto se construyó en una sesión de programación en pareja entre su mantenedor y un asistente de IA (Claude Code). El mantenedor fijó objetivos y restricciones; el asistente investigó, escribió y probó el código. Todo es revisable en el historial de Git.

1. **Investigación de la API.** Se leyó la [referencia GraphQL](https://frontify.github.io/graphql-reference/) tipo a tipo para que cada campo consultado exista. Resultados en [`FRONTIFY_API.md`](FRONTIFY_API.md).
2. **La primera versión era demasiado grande:** base de datos, vector stores, dashboard React y jobs.
3. **Simplificación radical:** una página local (o un script), sistema de archivos, JSON y Markdown. Se reutilizó lo sólido (cliente, queries, render Markdown, extracción de texto).
4. **Fiabilidad por diseño:** paginación, reintentos, reanudación, hashes, duplicados, no sobrescribir originales en silencio, un fallo no detiene el resto, informes honestos.
5. **Pruebas sin credenciales:** un Frontify simulado (`tests/fake_frontify.py`) con el esquema documentado; la suite cubre exportación completa, incrementales, reanudación, fallos y la API de la UI.
6. **Empaquetado:** Docker + scripts de un comando para macOS/Linux/Windows y automatización del repositorio (CI, CodeQL, Dependabot, releases).

**Estado honesto:** nunca se ha ejecutado contra un Frontify *real* (no había credenciales). Dos supuestos sin confirmar: el endpoint `https://<dominio>/graphql` y la cabecera `X-Frontify-Beta`. Se agradece el feedback real.
