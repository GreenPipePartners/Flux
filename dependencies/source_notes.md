# Dependency Source Notes

Last updated: 2026-05-24

## Retrieval Summary

This run used local manifests/locks, package-manager commands where permitted, repository grep/read evidence, and public package source feeds. Network source claims below were retrieved on 2026-05-24.

## Local Evidence Sources

| Source | Notes |
| --- | --- |
| `web/Flux/pyproject.toml`, `web/Flux/uv.lock` | Web runtime/dev dependency declarations and lock evidence. |
| root `pyproject.toml`, root `uv.lock` | PyPI `fluxy-ign` runtime dependency declaration and lock evidence. |
| `deep/pyproject.toml`, `build/pyproject.toml`, `mine/pyproject.toml`, `sim/pyproject.toml` and locks | Local package dependency posture. |
| `field/Flux.FieldAgent/Flux.FieldAgent.csproj` | NuGet package declarations. |
| `.opencode/package.json`, `.opencode/package-lock.json` | Tool-local npm dependency declaration and lock evidence. |
| `test/manifest.toml` | Verification command evidence for Django, pytest, Playwright/e2e, Fluxy, sim/build/mine. |
| `web/Flux/src/static/flux/vendor/README.md` and vendored asset headers | Vendored HTMX/uPlot version evidence. |

## Commands Run

| Command | Working directories | Result / limitation |
| --- | --- | --- |
| `uv lock --check && uv tree --depth 1 --outdated` | `web/Flux`, `fluxy`, `deep`, `build`, `mine`, `sim`; re-run in `web/Flux` and `fluxy` after updates | Locks resolved/fresh. After updates, Ruff is 0.15.14 in web/Flux and fluxy; ty is 0.0.39 in fluxy; Pyright is absent. Remaining outdated direct deps: Django and Playwright in web. |
| `uv pip list` | `web/Flux`, `fluxy`, `deep`, `build`, `mine`, `sim`; re-run in `web/Flux` and `fluxy` after updates | Captured installed versions. After cleanup, Waitress is absent from web/Flux and Pyright is absent from Fluxy. |
| `uv pip uninstall waitress` | `web/Flux` | Removed `waitress==3.0.2` from the web uv environment. |
| `uv sync --dev` | `web/Flux`, `fluxy` | Synchronized dev envs after lock updates. Updated Ruff and ty locally; removed Pyright/nodeenv from Fluxy env. |
| `uv run ty check src/fluxy` | `fluxy` | Passed after adding missing `TagTransport.browse()` protocol contract. |
| `uv run ruff check src tests` | `fluxy` | Passed. |
| `uv run ruff check src` | `web/Flux` | Passed. `uv run ruff check src tests` failed first because `web/Flux/tests` does not exist. |
| `uv run python -m pip check` | `web/Flux`, `fluxy`, `deep` | Failed: `.venv/bin/python3: No module named pip`. |
| `npm ls --prefix .opencode` | repo root | Failed: `npm: command not found`. |
| `npm outdated --prefix .opencode` | repo root | Failed: `npm: command not found`. |
| glob/grep/read checks | repo root | Found manifests/locks/source usage; no Docker, docker-compose, CI workflows, requirements files, Pipfile, or prior dependency reports. |

## Public Source URLs Retrieved

### Python / PyPI

| Package / topic | URL | Notes |
| --- | --- | --- |
| Django 6.0.5 | `https://pypi.org/pypi/Django/6.0.5/json` | Version, Python requirement, upload date, package metadata. |
| Django 6.0 release notes | `https://docs.djangoproject.com/en/dev/releases/6.0/` | Compatibility and backwards-incompatible changes. Dev URL fetched; page links to stable 6.0 docs. |
| Playwright 1.60.0 | `https://pypi.org/pypi/playwright/1.60.0/json` | Version, Python requirement, upload date, browser versions in description. |
| Playwright Python release notes | `https://playwright.dev/python/docs/release-notes` | Retrieved, but fetched segment did not include a 1.60 section; changelog detail incomplete. |
| Ruff 0.15.14 | `https://pypi.org/pypi/ruff/0.15.14/json` | Version, Python requirement, upload date. |
| ty 0.0.39 | `https://pypi.org/pypi/ty/0.0.39/json` | Version, Python requirement, upload date, beta `0.0.x` policy text. |
| Python 3.13 release notes | `https://docs.python.org/3.13/whatsnew/3.13.html` | `os.process_cpu_count()` worker-count changes, experimental free-threaded CPython, and concurrency/performance context. |
| Python 3.14 release notes | `https://docs.python.org/3.14/whatsnew/3.14.html` | Multiple interpreters, `InterpreterPoolExecutor`, and free-threaded performance context. |
| dj-database-url | `https://pypi.org/pypi/dj-database-url/json` | Latest/current metadata; response was large. |
| django-environ | `https://pypi.org/pypi/django-environ/json` | Latest/current metadata and changelog snippet. |
| django-htmx | `https://pypi.org/pypi/django-htmx/json` | Latest/current metadata; response truncated by tool. |
| gunicorn | `https://pypi.org/pypi/gunicorn/json` | Latest/current metadata; response truncated by tool. |
| orjson | `https://pypi.org/pypi/orjson/json` | Latest/current metadata; response very large/truncated by tool. |
| psycopg | `https://pypi.org/pypi/psycopg/json` | Latest/current metadata; response truncated by tool. |
| whitenoise | `https://pypi.org/pypi/whitenoise/json` | Latest/current metadata; response truncated by tool. |
| httpx | `https://pypi.org/pypi/httpx/json` | Latest/current metadata; response truncated by tool. |
| SQLAlchemy | `https://pypi.org/pypi/SQLAlchemy/json` | Latest/current metadata; response very large/truncated by tool. |
| mcp | `https://pypi.org/pypi/mcp/json` | Latest/current metadata; response truncated by tool. |

### NuGet

| Package | URL | Notes |
| --- | --- | --- |
| `Microsoft.Extensions.Hosting.Systemd` | `https://api.nuget.org/v3-flatcontainer/microsoft.extensions.hosting.systemd/index.json` | Version list showed stable 10.0.8 and later 11.0 preview versions. |
| `OPCFoundation.NetStandard.Opc.Ua` | `https://api.nuget.org/v3-flatcontainer/opcfoundation.netstandard.opc.ua/index.json` | Version list showed latest 1.5.378.145. |

### npm

| Package | URL | Notes |
| --- | --- | --- |
| `@opencode-ai/plugin@1.15.10` | `https://registry.npmjs.org/@opencode-ai/plugin/1.15.10` | Version-specific registry document; npm package web page returned 403 in prior attempt, full package registry document was too large, version-specific fetch succeeded. |

## Query Notes And Limitations

- `uv tree --depth 1 --outdated` uses the configured Python package indexes. It was the primary latest-version signal for direct Python packages.
- Some PyPI project JSON responses were very large and truncated by the tool; for update decisions, version-specific PyPI JSON was preferred where possible.
- NuGet evidence came from flat-container API version lists, not local restore/build.
- npm evidence came from the registry API, not local npm CLI.
- Vendored HTMX-compatible runtime and uPlot have no package-manager source. Future updates need manual upstream source capture and browser tests.
- Threat/advisory review belongs primarily to the security/Threat Watch area. This dependency review only cited advisory/security posture where needed for update/removal decisions.
