# Investigación de la API de Frontify

Fuentes: <https://developer.frontify.com/> y <https://frontify.github.io/graphql-reference/> (páginas consultadas el 2026‑11‑10; la referencia indicaba "Last updated 09‑11‑2026"). Nada de lo usado se ha inferido sin comprobarlo en la referencia, salvo lo marcado como **supuesto**.

## Conexión

| Aspecto | Uso en el proyecto |
|---|---|
| Endpoint | `https://<dominio>/graphql` (**supuesto** basado en la convención documentada de Frontify) |
| Auth | `Authorization: Bearer <token>` (token personal u OAuth2) |
| Beta | `X-Frontify-Beta: enabled` (**supuesto**: necesario para campos marcados *Beta* como guidelines, essentials) |
| Paginación | Conexiones con `limit`/`page` → `{ total, page, limit, hasNextPage, items }` (verificado) |

`src/frontify/client.py` centraliza todo: reintentos con backoff+jitter (429/5xx/red, respeta `Retry-After`), `UNAUTHENTICATED`/401/403 → `FrontifyAuthError` sin reintento, errores GraphQL parciales (se registran y se devuelve `data`), detección de errores de validación (`is_validation`) para degradar consultas.

## Operaciones usadas (todas existen en la referencia)

Queries raíz: `currentUser`, `brands`, `brand(id)`, `library(id)`, `workspaceProject(id)`, `node(id)`, `assets(ids)`, `guidelineNavigationItem(id)`, `guidelinePage(id)` (Beta).

| Dato | Ruta GraphQL |
|---|---|
| Marcas | `brands { id name slug avatar }` |
| Librerías / workspaces | `brand.libraries`, `brand.workspaceProjects` |
| Carpetas | `library.browse.folders`, `workspaceProject.browse.folders`, `node(id){... on SubFolder { folders }}` |
| Assets | `…browse.assets`, `SubFolder.assets` (interfaz `Asset` + fragmentos `File/Image/Document/Video/Audio`) |
| Original | `downloadUrl` (URL firmada; `null` si está protegido contra descarga) — nunca `previewUrl`/`thumbnailUrl` |
| Metadatos | `title description alternativeText externalId createdAt modifiedAt expiresAt author status creator modifier tags customMetadata filename size extension fileCreatedAt width height pageCount duration bitrate` |
| Campos personalizados | `customMetadata { property{id name} ... on CustomMetadataValue{value} ... on CustomMetadataValues{values} }` (los `metadataValues` están deprecados) |
| Colecciones | `library.collections` + `Collection.assets` |
| Relacionados | `Asset.relatedAssets` |
| Total de control | `library.assets.total` (verifica que el recorrido por carpetas no perdió assets) |
| Guidelines | `brand.guidelines` → `Guideline.navigation` (unión de 5 tipos) → `children` de Document / Group / PageCategory → `guidelinePage.sections.elements` |
| Bloques | `GuidelinePageBlockInterface { id content url modifiedAt settings type{id name} assetSettings }`, `GuidelinePageHeading`, `GuidelinePageBlockReference` |
| Páginas de librería | `node(id){ ... on LibraryPage { assets } }` |
| Colores / tipografías | `brand.essentials.colorPalettes[].colors[].representations` y `fontFamilies[].fontStyles` |

## Limitaciones de la API (y alternativa adoptada)

1. **Sin PDF de guidelines** → Markdown + JSON crudo; PDF de librerías se descargan como assets.
2. **Assets en bloques sin ID** (`GuidelinePageBlockAsset` solo tiene `previewUrl`) → se guarda el preview junto a la página y los originales salen del recorrido de librerías; las páginas de tipo *Library* sí enlazan IDs reales (`relationships.json`, `rel=shows`).
3. **`content` nullable** en bloques → se conservan `settings` crudos.
4. **Sin permalink de asset** → procedencia por ID + dominio.
5. **Descarga protegida** (`downloadUrl` nulo) → estado `unavailable`, sin sustituir por preview.
6. Campos **Beta** pueden cambiar; los asset tienen dos niveles de consulta (completo → mínimo) y guidelines/essentials fallan de forma aislada.
7. No se exportan: `AssetVariant` (logos/iconos), `revisions`, `comments`, `licenses`, `workflow`, `attachments`, `provenance`, plantillas creativas. Son ampliaciones directas (ya existen en el esquema) si se necesitan.
