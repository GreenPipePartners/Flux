# Dependency Inventory

Last updated: 2026-05-24

## Scope And Evidence

Inventory sources inspected:

- `web/Flux/pyproject.toml`, `web/Flux/uv.lock`, and `uv tree --depth 1 --outdated` / `uv pip list` from `web/Flux`.
- `fluxy/pyproject.toml`, `fluxy/uv.lock`, and `uv tree --depth 1 --outdated` / `uv pip list` from `fluxy`.
- `deep/pyproject.toml`, `build/pyproject.toml`, `mine/pyproject.toml`, `sim/pyproject.toml`, their locks, and `uv tree --depth 1 --outdated` / `uv pip list` from each project.
- `field/Flux.FieldAgent/Flux.FieldAgent.csproj`.
- `.opencode/package.json` and `.opencode/package-lock.json`.
- Vendored browser asset notes in `web/Flux/src/static/flux/vendor/README.md` and asset headers.

Version confidence legend: **high** = manifest and lock/environment agree; **medium** = manifest or lock evidence but command/source tool missing; **low** = inferred from vendored header or partial evidence.

## Flux Web / Django (`web/Flux`)

### Runtime direct dependencies

| Dependency | Manifest spec | Detected version | Owner / area | Local purpose and direct evidence | Confidence |
| --- | --- | ---: | --- | --- | --- |
| `django` | `>=5.2.14,<6.0` | 5.2.14 | Flux.web / Django app | Core web framework. `web/Flux/src/flux/settings.py` sets `INSTALLED_APPS`, middleware, URLs, templates, DB, static config. | High |
| `dj-database-url` | `>=2.2` | 3.1.2 | Flux.web settings | Parses `DATABASE_URL` at `web/Flux/src/flux/settings.py:91-93` with `conn_max_age=600`. | High |
| `django-environ` | `>=0.11` | 0.13.0 | Flux.web settings | Env casting/defaults in `settings.py:13-31` and `.env` loading in `settings.py:23-25`. | High |
| `django-htmx` | `>=1.18` | 1.27.0 | Flux.web HTMX UI | Adds `django_htmx` app and middleware in `settings.py:39,65`; `dashboard/views.py` branches on `request.htmx`. | High |
| `flux-build` | local editable path `../../build` | 0.1.0 | Flux.build | Web build app imports `flux_build` in `flux/build/services.py` and `flux/build/views.py`. | High |
| `flux-mine` | local editable path `../../mine` | 0.1.0 | Flux.mine | Web mine/build apps import `flux_mine` parsers/models in `flux/mine/services.py` and `flux/build/services.py`. | High |
| `flux-sim` | local editable path `../../sim` | 0.1.0 | Flux.sim | Declared local simulator package; web app has extensive `flux.sim` app and simulator workflows. | High |
| `fluxy-ign` | local editable path `../../fluxy` | 0.1.0 | Flux.bridge / Ignition integration | `dashboard/services.py` and multiple management commands instantiate/import `fluxy.Fluxy`. | High |
| `gunicorn` | `>=26.0.0` | 26.0.0 | Linux web serving | Production/trace server path; Linux-only deployment posture. | High |
| `orjson` | `>=3.11.9` | 3.11.9 | Flux.charts / JSON performance | Imported in `flux/charts/control.py`, `views.py`, and `questdb_data_plane.py` for payload parse/dump performance. | High |
| `psycopg[binary]` | `>=3.2` | 3.3.4 (`psycopg`, `psycopg-binary`) | Flux.charts / QuestDB PostgreSQL wire path | `flux/charts/questdb_data_plane.py` imports `psycopg`, opens QuestDB connection, catches `psycopg.Error`. | High |
| `whitenoise` | `>=6.7` | 6.12.0 | Static asset serving | Middleware and staticfiles backend in `settings.py:58,118-123`. | High |

### Dev/test/tooling direct dependencies

| Dependency | Manifest spec | Detected version | Owner / area | Local purpose and direct evidence | Confidence |
| --- | --- | ---: | --- | --- | --- |
| `mkdocs` | `>=1.6.1` | 1.6.1 | Docs | Root `mkdocs.yml` and docs site tooling. | High |
| `mkdocs-material` | `>=9.7.6` | 9.7.6 | Docs | `mkdocs.yml` uses `theme.name: material`. | High |
| `playwright` | `>=1.50` | 1.59.0 | Browser e2e | E2E tests import `playwright.sync_api.sync_playwright` in dashboard/live/sim/mine/build/cell/trace test files. | High |
| `pytest` | `>=8.0` | 9.0.3 | Tests | `pyproject.toml` test configuration and `test/manifest.toml` pytest suites. | High |
| `pytest-django` | `>=4.8` | 4.12.0 | Django tests | Django pytest integration for web test suites. | High |
| `ruff` | `>=0.15.14` | 0.15.14 | Lint/format | `[tool.ruff]` in `web/Flux/pyproject.toml`; `uv run ruff check src` passed after update. | High |

### Removed environment residue

| Package | Prior version | Current evidence | Inventory status | Recommendation |
| --- | ---: | --- | --- | --- |
| `waitress` | 3.0.2 | Removed with `uv pip uninstall waitress`; final `uv pip list` for `web/Flux` no longer includes it; absent from manifest and lock. | Not a Flux dependency. | Keep absent; do not reintroduce Windows/Waitress runtime support. |

## Fluxy (`fluxy`)

### Runtime and optional dependencies

| Dependency | Manifest spec | Detected version | Owner / area | Local purpose and direct evidence | Confidence |
| --- | --- | ---: | --- | --- | --- |
| `httpx` | `>=0.27` | 0.28.1 | Fluxy HTTP client | Imported in `fluxy/core.py`, `fluxy/client/core.py`, and `fluxy/check_ignition_dev.py` for Ignition/WebDev HTTP calls. | High |
| `sqlalchemy` | optional extra `sqlalchemy>=2.0` | 2.0.49 in lock/tree; present in current fluxy env | Optional Fluxy plugin | `fluxy/plugins/sqlalchemy.py` imports `sqlalchemy.text` lazily and reports `source="sqlalchemy"`. | Medium |
| `mcp` | optional extra `mcp>=1.0` | 1.27.1 in lock/tree; not observed in `uv pip list` output | Optional MCP server | `fluxy/mcp/server.py` lazily imports `mcp.server.fastmcp.FastMCP` and exits with install guidance if missing. | Medium |

### Dev/test/tooling dependencies

| Dependency | Manifest spec | Detected version | Owner / area | Local purpose and direct evidence | Confidence |
| --- | --- | ---: | --- | --- | --- |
| `pytest` | `>=8.0` | 9.0.3 | Tests | Fluxy pytest config and `test/manifest.toml` Fluxy suites. | High |
| `ruff` | `>=0.15.14` | 0.15.14 | Lint/format | `[tool.ruff]` in `fluxy/pyproject.toml`; `uv run ruff check src tests` passed after update. | High |
| `ty` | `>=0.0.39` | 0.0.39 | Authoritative Fluxy type checker | `[tool.ty.*]` config in `fluxy/pyproject.toml`; release docs and CI use `uv run ty check src/fluxy`; `uv run ty check src/fluxy` passed after adding the missing Tag transport protocol method. | High |

Pyright was intentionally removed from Fluxy on 2026-05-24. It should not be counted as a Fluxy dependency unless the type-checking architecture is explicitly reversed.

## Flux.Deep (`deep`)

| Dependency | Manifest spec | Detected version | Runtime/dev | Local purpose and evidence | Confidence |
| --- | --- | ---: | --- | --- | --- |
| `pytest` | `>=8.0` | 9.0.3 | Dev/test | `deep/pyproject.toml` test config and tests. | High |
| `ruff` | `>=0.6` | 0.15.14 | Dev/tooling | `deep/pyproject.toml` ruff config. | High |

Flux.Deep has no external runtime dependencies in `deep/pyproject.toml`.

## Flux.build / Flux.mine / Flux.sim

| Project | Dependency | Manifest spec | Detected version | Runtime/dev | Local purpose and evidence | Confidence |
| --- | --- | --- | ---: | --- | --- | --- |
| `build` | `flux-mine` | local dependency | 0.1.0 | Runtime local | Flux.build builds from Flux.mine parse/reconciliation primitives. | High |
| `build` | `pytest` | `>=8.0` | 9.0.3 | Dev/test | Build core tests. | High |
| `mine` | `pytest` | `>=8.0` | 9.0.3 | Dev/test | Mine parser/reconciliation tests. | High |
| `sim` | `pytest` | `>=8.0` | 9.0.3 | Dev/test | Simulator tests including integration marker. | High |

Flux.mine and Flux.sim have no external runtime dependencies in their manifests.

## FieldAgent / NuGet (`field/Flux.FieldAgent`)

| Dependency | Manifest version | Latest reviewed | Runtime/dev | Local purpose and evidence | Confidence |
| --- | ---: | ---: | --- | --- | --- |
| `Microsoft.Extensions.Hosting.Systemd` | 10.0.0 | 10.0.8 stable latest on NuGet flat-container API | Runtime/Linux service hosting | `Program.cs` calls `builder.Services.AddSystemd()`. Linux-only service integration. | Medium |
| `OPCFoundation.NetStandard.Opc.Ua` | 1.5.378.134 | 1.5.378.145 stable latest on NuGet flat-container API | Runtime/OPC UA | `FieldOpcServerHost.cs`, `FieldOpcServer.cs`, `FieldNodeManager.cs`, and `OpcStackProbe.cs` import `Opc.Ua`. | Medium |

No NuGet lock file was detected. `dotnet list ... package --outdated` was not run due current command restrictions.

## opencode Tooling (`.opencode`)

| Dependency | Manifest version | Lock evidence | Runtime/dev | Local purpose and evidence | Confidence |
| --- | ---: | --- | --- | --- | --- |
| `@opencode-ai/plugin` | 1.14.41 | `.opencode/package-lock.json` locks `@opencode-ai/plugin` and `@opencode-ai/sdk` at 1.14.41; transitive `effect` 4.0.0-beta.59 and `zod` 4.1.8. | Tooling-only | opencode workspace plugin dependency; not app/runtime Flux dependency. | Medium |

`npm` was not installed, so local npm dependency graph and outdated checks could not be run.

## Vendored Browser Assets

| Dependency | Version evidence | Package-managed? | Local purpose and evidence | Confidence |
| --- | ---: | --- | --- | --- |
| HTMX-compatible local runtime | `2.0.4-flux-local` | No | `vendor/README.md`; `base.html` loads `flux/vendor/htmx/htmx.min.js?v=2.0.4`; `htmx.min.js` exposes `window.htmx.version`. | Medium |
| uPlot | 1.6.32 | No | `vendor/README.md`; `uPlot.iife.min.js` header; trace/chart templates load local uPlot CSS/JS. | Medium |

## Inventory Gaps

- No package-manager tracking exists for vendored HTMX-compatible runtime or uPlot. Latest upstream versions were not reviewed in this run.
- No npm runtime was available for `.opencode`; registry evidence was used instead.
- No NuGet lock file or `dotnet list` output was available; NuGet API evidence was used instead.
- `uv run python -m pip check` could not verify Python environment consistency because `pip` is absent from the uv-managed venvs.
