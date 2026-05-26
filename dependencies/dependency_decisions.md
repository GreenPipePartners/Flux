# Dependency Decision Log

This log records durable dependency decisions. Newest entries should append under the relevant date.

## 2026-05-24

### DEP-2026-05-24-001: Hold Django 6 during routine review

- **Decision:** Hold `web/Flux` on Django 5.2.x and keep the manifest `<6.0` pin until a planned migration.
- **Reason:** Django 6.0.5 is available, but release notes include backwards-incompatible changes and the project manifest intentionally excludes 6.x. Flux has broad Django/HTMX/migration surface area, so this is not a drive-by update.
- **Evidence:** `uv tree --depth 1 --outdated` reports Django 5.2.14 latest 6.0.5; PyPI Django 6.0.5 JSON and Django 6.0 release notes retrieved 2026-05-24.
- **Review trigger:** Revisit when Flux schedules a Django 6 migration/deprecation pass.

### DEP-2026-05-24-002: Prefer low-risk dev-tool patch updates after checks

- **Decision:** Ruff `0.15.12 -> 0.15.14` in `web/Flux` and `fluxy` is recommended when package bumps are allowed, subject to clean Ruff checks.
- **Reason:** Dev-only, low runtime risk, and Flux.Deep already resolves 0.15.14.
- **Evidence:** `uv tree --depth 1 --outdated`; PyPI Ruff 0.15.14 JSON retrieved 2026-05-24.
- **Review trigger:** Run `uv run ruff check` after bump.

### DEP-2026-05-24-003: Treat Playwright updates as browser-verification work

- **Decision:** Playwright `1.59.0 -> 1.60.0` is `update after prep`, not automatic.
- **Reason:** Playwright is dev-only but browser engines can change UI test timing/rendering. Flux relies on browser tests for HTMX/Comp Surface behavior.
- **Evidence:** `uv tree --depth 1 --outdated`; PyPI Playwright 1.60.0 JSON retrieved 2026-05-24.
- **Review trigger:** Update only with browser install and e2e run plan.

### DEP-2026-05-24-004: Superseded — ty chosen over Pyright

- **Decision:** Superseded by DEP-2026-05-24-009. `ty` is now the explicit Fluxy static-check gate and Pyright is removed.
- **Reason:** User selected ty as the replacement for Pyright.
- **Evidence:** `fluxy/pyproject.toml`, docs, workflow, and `uv.lock` now reflect ty-only type checking.
- **Review trigger:** Revisit only if ty fails to cover required checks or the user explicitly reverses the decision.

### DEP-2026-05-24-005: Patch FieldAgent NuGet only with dotnet/build evidence

- **Decision:** `Microsoft.Extensions.Hosting.Systemd` and `OPCFoundation.NetStandard.Opc.Ua` patches are `update after prep`.
- **Reason:** Both are runtime infrastructure dependencies; OPC UA stack changes need FieldAgent smoke tests. Current run lacked dotnet command output.
- **Evidence:** `.csproj` versions and NuGet flat-container APIs retrieved 2026-05-24.
- **Review trigger:** When dotnet restore/build/test and OPC UA smoke can be run.

### DEP-2026-05-24-006: Superseded — Waitress removed

- **Decision:** Superseded by DEP-2026-05-24-010. Waitress has been removed from the web uv environment.
- **Reason:** It was Windows-runtime residue and Flux is Linux/gunicorn-first.
- **Evidence:** `uv pip uninstall waitress` removed it and final `uv pip list` no longer includes it.
- **Review trigger:** Revisit only if the Linux-only runtime architecture is explicitly changed.

### DEP-2026-05-24-007: Keep Fluxy optional extras optional

- **Decision:** `mcp` and `sqlalchemy` should remain optional Fluxy extras and should not be pulled into web/runtime by default.
- **Reason:** They have local lazy-import/plugin jobs but increase transitive surface when installed.
- **Evidence:** `fluxy/pyproject.toml` optional extras and lazy imports in `fluxy/mcp/server.py` and `fluxy/plugins/sqlalchemy.py`.
- **Review trigger:** Revisit if MCP or SQLAlchemy integration becomes first-class Flux runtime.

### DEP-2026-05-24-008: opencode plugin is tool-only watch

- **Decision:** Do not treat `@opencode-ai/plugin` as Flux runtime. Watch/update only with opencode tooling verification.
- **Reason:** It is isolated under `.opencode`; npm is missing locally; latest version changes transitive/peer surface.
- **Evidence:** `.opencode/package.json`, `.opencode/package-lock.json`, npm registry `@opencode-ai/plugin@1.15.10` retrieved 2026-05-24.
- **Review trigger:** opencode agent/plugin failure, explicit tool update request, or npm availability.

### DEP-2026-05-24-009: ty supplants Pyright for Fluxy

- **Decision:** `ty` is Fluxy's authoritative type checker. Pyright is removed from Fluxy dependencies, config, docs, workflow checks, and ignore rules.
- **Reason:** User explicitly chose ty over Pyright; one type-checker owner is cleaner than split authority.
- **Evidence:** `fluxy/pyproject.toml` now declares `ty>=0.0.39` and `[tool.ty.*]`; `uv tree --depth 1 --outdated` shows ty 0.0.39 and no Pyright; `uv run ty check src/fluxy` passed.
- **Review trigger:** Revisit only if ty fails to cover required checks or the user explicitly reverses the decision.

### DEP-2026-05-24-010: Waitress removed and forbidden as Flux runtime

- **Decision:** Waitress is removed from the web uv environment and should not be reintroduced.
- **Reason:** It was residue from the now-ended Windows implementation path. Flux is Linux/gunicorn-first.
- **Evidence:** `uv pip uninstall waitress` removed 3.0.2; final `uv pip list` in `web/Flux` no longer includes Waitress; manifests/locks have no Waitress entry.
- **Review trigger:** Revisit only if the Linux-only runtime architecture is explicitly changed.

### DEP-2026-05-24-011: Ruff aligned at 0.15.14

- **Decision:** Ruff is updated to 0.15.14 in `web/Flux` and `fluxy`.
- **Reason:** Low-risk dev-tool alignment; Flux.Deep already used 0.15.14.
- **Evidence:** `uv lock --check && uv tree --depth 1 --outdated` shows Ruff 0.15.14 in both projects; `uv run ruff check src` passed in web; `uv run ruff check src tests` passed in Fluxy.
- **Review trigger:** Normal future dependency review.

### DEP-2026-05-24-012: Django 6 is not a multiprocessing-performance upgrade by itself

- **Decision:** Do not upgrade to Django 6 solely to chase Python 3.13+/3.14 multiprocessing/concurrency improvements.
- **Reason:** The most relevant Django 6 multiprocessing note is test-runner parallel support. Python 3.13/3.14 concurrency improvements may matter for CPU-bound Flux worker workloads, but Flux's current production hot paths are primarily IO-bound.
- **Evidence:** Django 6.0 release notes; Python 3.13 and 3.14 release notes retrieved 2026-05-24; local Flux architecture and dependency inventory.
- **Review trigger:** Revisit with targeted benchmarks for Flux.mine/Flux.build/Flux.charts CPU-bound work or a planned Django 6 migration.
