# Dependency Daily Log — 2026-05-24

## Session Entry — timestamp not captured

### Task intent

Continue dependency stewardship review for Flux after major Flux.Deep/Linux-only/trace-charts working-tree changes. Build the first dependency-owned inventory, version watch, update-impact, removal-candidate, decision, source-note, and daily log files without changing dependency manifests, lock files, application code, tests, migrations, templates, generated data, runtime config, or security reports.

### Manifests and lock files inspected

- Python/uv: `web/Flux/pyproject.toml`, `web/Flux/uv.lock`; `fluxy/pyproject.toml`, `fluxy/uv.lock`; `deep/pyproject.toml`, `deep/uv.lock`; `build/pyproject.toml`, `build/uv.lock`; `mine/pyproject.toml`, `mine/uv.lock`; `sim/pyproject.toml`, `sim/uv.lock`.
- NuGet: `field/Flux.FieldAgent/Flux.FieldAgent.csproj`.
- npm/tooling: `.opencode/package.json`, `.opencode/package-lock.json`.
- Browser vendored assets: `web/Flux/src/static/flux/vendor/README.md`, `htmx/htmx.min.js`, `uplot/uPlot.iife.min.js`, `uplot/uPlot.min.css`.
- Verification manifest: `test/manifest.toml`.

### Commands run

- `uv lock --check && uv tree --depth 1 --outdated` in `web/Flux`, `fluxy`, `deep`, `build`, `mine`, and `sim`.
- `uv pip list` in `web/Flux`, `fluxy`, `deep`, `build`, `mine`, and `sim`.
- `uv run python -m pip check` in `web/Flux`, `fluxy`, and `deep` — failed because the uv venv Python had no `pip` module.
- `npm ls --prefix .opencode` — failed because `npm` is not installed.
- `npm outdated --prefix .opencode` — failed because `npm` is not installed.
- `git status --short` for awareness of existing working-tree changes; no commit/staging work performed.
- Repository glob/grep/read checks for manifests, lock files, package usages, vendored browser asset versions, stale Waitress mentions, and test commands.

### Packages reviewed

- Web runtime: Django 5.2.14, dj-database-url 3.1.2, django-environ 0.13.0, django-htmx 1.27.0, gunicorn 26.0.0, orjson 3.11.9, psycopg/psycopg-binary 3.3.4, whitenoise 6.12.0, local Flux packages.
- Web dev/test: mkdocs 1.6.1, mkdocs-material 9.7.6, Playwright 1.59.0, pytest 9.0.3, pytest-django 4.12.0, Ruff 0.15.12.
- Fluxy runtime/optional/dev: httpx 0.28.1, optional SQLAlchemy 2.0.49, optional MCP 1.27.1, Pyright 1.1.409, pytest 9.0.3, Ruff 0.15.12, ty 0.0.35.
- Deep/build/mine/sim dev: pytest 9.0.3; Ruff 0.15.14 in deep; local Flux.mine dependency in build.
- FieldAgent NuGet: `Microsoft.Extensions.Hosting.Systemd` 10.0.0 and `OPCFoundation.NetStandard.Opc.Ua` 1.5.378.134.
- opencode tooling: `@opencode-ai/plugin` 1.14.41 and lockfile transitive plugin/sdk evidence.
- Vendored browser assets: HTMX-compatible `2.0.4-flux-local`; uPlot 1.6.32.
- Environment residue: Waitress 3.0.2 present in `web/Flux` venv but absent from manifest/lock.

### Source URLs queried

- `https://pypi.org/pypi/Django/6.0.5/json`
- `https://docs.djangoproject.com/en/dev/releases/6.0/`
- `https://pypi.org/pypi/playwright/1.60.0/json`
- `https://playwright.dev/python/docs/release-notes`
- `https://pypi.org/pypi/ruff/0.15.14/json`
- `https://pypi.org/pypi/ty/0.0.39/json`
- `https://api.nuget.org/v3-flatcontainer/microsoft.extensions.hosting.systemd/index.json`
- `https://api.nuget.org/v3-flatcontainer/opcfoundation.netstandard.opc.ua/index.json`
- `https://registry.npmjs.org/@opencode-ai/plugin/1.15.10`
- PyPI package JSON for `dj-database-url`, `django-environ`, `django-htmx`, `gunicorn`, `orjson`, `psycopg`, `whitenoise`, `httpx`, `SQLAlchemy`, and `mcp`.

### Recommendations recorded

- Hold Django 6.0.5 for a deliberate migration; keep current `<6.0` pin.
- Update Ruff `0.15.12 -> 0.15.14` in `web/Flux` and `fluxy` when package bumps are allowed and Ruff checks are run.
- Update Playwright `1.59.0 -> 1.60.0` only with browser install and e2e verification.
- Decide whether ty earns its place beside Pyright; update after baseline if kept, otherwise remove later.
- Patch FieldAgent NuGet packages only with dotnet restore/build and OPC UA smoke evidence.
- Treat Waitress as environment residue and remove via environment sync/recreation, not manifest work.
- Keep Fluxy `mcp` and `sqlalchemy` optional extras optional; avoid pulling them into default web/runtime env.
- Watch opencode plugin as tool-only; update only with npm/opencode verification.
- Add manual update/review path for vendored HTMX/uPlot assets.

### Blockers and limitations

- `npm` is not installed.
- `uv run python -m pip check` failed because `pip` is absent from uv venv Pythons.
- `uv pip check` and arbitrary dotnet package commands were blocked by command permissions.
- No NuGet lock file detected.
- Vendored browser assets are not package-managed.
- Some PyPI JSON responses were very large and truncated by the tool; source identities and key version-specific responses were still captured.
- Security docs contain stale Waitress mentions, but security files are outside dependency-owned write scope for this run.

### Files written

- Created `dependencies/core_area_files.md`.
- Created `dependencies/dependency_inventory.md`.
- Created `dependencies/version_watch.md`.
- Created `dependencies/update_impact.md`.
- Created `dependencies/removal_candidates.md`.
- Created `dependencies/dependency_decisions.md`.
- Created `dependencies/source_notes.md`.
- Created this daily log.

### Next dependency actions

1. Ask for explicit approval before applying any package updates.
2. If approved, start with Ruff alignment because it is low runtime risk.
3. Recreate/sync `web/Flux` venv and verify Waitress disappears.
4. Establish ty-vs-Pyright policy for Fluxy.
5. Add vendored-browser-asset review convention before changing HTMX/uPlot.

## Session Entry — dependency cleanup follow-up

### Task intent

Apply explicit dependency decisions: remove Waitress residue, make ty replace Pyright for Fluxy type checking, update Ruff, notify Dependency Steward policy, and assess whether Django 6 should be justified by Python 3.13+/3.14 multiprocessing/concurrency improvements.

### Changes made

- Removed Pyright from `fluxy/pyproject.toml` dev dependencies and removed `[tool.pyright]` config.
- Added `[tool.ty.*]` config in `fluxy/pyproject.toml` and made ty `>=0.0.39` the Fluxy type-checker dependency.
- Updated Fluxy release docs and GitHub workflow from `uv run pyright` to `uv run ty check src/fluxy`.
- Removed `.pyright/` from `fluxy/.gitignore`.
- Removed the Pyright-specific optional MCP import suppression from `fluxy/src/fluxy/mcp/server.py`; optional unresolved imports are now handled by ty config.
- Fixed the type contract ty found by adding `TagTransport.browse()` to `fluxy/src/fluxy/client/tag/Tag.py`.
- Updated Ruff lower bounds to `>=0.15.14` in `web/Flux/pyproject.toml` and `fluxy/pyproject.toml`.
- Updated `web/Flux/uv.lock` and `fluxy/uv.lock`; Pyright/nodeenv were removed from the Fluxy lock and Ruff/ty were updated.
- Removed Waitress from the web uv environment with `uv pip uninstall waitress`.
- Updated Dependency Steward's opencode agent prompt to treat Waitress as forbidden Windows residue and ty as Fluxy's type-checking owner.

### Verification

- `uv lock --check && uv tree --depth 1 --outdated` passed in `web/Flux`; Ruff is 0.15.14 and remaining direct outdated packages are Django 6.0.5 and Playwright 1.60.0.
- `uv lock --check && uv tree --depth 1 --outdated` passed in `fluxy`; Pyright is gone, ty is 0.0.39, Ruff is 0.15.14.
- `uv pip list` in `web/Flux` confirms Waitress is absent and Ruff is 0.15.14.
- `uv pip list` in `fluxy` confirms Pyright is absent and ty/Ruff are current.
- `uv run ty check src/fluxy` passed.
- `uv run ruff check src tests` passed in Fluxy.
- `uv run ruff check src` passed in web/Flux.
- `uv run ruff check src tests` in web/Flux failed because `web/Flux/tests` does not exist; reran the valid `src` scope.

### Django 6 / Python 3.13+ assessment

- Django 6's relevant multiprocessing note is primarily test-runner parallel support (`DiscoverRunner` with `forkserver`). That is not a strong production-performance reason for Flux by itself.
- Python 3.13/3.14 concurrency improvements may matter for CPU-bound Flux.mine, Flux.build, Flux.charts, import parsing, downsampling, or worker pools, but they should be benchmarked independently of the Django 6 migration.
- Current Flux production hot paths are more likely IO-bound: Ignition/WebDev, QuestDB/PostgreSQL, browser/chart rendering, and HTMX swaps.

### Standing decisions updated

- Waitress is removed and should stay out.
- Pyright is removed and should stay out.
- ty is Fluxy's type-checking authority.
- Ruff is aligned at 0.15.14.
- Django 6 remains a planned migration candidate, not a multiprocessing-performance update.
