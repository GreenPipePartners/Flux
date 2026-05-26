# Dependency Update Impact Notes

Review date: 2026-05-24

## Summary

This file captures impact analysis for updates detected during the 2026-05-24 dependency review. No manifest or lock changes were made.

## Django 5.2.14 -> 6.0.5

Recommendation: **hold; deliberate migration later**.

### Local usage surface

- Core framework for `web/Flux`.
- `settings.py` configures middleware, apps, templates, database, static files, security-related cookie flags, and default auto field.
- Extensive Django apps under `web/Flux/src/flux/*`, dashboard, runtime, migrations, templates, management commands, and HTMX views.
- `django-htmx` is installed and `request.htmx` is used in dashboard views.

### Source evidence

- PyPI Django 6.0.5 JSON retrieved 2026-05-24: version 6.0.5, Python `>=3.12`, uploaded 2026-05-05.
- Django 6.0 release notes retrieved 2026-05-24: Python 3.12/3.13/3.14 support; backwards-incompatible changes and removed deprecated features.

### Main risks

- Project manifest intentionally pins `<6.0`; changing this is a migration decision, not maintenance drift.
- Database/backend and ORM behavior changes could affect migrations and query paths.
- Template/rendering changes could affect HTMX-first Comp Surfaces.
- Staticfiles and middleware behavior changes could affect WhiteNoise and local vendored assets.
- Removed deprecated APIs may surface in older app code or dependencies.

### Prep and tests required

1. Run under Django 5.2 with warnings enabled and clean deprecations first.
2. Confirm `django-htmx`, WhiteNoise, psycopg, pytest-django, and Django 6 compatibility matrix.
3. Update pin intentionally, lock, and run:
   - `uv run python manage.py check`
   - full non-integration Django test suite
   - migration smoke with a copied DB or test DB
   - Playwright e2e coverage for Comp Surface mode controls and HTMX swaps
   - staticfiles collect/WhiteNoise smoke if production mode is used
4. Rollback plan: restore previous `pyproject.toml` pin and `uv.lock`.

## Playwright 1.59.0 -> 1.60.0

Recommendation: **update after prep**.

### Local usage surface

- Dev/test only in `web/Flux`.
- Direct imports in e2e files for dashboard, mine, build, cell, live, sim, and trace.
- `test/manifest.toml` has e2e suites requiring `FLUX_PLAYWRIGHT` and browser services.

### Source evidence

- PyPI Playwright 1.60.0 JSON retrieved 2026-05-24: Python `>=3.9`, uploaded 2026-05-18, browser versions Chromium 148.0.7778.96, WebKit 26.4, Firefox 150.0.2.
- Playwright Python release notes page retrieved 2026-05-24; fetched page segment did not expose a 1.60 section, so changelog-specific risk is incomplete.

### Main risks

- Browser binary updates can shift timing, visibility, accessibility tree, selectors, and rendering.
- Could increase local setup weight and CI/browser cache size.
- Flux UI tests are valuable because HTMX/Comp Surface behavior is first-class; false positives/negatives matter.

### Prep and tests required

1. Update lock only when browser install/update can be done in the same pass.
2. Run Playwright browser install for the web uv env.
3. Run all e2e tests that import Playwright, especially Comp Surface mode controls and trace/chart pages.
4. If failures appear, separate real UX regressions from browser-behavior drift.

## Ruff 0.15.12 -> 0.15.14

Recommendation: **update now once package bumps are allowed**.

### Local usage surface

- Dev/tooling only in `web/Flux` and `fluxy`.
- Flux.Deep already resolves Ruff 0.15.14.
- `[tool.ruff]` exists in `web/Flux`, `fluxy`, and `deep` manifests.

### Source evidence

- PyPI Ruff 0.15.14 JSON retrieved 2026-05-24: uploaded 2026-05-21; Python `>=3.7`.

### Main risks

- New/changed diagnostics or formatting output could require code cleanup.
- No runtime import path impact.

### Prep and tests required

- `uv run ruff check` in `web/Flux` and `fluxy`.
- If format is enforced, `uv run ruff format --check`.

## ty 0.0.35 -> 0.0.39 and Pyright removal

Recommendation: **completed; ty is authoritative**.

### Local usage surface

- Dev/tooling only in `fluxy`.
- `fluxy/pyproject.toml` now declares `ty>=0.0.39` and configures `[tool.ty.*]` for Linux/Python 3.12 with `src/fluxy` as the checked source.
- Release docs and GitHub workflow now use `uv run ty check src/fluxy`.
- Pyright dependency, config, docs, workflow check, and `.pyright/` ignore are removed.

### Source evidence

- PyPI ty 0.0.39 JSON retrieved 2026-05-24: uploaded 2026-05-22; Python `>=3.8`; package description states ty uses `0.0.x` beta versioning and breaking changes/diagnostic changes may occur between any two versions.

### Main risks

- Beta type-checker diagnostic churn can create local friction.
- Optional extras such as MCP/SQLAlchemy may be absent from a default env, so ty config allows unresolved optional imports for those extras.
- No runtime import path impact.

### Prep and tests required

- `uv run ty check src/fluxy` passed after adding `TagTransport.browse()` to the protocol contract.
- `uv run ruff check src tests` passed in Fluxy.
- Future Fluxy type-check verification should use ty, not Pyright.

## Django 6 and Python 3.13+/3.14 multiprocessing/concurrency improvements

Recommendation: **hold Django 6; benchmark Python concurrency separately**.

### Source evidence

- Django 6.0 release notes mention `DiscoverRunner` support for parallel test execution on systems using the `forkserver` multiprocessing start method.
- Python 3.13 release notes mention `concurrent.futures`/`compileall` default worker counts using `os.process_cpu_count()` and experimental free-threaded CPython.
- Python 3.14 release notes add `concurrent.interpreters` and `InterpreterPoolExecutor`, framing multiple interpreters as process-like isolation with lower resource overhead for CPU-bound work.

### Flux impact

- Likely production benefit from Django 6 solely due multiprocessing changes: **low**.
- Likely test-suite benefit if we use Django's `DiscoverRunner --parallel` or forkserver-sensitive paths: **medium**, but Flux currently leans heavily on pytest/pytest-django and browser tests.
- Likely benefit for future CPU-bound worker pools around Flux.mine, Flux.build, chart downsampling, import parsing, and batch materialization: **potentially meaningful**, but this is Python/runtime architecture work, not a Django 6 reason by itself.
- Likely benefit for Ignition/WebDev, tag IO, QuestDB/PostgreSQL query latency, or HTMX swap rendering: **low**, because those paths are IO-bound or browser-bound.

### Recommendation

Evaluate Django 6 for framework lifecycle, security, and feature reasons. Evaluate Python 3.13/3.14 concurrency for Flux CPU-bound workloads with targeted benchmarks. Do not combine them into one migration rationale unless a benchmark proves the coupling.

## FieldAgent NuGet patches

Recommendation: **update after dotnet and runtime prep**.

### Packages

- `Microsoft.Extensions.Hosting.Systemd` 10.0.0 -> 10.0.8.
- `OPCFoundation.NetStandard.Opc.Ua` 1.5.378.134 -> 1.5.378.145.

### Local usage surface

- FieldAgent targets `net10.0` and is Linux service/runtime infrastructure.
- `Program.cs` calls `AddSystemd()`.
- OPC UA package is used across server host, server, node manager, and probe classes.

### Source evidence

- NuGet flat-container APIs retrieved 2026-05-24 list 10.0.8 and 1.5.378.145 as latest stable versions in the current lines.

### Main risks

- FieldAgent is runtime, not dev-only.
- OPC UA stack changes can affect endpoint startup, node model behavior, subscriptions, and client compatibility.
- No NuGet lock or dotnet CLI output was available in this run.

### Prep and tests required

1. Run `dotnet restore` and `dotnet build` for FieldAgent.
2. Start FieldAgent on Linux under normal service-like conditions.
3. Browse/read OPC UA nodes from Flux.sim or an OPC UA client.
4. Run integration tests that cover FieldAgent and Ignition/Flux.sim if environment is available.

## `@opencode-ai/plugin` 1.14.41 -> 1.15.10

Recommendation: **watch / update only with opencode verification**.

### Local usage surface

- Tool-local dependency in `.opencode`; not Flux runtime.
- `.opencode/package-lock.json` locks plugin/sdk 1.14.41.
- `.opencode/agents` exist, but npm was unavailable for graph verification.

### Source evidence

- npm registry document for `@opencode-ai/plugin@1.15.10` retrieved 2026-05-24: depends on `@opencode-ai/sdk` 1.15.10, `effect` 4.0.0-beta.66, `zod` 4.1.8; peer deps include optional `@opentui/keymap` in addition to OpenTUI core/solid.

### Main risks

- Missing npm locally makes update untestable in this run.
- Tooling-only value; should not block Flux app work.
- Peer dependency surface changed.

### Prep and tests required

- Install/enable npm or use opencode's preferred package tooling.
- Run `npm ls --prefix .opencode` and `npm outdated --prefix .opencode`.
- Verify opencode plugin/agent loading.

## Vendored HTMX-compatible runtime and uPlot

Recommendation: **watch and document an update path**.

### Local usage surface

- `base.html` loads local HTMX-compatible runtime.
- Trace/chart templates load uPlot assets.
- HTMX-first UI architecture depends on `hx-*` behavior and events.
- Chart pages depend on `window.uPlot`.

### Main risks

- Not package-managed, so standard outdated tools cannot detect drift.
- HTMX runtime is a local compatibility implementation reporting `2.0.4-flux-local`, not necessarily full upstream HTMX.
- uPlot update may affect chart rendering/performance.

### Prep and tests required

- Add a manual vendored-asset source note when updating.
- Run browser e2e tests for HTMX swaps and chart pages.
- Keep local assets rather than CDN to preserve deterministic/offline Flux behavior.
