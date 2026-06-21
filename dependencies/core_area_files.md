# Dependencies Area File Index

Last updated: 2026-05-24

## Area Purpose

Dependency Steward owns dependency inventory, version-watch, update impact, removal-candidate, source-note, decision-log, and daily activity records for Flux. This area is report-only: dependency stewardship does not change manifests, lock files, application code, tests, migrations, generated data, runtime config, or security-owned reports unless explicitly reassigned.

## Owned Dependency Reports

| File | Purpose | Update cadence |
| --- | --- | --- |
| `dependencies/core_area_files.md` | Index of dependency-owned files, manifests, lock files, recurring commands, source feeds, and review conventions. | Every non-trivial dependency run when sources/conventions change. |
| `dependencies/dependency_inventory.md` | Current direct dependency inventory with detected versions, local purpose, owner, usage evidence, and confidence. | After manifest/lock changes or broad dependency review. |
| `dependencies/version_watch.md` | Latest-version tracking report and update/hold/watch recommendations. | After version checks or source-feed review. |
| `dependencies/update_impact.md` | Impact notes, migration risks, and test recommendations for candidate updates. | Before/after update planning. |
| `dependencies/removal_candidates.md` | Dependencies worth removing, replacing, or proving necessary. | Every removal-minded review. |
| `dependencies/dependency_decisions.md` | Durable decision log for update, hold, remove, replace, defer, and watch decisions. | When a recommendation becomes a standing decision. |
| `dependencies/source_notes.md` | Trusted source URLs, retrieval dates, command notes, and source limitations. | Every source-query run. |
| `dependencies/daily/dependencies_YYYY-MM-DD/dependencies_YYYY-MM-DD.md` | Append-only daily activity ledger. | Every non-trivial dependency run. |

## Dependency Source Files Reviewed

### Python / uv

| Project | Manifest | Lock | Notes |
| --- | --- | --- | --- |
| Flux web/Django | `web/Flux/pyproject.toml` | `web/Flux/uv.lock` | Main Django app, docs tooling, browser e2e tooling, local workspace packages. |
| Fluxy | PyPI `fluxy-ign` entry in root `pyproject.toml` | root `uv.lock` | Ignition/WebDev client consumed as a package dependency. Fluxy source/tests are not vendored in this repository. |
| Flux.Deep | `deep/pyproject.toml` | `deep/uv.lock` | Isolated OpenPLC/L5X experiment package; no runtime external dependencies. |
| Flux.build | `build/pyproject.toml` | `build/uv.lock` | Local core package; runtime dependency on local Flux.mine. |
| Flux.mine | `mine/pyproject.toml` | `mine/uv.lock` | Local core package; no runtime external dependencies. |
| Flux.sim | `sim/pyproject.toml` | `sim/uv.lock` | Local simulator package; no runtime external dependencies. |

### .NET / NuGet

| Project | Manifest | Lock | Notes |
| --- | --- | --- | --- |
| Flux FieldAgent | `field/Flux.FieldAgent/Flux.FieldAgent.csproj` | None detected | Targets `net10.0`; direct packages are `Microsoft.Extensions.Hosting.Systemd` and `OPCFoundation.NetStandard.Opc.Ua`. |

### npm / tool-local

| Project | Manifest | Lock | Notes |
| --- | --- | --- | --- |
| opencode workspace tooling | `.opencode/package.json` | `.opencode/package-lock.json` | Tooling-only package `@opencode-ai/plugin`; not Flux app runtime. `npm` was not installed during review. |

### Vendored browser assets

| Asset | Location | Version evidence | Notes |
| --- | --- | --- | --- |
| HTMX-compatible runtime | `web/Flux/src/static/flux/vendor/htmx/htmx.min.js` | Reports `2.0.4-flux-local`; template query string `?v=2.0.4`; `vendor/README.md`. | Local subset/runtime, not package-managed. Critical to HTMX-first UI. |
| uPlot | `web/Flux/src/static/flux/vendor/uplot/uPlot.iife.min.js`; `uPlot.min.css` | Header `uPlot (v1.6.32)`; `vendor/README.md`. | Local charting dependency, not package-managed. |

## Source Files Not Found On 2026-05-24

- No `requirements*.txt`, `requirements*.in`, or `Pipfile*` found.
- No `Dockerfile*` or `docker-compose*.yml` found.
- No `.github/workflows/*` found.
- No prior `dependencies/**/*.md` files found before this run.

## Recurring Commands

Use these commands as read-only evidence-gathering commands. Do not apply updates unless the user explicitly asks.

### Python / uv

```bash
uv lock --check
uv tree --depth 1 --outdated
uv pip list
uv run python -m pip check
```

Run from each Python project root: `web/Flux`, `fluxy`, `deep`, `build`, `mine`, and `sim`.

Known 2026-05-24 limitation: `uv run python -m pip check` failed in `web/Flux`, `fluxy`, and `deep` because the venv Python had no `pip` module. `uv pip check` was blocked by command permissions.

### npm / opencode

```bash
npm ls --prefix .opencode
npm outdated --prefix .opencode
```

Known 2026-05-24 limitation: both commands failed because `/usr/bin/bash: line 1: npm: command not found`.

### NuGet / FieldAgent

Preferred if permitted in a future run:

```bash
dotnet list field/Flux.FieldAgent/Flux.FieldAgent.csproj package --outdated
dotnet restore field/Flux.FieldAgent/Flux.FieldAgent.csproj
dotnet build field/Flux.FieldAgent/Flux.FieldAgent.csproj
```

Known 2026-05-24 limitation: `dotnet list ... package --outdated` could not be run under current command permissions, so NuGet version evidence came from the `.csproj` and NuGet flat-container APIs.

## Trusted Source Feeds

| Ecosystem | Source | URL pattern |
| --- | --- | --- |
| PyPI | PyPI JSON API and project pages | `https://pypi.org/pypi/{package}/json`, `https://pypi.org/pypi/{package}/{version}/json`, `https://pypi.org/project/{package}/{version}/` |
| Django | Official release notes | `https://docs.djangoproject.com/en/6.0/releases/6.0/` |
| Playwright Python | Official docs / PyPI metadata | `https://playwright.dev/python/docs/release-notes`, `https://pypi.org/pypi/playwright/{version}/json` |
| Ruff / ty | PyPI metadata; Astral/GitHub changelogs if deeper review needed | `https://pypi.org/pypi/ruff/{version}/json`, `https://pypi.org/pypi/ty/{version}/json` |
| NuGet | NuGet flat-container API | `https://api.nuget.org/v3-flatcontainer/{package-id-lower}/index.json` |
| npm | npm registry package documents | `https://registry.npmjs.org/{package}/{version}` |

## Review Conventions

- Separate direct dependencies from transitive dependencies.
- Separate runtime dependencies from dev/test/tooling dependencies.
- Treat local workspace packages as direct dependencies only where manifests declare them.
- Treat vendored browser assets separately from package-managed dependencies.
- Treat Waitress as unsupported Windows-runtime residue. It should stay absent from manifests, locks, environments, and dependency recommendations.
- Treat `ty` as Fluxy's authoritative type checker. Pyright should stay absent unless the architecture decision is explicitly reversed.
- Do not recommend an update merely because a newer version exists; tie it to Flux value, security, compatibility, determinism, or maintenance cost.
- Favor dependency removal when purpose is weak, usage is absent, or responsibility overlaps with another first-class project tool.
- Keep Flux performance first: flag import-time, page-weight, browser-work, database-pressure, Ignition-IO, polling, and runtime-complexity risks.
- Do not modify manifests, lock files, application code, tests, migrations, templates, generated data, runtime config, or non-dependency reports during stewardship runs.
