# Dependency Exposure Inventory

Retrieval date: 2026-05-24

## Detected Runtime And Dependency Stack

| Area | Evidence | Detected version / confidence | Exposure notes |
| --- | --- | --- | --- |
| Python runtime | `requires-python = ">=3.12"` in all Python subprojects; `python --version`; `uv run python --version` in `web/Flux` | Local default and web project Python 3.14.4; deployed patch version unknown | Local evidence is now confirmed. Deployment may differ and still needs explicit version capture. |
| uv tooling | `uv --version` | uv 0.11.11 | Lock/resolution tool. |
| Django web app | `web/Flux/pyproject.toml`; `web/Flux/uv.lock`; `web/Flux/src/flux/settings.py`; runtime Django import probe | Django 5.2.14 locked and runtime-confirmed | Main web runtime. SecurityMiddleware, CSRF middleware, sessions, auth middleware present. WSGI is configured; ASGI entrypoint exists and must be considered if deployed. |
| Django deployment servers | `web/Flux/pyproject.toml`; `web/Flux/uv.lock`; `uv pip list` in web env | gunicorn 26.0.0 locked | Gunicorn is the documented/test server. Waitress was removed as unsupported Windows-runtime residue and is not a Flux dependency. |
| Django support packages | `web/Flux/uv.lock`; `web/Flux/pyproject.toml`; `uv pip list`; synced runtime import check; `pip-audit --path` | django-htmx 1.27.0; django-environ 0.13.0; dj-database-url 3.1.2; whitenoise 6.12.0; orjson 3.11.9; idna 3.16 | `idna` was upgraded from vulnerable 3.14 to 3.16, and web now explicitly requires `idna>=3.15`. Synced web environment audits clean. |
| Browser/UI | `web/Flux/src/templates/flux/base.html`; `web/Flux/src/static/flux/vendor/` | local HTMX-compatible runtime; uPlot 1.6.32 already local | No public CDN fetch observed in this review. Replace the local HTMX-compatible runtime with exact upstream vendored HTMX when asset refresh tooling is available. |
| Browser automation | `web/Flux/uv.lock`; `uv run python -m playwright --version` | Playwright 1.59.0 | Dev/test dependency; bundled browsers are separate artifacts and should be updated with Playwright. |
| Database client | `web/Flux/uv.lock`; psycopg/libpq runtime probe; `psql --version` | psycopg / psycopg-binary 3.3.4; bundled libpq reports 18.0; local psql 18.3 | Local libpq/psql are below PostgreSQL fixed 18.4 for May 2026 client CVEs, including CVE-2026-6477. Practical Flux app exposure depends on large-object/client-utility use and trust boundary of DB servers. |
| Database services | docs/operator-guide.md; `settings.py`; QuestDB localhost probe | PostgreSQL server version unknown; QuestDB documented as 9.3.5; local QuestDB endpoint returned only `PostgreSQL 12.3, ... QuestDB` compatibility string | QuestDB DSN defaults to `postgresql://admin:quest@localhost:8812/qdb`; confirm not network-exposed with default credentials. PostgreSQL server needs current minor-release evidence after 2026-05-14 security release. |
| Ignition / WebDev | docs, `fluxy/pyproject.toml`, `fluxy/src`, Fluxy generated WebDev resources | Ignition Gateway version unknown; Fluxy package 0.1.0 | Gateway/WebDev is a privileged automation boundary. Version, OS, service-account privilege, project-import policy, and WebDev auth mode need environment evidence. |
| Fluxy HTTP client | `fluxy/pyproject.toml`; `fluxy/uv.lock`; `uv tree`; synced runtime import check; `pip-audit --path` | httpx 0.28.1, httpcore 1.0.9, idna 3.16 | Used by Fluxy to call Ignition/WebDev and gateway utility endpoints. `idna` was upgraded from vulnerable 3.14 to 3.16, and Fluxy now explicitly requires `idna>=3.15`. |
| Optional Fluxy MCP | `fluxy/pyproject.toml`; `fluxy/uv.lock`; full `uv tree`; `fluxy/src/fluxy/mcp/server.py`; synced runtime import check; `pip-audit --path` | mcp 1.27.1; starlette 1.1.0; python-multipart 0.0.28; sse-starlette 3.4.4; uvicorn 0.46.0 | Optional extra/script. `starlette` was upgraded from vulnerable 1.0.0 to 1.1.0, and the MCP extra now explicitly requires `starlette>=1.0.1`. Runtime exposure still exists only if MCP is installed/run through a Starlette-backed HTTP/SSE transport. Bind/auth requirements should be explicit before use beyond localhost. |
| Node/OpenCode local tooling | `.opencode/package.json`, `.opencode/package-lock.json`; `node --version`; `npm --version`; `npm audit --audit-level=low` | Node 25.9.0; npm 11.12.1; `@opencode-ai/plugin` / sdk 1.14.41; cross-spawn 7.0.6; npm audit found 0 vulnerabilities | Developer tooling, not app runtime unless invoked in deployed environment. `opencode-ai` package itself was not detected. |

## Remediated Dependency Findings From Rerun

- **`idna==3.14` — remediated to `idna==3.16`.** `pip-audit 2.10.0` originally found CVE-2026-45409 in both web and Fluxy all-extra requirement sets. Web and Fluxy now require `idna>=3.15`, lock `idna==3.16`, and synced environment audits report no known vulnerabilities.
- **`starlette==1.0.0` — remediated to `starlette==1.1.0` in optional Fluxy MCP.** `pip-audit 2.10.0` originally found `PYSEC-2026-161`; the Fluxy MCP extra now requires `starlette>=1.0.1`, locks `starlette==1.1.0`, and the synced all-extra environment audit reports no known vulnerabilities.
- **libpq/psql 18.x below fixed minor — confirmed local client version concern.** psycopg-binary reports bundled libpq 18.0 and local `psql` is 18.3; PostgreSQL May 2026 client fixes require 18.4 for major 18.
- **npm OpenCode tooling — no known vulnerabilities found by npm audit** on `.opencode/package-lock.json`.

## Local Configuration Exposure Notes

- `web/Flux/src/flux/settings.py` defaults `DJANGO_DEBUG=True` and a `dev-only-insecure-flux-secret-key`. This is acceptable for local development only; it is high risk if deployment relies on defaults.
- Django admin is no longer installed or routed; keep it out of Flux unless explicitly reintroduced behind a dev-only switch.
- Multiple state-changing views exist without explicit authentication decorators in the inspected modules; CSRF middleware is present, but unauthenticated local-network users may still be able to drive Flux/Ignition/QuestDB workflows if the app is reachable.
- QuestDB defaults use `admin:quest` on localhost. This should be treated as a local-dev default only and verified as non-routable.
- PostgreSQL server is not pinned by this repository. If `DATABASE_URL` points to a supported PostgreSQL 14-18 server below 18.4/17.10/16.14/15.18/14.23, the 2026-05-14 PostgreSQL security release may apply.
- Inductive Automation Ignition is not pinned by this repository. CISA ICS advisories from 2025-12 and 2026-03 affect some Ignition 8.1.x/8.3.x/pre-8.3.0 scenarios; Flux targets need version/platform evidence.
- Security-relevant environment variables are tracked in `security/environment_variables.md` and `web/Flux/.env.example`.
- Ignition, authoritative QuestDB product version, deployed PostgreSQL server version, and deployed Python version are not locked by this repository; environment inspection is required for those products.

## Version Evidence Commands To Resolve Blockers

- Django/app: `uv run python -c "import django; print(django.get_version())"` from `web/Flux`.
- Django dependencies: `uv tree --locked --all-groups --depth 2` from each Python subproject.
- Python: `python --version` in the deployed runtime.
- PostgreSQL server: `psql -c 'select version();'` against the deployed database.
- PostgreSQL client/libpq: `uv run python -c "import psycopg, psycopg.pq as pq; print(psycopg.__version__); print(pq.version_pretty(pq.version()))"` from `web/Flux`; `psql --version` for client tooling.
- QuestDB: use a vendor-documented product version command/endpoint, admin UI, package metadata, or service logs; the SQL compatibility `select version()` result was not sufficient.
- Ignition: use the existing Flux/Fluxy gateway version probe (`flux doctor` / Fluxy util version path) against the target gateway.
- Optional MCP: record whether `fluxy-mcp` is running, transport, host/port binding, and auth/token mode before treating MCP advisories as runtime exposure.
