# Dependency Version Watch

Review date: 2026-05-24

## Scope

Manifests, lock files, package groups, runtimes, and source feeds reviewed:

- Python/uv: `web/Flux`, `fluxy`, `deep`, `build`, `mine`, `sim` manifests and locks.
- NuGet: `field/Flux.FieldAgent/Flux.FieldAgent.csproj`.
- npm/tooling: `.opencode/package.json` and `.opencode/package-lock.json`.
- Vendored browser assets: local HTMX-compatible runtime and uPlot.
- Source feeds: PyPI JSON/project pages, Django 6.0 release notes, Playwright Python release notes/PyPI, NuGet flat-container APIs, npm registry version document for `@opencode-ai/plugin`.

## Executive Summary

- **Completed update/removal:** Ruff is now `0.15.14` in `web/Flux` and `fluxy`; Fluxy now uses `ty==0.0.39` as the authoritative type checker; Pyright and Waitress are removed.
- **Highest-risk hold:** hold Django at 5.2.x. Django 6.0.5 exists, but `web/Flux/pyproject.toml` deliberately pins `<6.0`, and Django 6.0 has backwards-incompatible changes that deserve a migration pass rather than routine churn.
- **Django 6 performance read:** Django 6's Python 3.13+/multiprocessing upside is mostly test-runner/concurrency-adjacent for Flux today, not a direct production performance lever. Flux's hot paths are still IO, database, browser, and Ignition-bound.
- **Update after prep:** Playwright `1.59.0 -> 1.60.0`, `Microsoft.Extensions.Hosting.Systemd` `10.0.0 -> 10.0.8`, `OPCFoundation.NetStandard.Opc.Ua` `1.5.378.134 -> 1.5.378.145`, and `@opencode-ai/plugin` `1.14.41 -> 1.15.10` should only move with their relevant verification commands.

## Dependency Inventory Summary

| Area | Direct dependencies reviewed | Current versions / latest reviewed | Version confidence |
| --- | --- | --- | --- |
| `web/Flux` runtime | Django, dj-database-url, django-environ, django-htmx, local Flux packages, gunicorn, orjson, psycopg, whitenoise | Django 5.2.14 (latest major reviewed 6.0.5); dj-database-url 3.1.2; django-environ 0.13.0; django-htmx 1.27.0; gunicorn 26.0.0; orjson 3.11.9; psycopg 3.3.4; whitenoise 6.12.0 | High for local current; medium/high for latest via uv/PyPI. |
| `web/Flux` dev | mkdocs, mkdocs-material, Playwright, pytest, pytest-django, Ruff | Playwright 1.59.0 (latest 1.60.0); Ruff 0.15.14; mkdocs 1.6.1; mkdocs-material 9.7.6; pytest 9.0.3; pytest-django 4.12.0 | High for local current; medium/high for latest via uv/PyPI. |
| `fluxy` runtime/optional | httpx, optional SQLAlchemy, optional MCP | httpx 0.28.1; SQLAlchemy 2.0.49; MCP 1.27.1 | High for httpx; medium for optional extras because sync state differs from lock/tree. |
| `fluxy` dev | pytest, Ruff, ty | Ruff 0.15.14; ty 0.0.39; pytest 9.0.3. Pyright removed. | High for local current; medium/high for latest via uv/PyPI. |
| `deep` | pytest, Ruff | pytest 9.0.3; Ruff 0.15.14 | High. |
| `build`, `mine`, `sim` | pytest and local Flux.mine dependency in build | pytest 9.0.3; Flux.mine 0.1.0 | High. |
| FieldAgent | `Microsoft.Extensions.Hosting.Systemd`, `OPCFoundation.NetStandard.Opc.Ua` | 10.0.0 -> 10.0.8; 1.5.378.134 -> 1.5.378.145 | Medium: manifest + NuGet API; no dotnet command output. |
| opencode tooling | `@opencode-ai/plugin` | 1.14.41 -> 1.15.10 | Medium: manifest/lock + npm registry; no npm CLI. |
| Vendored browser assets | HTMX-compatible runtime, uPlot | HTMX-compatible `2.0.4-flux-local`; uPlot 1.6.32 | Medium: vendored headers/README; upstream latest not reviewed. |

## Update Decisions

### Hold: Django `5.2.14` -> `6.0.5`

- **Recommendation:** **hold** for routine review; plan a deliberate Django 6 migration later.
- **Current evidence:** `web/Flux/pyproject.toml` pins `django>=5.2.14,<6.0`; `uv tree --depth 1 --outdated` reports installed 5.2.14 and latest 6.0.5.
- **Source evidence:** PyPI Django 6.0.5 JSON, retrieved 2026-05-24, reports version 6.0.5, Python `>=3.12`, upload time 2026-05-05, no PyPI vulnerability entries in that response. Django official 6.0 release notes, retrieved 2026-05-24, list Python 3.12/3.13/3.14 support and backwards-incompatible changes including database backend API changes, `DEFAULT_AUTO_FIELD` default change, custom ORM expression param tuple expectation, and removed deprecated APIs.
- **Flux value:** Django 6 brings useful built-in CSP/template partial/task features, but Flux already has high active churn and a pin that intentionally excludes 6.x.
- **Risk:** High relative to routine dependency work because this touches every Django app, migrations, templates, auth/session behavior, staticfiles, and tests. Flux avoids Django admin links and has HTMX-first surfaces; template and middleware regressions would be costly.
- **Required tests before future update:** `uv run python manage.py check`, full non-integration Django tests, e2e Comp Surface/HTMX tests, migration smoke, staticfiles/WhiteNoise check, and deprecation warning run.
- **Confidence:** High.

### Completed: Ruff `0.15.12` -> `0.15.14` in `web/Flux` and `fluxy`

- **Recommendation:** **done**.
- **Current evidence:** `uv lock --check && uv tree --depth 1 --outdated` now reports Ruff 0.15.14 in `web/Flux` and `fluxy`; Flux.Deep already resolved Ruff 0.15.14.
- **Source evidence:** PyPI Ruff 0.15.14 JSON, retrieved 2026-05-24, reports version 0.15.14, Python `>=3.7`, upload time 2026-05-21.
- **Flux value:** Keeps lint/format behavior aligned across local packages and reduces tool divergence.
- **Risk:** Low runtime risk; possible lint rule/formatter output changes.
- **Verification:** `uv run ruff check src tests` passed in `fluxy`; `uv run ruff check src` passed in `web/Flux`. `uv run ruff check src tests` in `web/Flux` failed only because `web/Flux/tests` does not exist.
- **Confidence:** High.

### Update after prep: Playwright `1.59.0` -> `1.60.0`

- **Recommendation:** **update after prep** because browser automation updates can shift selectors, browser binaries, and screenshot/render behavior.
- **Current evidence:** `uv tree --depth 1 --outdated` in `web/Flux` reports Playwright 1.59.0 latest 1.60.0; tests directly import `playwright.sync_api.sync_playwright` in multiple e2e files.
- **Source evidence:** PyPI Playwright 1.60.0 JSON, retrieved 2026-05-24, reports version 1.60.0, Python `>=3.9`, upload time 2026-05-18, bundled browser versions Chromium 148.0.7778.96, WebKit 26.4, Firefox 150.0.2. Playwright Python release notes page was retrieved 2026-05-24 but did not show a 1.60 section in the fetched page segment, so changelog details are incomplete.
- **Flux value:** E2E suite covers Comp Surfaces and HTMX workflows; fresh browser engines catch real UI drift.
- **Risk:** Medium due browser binary size and behavior changes; no runtime app import risk.
- **Required tests:** Install/update Playwright browsers in the web env, then run e2e suites from `test/manifest.toml` including dashboard/live/sim/mine/build/cell/trace browser tests.
- **Confidence:** Medium.

### Upstream: Fluxy type checker ownership

- **Recommendation:** Track through upstream `fluxy-ign`. Flux no longer vendors Fluxy source/dev tooling.
- **Current evidence:** root `pyproject.toml` consumes PyPI `fluxy-ign`; root `uv.lock` resolves package/runtime dependencies from PyPI.
- **Source evidence:** PyPI ty 0.0.39 JSON, retrieved 2026-05-24, reports version 0.0.39, Python `>=3.8`, upload time 2026-05-22, and states ty uses `0.0.x` beta versioning where breaking diagnostic/type-system changes may occur between any two versions.
- **Flux value:** Types are valuable for Fluxy, and ty now owns that responsibility without Pyright overlap.
- **Risk:** Medium for future developer friction because ty is still beta. This is now accepted architectural direction, not a blocker.
- **Verification:** upstream package verification is outside this repository.
- **Confidence:** Medium.

### Hold with note: Django 6 and Python 3.13+/multiprocessing performance

- **Recommendation:** **hold Django 6 for now**; do not upgrade just to chase Python multiprocessing improvements.
- **Source evidence:** Django 6.0 release notes mention `DiscoverRunner` support for parallel test execution on systems using the `forkserver` multiprocessing start method. Python 3.13 release notes mention `concurrent.futures` and `compileall` selecting default worker counts with `os.process_cpu_count()` and experimental free-threaded CPython; Python 3.14 release notes add standard-library multiple interpreters and `InterpreterPoolExecutor`.
- **Flux impact:** Current Flux request/runtime performance is mostly IO-bound: Ignition/WebDev calls, QuestDB/PostgreSQL reads/writes, HTMX response rendering, and browser/chart work. Django 6 does not automatically make those faster.
- **Where it could help:** test parallelism, CPU-bound import/build/mining jobs, chart downsampling, and future worker pools if we deliberately move that work into process/interpreter pools.
- **Where it will not help much:** normal Gunicorn worker request throughput, Ignition tag IO loops, QuestDB latency, or HTMX swap cost.
- **Conclusion:** Evaluate Django 6 for framework/security/lifecycle reasons first. Evaluate Python 3.13/3.14 performance separately with targeted benchmarks around Flux.mine/Flux.build/Flux.charts CPU-bound work.
- **Confidence:** Medium.

### Update after prep: FieldAgent NuGet patch packages

- **Recommendation:** **update after prep** for both NuGet packages; do not patch blindly without `dotnet restore/build` and FieldAgent smoke.
- **Current evidence:** `.csproj` pins `Microsoft.Extensions.Hosting.Systemd` 10.0.0 and `OPCFoundation.NetStandard.Opc.Ua` 1.5.378.134. NuGet flat-container APIs retrieved 2026-05-24 list stable latest `10.0.8` and `1.5.378.145` respectively.
- **Flux value:** Stays current on Linux service-hosting patch line and OPC UA stack patch line without changing the architecture.
- **Risk:** Medium because FieldAgent is runtime infrastructure and OPC UA behavior is integration-sensitive.
- **Required tests:** `dotnet restore`, `dotnet build`, FieldAgent Linux service startup with `AddSystemd()`, OPC UA endpoint browse/read smoke, and Flux.sim/FieldAgent integration tests where available.
- **Confidence:** Medium due missing dotnet command output.

### Watch / tool-only update: `@opencode-ai/plugin` `1.14.41` -> `1.15.10`

- **Recommendation:** **watch** unless opencode tooling actually needs the newer plugin. It is not a Flux app runtime dependency.
- **Current evidence:** `.opencode/package.json` pins 1.14.41; `.opencode/package-lock.json` locks plugin/sdk 1.14.41, `effect` 4.0.0-beta.59, `zod` 4.1.8. npm CLI could not run because `npm` is missing.
- **Source evidence:** npm registry document for `@opencode-ai/plugin@1.15.10`, retrieved 2026-05-24, reports dependencies `@opencode-ai/sdk` 1.15.10, `effect` 4.0.0-beta.66, `zod` 4.1.8, and optional peer dependencies `@opentui/core`, `@opentui/solid`, and `@opentui/keymap` `>=0.2.15`.
- **Flux value:** Only developer-tooling value.
- **Risk:** Low app runtime risk; medium tooling drift risk because npm is not available locally and peer surface changed.
- **Required tests:** Install node/npm or use the opencode-managed package flow, run `npm ls --prefix .opencode`, `npm outdated --prefix .opencode`, and verify opencode agents/plugins load.
- **Confidence:** Medium.

### Hold current runtime packages with clear local jobs

- **Recommendation:** **hold / no action** for `dj-database-url`, `django-environ`, `django-htmx`, `gunicorn`, `orjson`, `psycopg`, `whitenoise`, `httpx`, SQLAlchemy optional extra, MCP optional extra, pytest, pytest-django, MkDocs, and MkDocs Material unless a specific security/compatibility reason appears.
- **Evidence:** `uv tree --depth 1 --outdated` did not report newer depth-1 versions for these packages in their project groups during this run. Local usage evidence is recorded in `dependencies/dependency_inventory.md`.
- **Risk:** Avoiding churn is preferred; these packages have clear jobs and stable local purpose.
- **Confidence:** Medium/high.

## Removal Candidates

| Candidate | Recommendation | Reason |
| --- | --- | --- |
| `waitress` | **removed** | Removed from the web uv environment and absent from manifest/lock. It was Windows-runtime residue and must not be reintroduced. |
| `pyright` | **removed** | Supplanted by ty for Fluxy type checking. Do not reintroduce without an explicit architecture reversal. |
| `dj-database-url` vs `django-environ` | **needs evidence** | Both can participate in DB URL/env parsing. Current code uses both; removal requires a small settings refactor and DATABASE_URL tests. |
| `@opencode-ai/plugin` | **needs owner evidence** | Tool-local package; npm unavailable; not Flux runtime. Keep only if opencode workflow needs it. |
| Optional Fluxy `mcp` / `sqlalchemy` extras | **watch** | Good optional isolation. Do not install into web/runtime by default unless feature owner needs them. |

## Not Reviewed Or Needs Evidence

- Full npm dependency graph and npm outdated state: blocked by missing `npm`.
- FieldAgent restore/build compatibility: `dotnet list ... package --outdated` and build were not run.
- Vendored HTMX-compatible runtime and uPlot upstream latest/changelog: not reviewed; no package manager source tracks them.
- Transitive dependency advisories beyond source metadata: defer to Threat Watch/security area when update decisions depend on advisories.
- `uv run python -m pip check`: blocked because uv venvs do not include `pip`.

## Commands And Sources

Commands run:

- `uv lock --check && uv tree --depth 1 --outdated` in `web/Flux`, `fluxy`, `deep`, `build`, `mine`, `sim`.
- `uv pip list` in `web/Flux`, `fluxy`, `deep`, `build`, `mine`, `sim`.
- `uv run python -m pip check` in `web/Flux`, `fluxy`, `deep` (failed: no pip module).
- `npm ls --prefix .opencode` and `npm outdated --prefix .opencode` (failed: npm not found).
- Repository glob/grep/read checks for manifests, locks, local imports/usages, vendored asset headers, stale Waitress mentions, and test-manifest commands.

Source URLs retrieved 2026-05-24:

- PyPI Django 6.0.5 JSON: `https://pypi.org/pypi/Django/6.0.5/json`
- Django 6.0 release notes: `https://docs.djangoproject.com/en/dev/releases/6.0/`
- PyPI Playwright 1.60.0 JSON: `https://pypi.org/pypi/playwright/1.60.0/json`
- Playwright Python release notes: `https://playwright.dev/python/docs/release-notes`
- PyPI Ruff 0.15.14 JSON: `https://pypi.org/pypi/ruff/0.15.14/json`
- PyPI ty 0.0.39 JSON: `https://pypi.org/pypi/ty/0.0.39/json`
- NuGet `Microsoft.Extensions.Hosting.Systemd` versions: `https://api.nuget.org/v3-flatcontainer/microsoft.extensions.hosting.systemd/index.json`
- NuGet `OPCFoundation.NetStandard.Opc.Ua` versions: `https://api.nuget.org/v3-flatcontainer/opcfoundation.netstandard.opc.ua/index.json`
- npm `@opencode-ai/plugin@1.15.10`: `https://registry.npmjs.org/@opencode-ai/plugin/1.15.10`
- PyPI project JSON for runtime dependencies including `dj-database-url`, `django-environ`, `django-htmx`, `gunicorn`, `orjson`, `psycopg`, `whitenoise`, `httpx`, `SQLAlchemy`, and `mcp`; several responses were large/truncated by the tool but enough source feed identity was captured.

## Blockers

- `npm` is not installed, so npm CLI verification could not run.
- `uv run python -m pip check` failed because uv venv Pythons have no `pip` module.
- `uv pip check` and arbitrary `dotnet` package commands were blocked by current command permissions.
- No NuGet lock file found for FieldAgent.
- Vendored browser assets are not package-managed.

## Recommended Next Moves

1. Plan Playwright update with browser install and all e2e suites, not as a drive-by lockfile change.
2. Patch FieldAgent NuGet packages only with dotnet build/OPC smoke evidence.
3. Keep Waitress and Pyright out of Flux unless explicitly re-approved.
4. Add a package-managed or documented review path for vendored HTMX/uPlot assets before future browser dependency reviews.
5. If Django 6 is reconsidered, benchmark Python 3.13/3.14 CPU-bound worker/test paths separately from framework migration risk.
