# Using the export with AI / Usar la exportación con IA

> 🇬🇧 English first · 🇪🇸 español debajo

## 🇬🇧 English

The goal of this tool: your AI assistant should **follow your brand's rules and styles** instead of guessing. The export gives it grounded context.

### What to give the AI (smallest useful set first)
1. `README_AI.md` — how the folder is organised and the ground rules.
2. `06_AI_KNOWLEDGE/BRAND_OVERVIEW.md` + `VISUAL_IDENTITY.md` — who the brand is, colors, typography, logos.
3. `06_AI_KNOWLEDGE/BRAND_GUIDELINES.md` — the rules (can be long; for chat tools upload it as a file, or give only the pages you need from `01_BRAND_GUIDELINES/`).
4. `ASSET_INDEX.md` / `DESIGN_SYSTEM.md` — only when the task needs asset paths or design details.

### Per tool
| Tool | How |
|---|---|
| **ChatGPT / Claude (projects)** | Upload the `06_AI_KNOWLEDGE/*.md` files (and `README_AI.md`) as project knowledge; put the prompt below in the project instructions. |
| **Claude Code / Codex / Cursor / Copilot** | Copy or symlink the export into your repo (e.g. `docs/brand/`) and reference it from `AGENTS.md` / `CLAUDE.md` / `.cursor/rules`: *"Brand rules live in docs/brand/06_AI_KNOWLEDGE — read VISUAL_IDENTITY.md before touching UI"*. Don't commit it if the content is confidential. |
| **Your own RAG** | Index the `.md` files (split by headings). Each guideline file's front-matter has the Frontify id and source URL for citations. |

### Starter instructions
```text
You work for the brand described in the attached Frontify export.
- Treat 06_AI_KNOWLEDGE/*.md as the source of truth for colors, typography, logo usage and tone.
- Use only the values found there. If something is "Not available" or missing, say so and ask; never invent colors, fonts or rules.
- When you use an asset, cite its path from ASSET_INDEX.md. Never alter original logos.
- If two documents disagree, prefer the guideline page and mention the conflict.
```

### Tips
- Large exports: start with VISUAL_IDENTITY + the guideline pages relevant to the task; ASSET_INDEX can be huge.
- Re-export when the brand changes (it is incremental) and re-upload the changed files.
- Check `EXPORT_REPORT.json`: failed or inaccessible pages mean the AI lacks that knowledge.
- Confidential brand material + third-party AI services: check your client's contract first.

## 🇪🇸 Español

El objetivo: que tu asistente de IA **siga las normas y estilos de la marca** en vez de adivinar. La exportación le da contexto fiable.

### Qué darle a la IA (de lo mínimo útil a lo más completo)
1. `README_AI.md` — cómo está organizada la carpeta y las reglas básicas.
2. `06_AI_KNOWLEDGE/BRAND_OVERVIEW.md` + `VISUAL_IDENTITY.md` — quién es la marca, colores, tipografías, logos.
3. `06_AI_KNOWLEDGE/BRAND_GUIDELINES.md` — las normas (puede ser largo; en herramientas de chat súbelo como archivo o da solo las páginas necesarias de `01_BRAND_GUIDELINES/`).
4. `ASSET_INDEX.md` / `DESIGN_SYSTEM.md` — solo si la tarea necesita rutas de assets o detalles de diseño.

### Por herramienta
| Herramienta | Cómo |
|---|---|
| **ChatGPT / Claude (proyectos)** | Sube los `.md` de `06_AI_KNOWLEDGE/` (y `README_AI.md`) como conocimiento del proyecto y pega el prompt de abajo en las instrucciones. |
| **Claude Code / Codex / Cursor / Copilot** | Copia o enlaza la exportación en tu repo (p. ej. `docs/brand/`) y referénciala desde `AGENTS.md` / `CLAUDE.md` / `.cursor/rules`: *«Las normas de marca están en docs/brand/06_AI_KNOWLEDGE; lee VISUAL_IDENTITY.md antes de tocar la UI»*. No lo subas al repo si el contenido es confidencial. |
| **Tu propio RAG** | Indexa los `.md` (partidos por encabezados). El front-matter de cada guideline trae el id de Frontify y la URL para citar. |

### Instrucciones de partida
```text
Trabajas para la marca descrita en la exportación de Frontify adjunta.
- Considera 06_AI_KNOWLEDGE/*.md la fuente de verdad de colores, tipografía, uso de logos y tono.
- Usa solo los valores que aparecen ahí. Si algo dice "Not available" o falta, dilo y pregunta; nunca inventes colores, fuentes ni normas.
- Al usar un asset, cita su ruta de ASSET_INDEX.md. Nunca modifiques los logos originales.
- Si dos documentos se contradicen, prefiere la página de guideline y menciona el conflicto.
```

### Consejos
- Exportaciones grandes: empieza por VISUAL_IDENTITY y las páginas de guideline relevantes; ASSET_INDEX puede ser enorme.
- Vuelve a exportar cuando cambie la marca (es incremental) y re-sube los ficheros cambiados.
- Revisa `EXPORT_REPORT.json`: páginas fallidas o inaccesibles = conocimiento que la IA no tiene.
- Material de marca confidencial + IA de terceros: revisa antes el contrato del cliente.
