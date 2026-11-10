# Contributing / Contribuir

🇬🇧 Thanks for helping! This is a small hobby tool, so the process is light.
🇪🇸 ¡Gracias por ayudar! Es una herramienta pequeña, así que el proceso es ligero.

## Setup
```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
pytest && ruff check src tests && mypy src      # must be green / debe estar en verde
python -m tests.serve_fake                        # UI against a fake Frontify (token: test-token-123456)
```

## Rules / Reglas
- **Never** commit tokens, exports (`EXPORTS/`) or customer data. / **Nunca** subas tokens, exportaciones ni datos de clientes.
- Only use fields/queries that exist in the [official GraphQL reference](https://frontify.github.io/graphql-reference/); cite them in `docs/FRONTIFY_API.md`. / Solo campos de la referencia oficial.
- Add a test for every behaviour change (the fake API lives in `tests/fake_frontify.py`). / Un test por cada cambio.
- Keep it simple: no database, no required external services. / Mantén la simplicidad.
- Commits follow [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, `deps:`…): the release bot builds the changelog from them. / Commits convencionales: el bot de releases genera el changelog.
- Docs in **English and Spanish** (`README.md` / `README.es.md`). / Docs en inglés y español.

## Reporting a real-instance result
The project was built without access to a live Frontify. Reports from real instances are the most valuable contribution: open an issue with the (redacted) relevant part of `EXPORT_REPORT.json`.
