# Third-party dependencies / Dependencias de terceros

Runtime dependencies (all permissive licences, compatible with Apache-2.0). Versions are resolved at install time; check `pip show <pkg>` for the exact licence text of what you installed.
Dependencias de ejecución (todas con licencias permisivas, compatibles con Apache-2.0).

| Package | Licence | Used for |
|---|---|---|
| [fastapi](https://github.com/fastapi/fastapi) | MIT | local web UI/API |
| [uvicorn](https://github.com/encode/uvicorn) | BSD-3-Clause | ASGI server |
| [httpx](https://github.com/encode/httpx) | BSD-3-Clause | Frontify GraphQL + downloads |
| [pydantic](https://github.com/pydantic/pydantic) | MIT | request validation |
| [pypdf](https://github.com/py-pdf/pypdf) | BSD-3-Clause | text extraction from PDFs |
| [Pillow](https://github.com/python-pillow/Pillow) | MIT-CMU (HPND) | image metadata |
| [python-docx](https://github.com/python-openxml/python-docx) | MIT | text extraction from DOCX |

Development only: pytest (MIT), pytest-asyncio (Apache-2.0), ruff (MIT), mypy (MIT).
The Docker image is based on the official `python:3.12-slim` image (Debian + CPython, PSF licence); see the licences of the base image's packages.
The Code of Conduct is adapted from the Contributor Covenant 2.1 (CC BY 4.0).
