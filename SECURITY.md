# Security policy / Política de seguridad

**Report privately / Reporta en privado:** use *Security → Report a vulnerability* in this repository (GitHub private advisory). Please do not open public issues for vulnerabilities. / Usa *Security → Report a vulnerability*; no abras issues públicos.

## Scope / Alcance
The tool runs locally and handles a Frontify API token. Relevant issues: token leakage (logs, files, network), path traversal when writing exports, unsafe handling of downloaded files, dependency vulnerabilities.

## Design choices / Decisiones
- The token is kept in memory or taken from the environment; it is never written to disk or returned by the local UI, and it is redacted from logs.
- Signed download URLs are used only against the CDN, **without** the Frontify token, and are not stored in exports.
- The UI binds to `127.0.0.1` (Docker publishes it on localhost only).
- Dependencies are monitored with Dependabot and CodeQL.

Best-effort support, no SLA. / Soporte best-effort, sin SLA.
