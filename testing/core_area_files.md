# Testing Core Area Files

Last updated: 2026-05-24 after strict live skip-barrier cleanup.

## Owned Logs

- `test_log.md` — project-level test intent and maintenance context.
- `test_audit.md` — latest broad/holistic audit report.
- `testing/core_area_files.md` — this continuous testing index.
- `testing/daily/testing_YYYY-MM-DD/testing_YYYY-MM-DD.md` — append-only daily testing ledger.

## Primary Test Entry Points

- `test/manifest.toml` — Flux.test suite definitions, required env gates, cleanup expectations, and destructive scope.
- `test/runner.py` / `test/flux_test.py` — report/execute harness and named profiles.
- `tests/` — top-level Python tests for CLI, test manifest behavior, and static performance guardrails.
- `web/Flux/src/**/tests.py` — Django app unit and integration-style tests.
- `web/Flux/src/**/test_e2e_playwright.py` — Playwright/browser tests gated by `FLUX_PLAYWRIGHT=1`.
- `mine/tests`, `build/tests`, `sim/tests`, `fluxy/tests`, `deep/tests` — package-local pytest suites.

## Daily/Broad Commands

- Fast non-live smoke: `uv run python test/runner.py --profile fast --execute` from repo root.
- Web/Django profile: `uv run python test/runner.py --profile web --execute` from repo root.
- Full web pytest: `uv run pytest src -q` from `web/Flux`.
- Focused provider-tree loop: `uv run pytest src/flux/base/tests.py -q` from `web/Flux`.
- Manifest e2e: `uv run python test/runner.py --live-audit-env e2e-mine-build --execute` from repo root.
- Ignition trial reset: `uv run python test/runner.py activate-ignition --execute` from repo root.
- Live audit: `uv run python test/runner.py --live-audit-env --profile e2e --profile live --execute` from repo root.
- Deep package: `uv run pytest -q` from `deep`.

## Profiles And Current Meaning

- `fast` — reliable green daily smoke as of 2026-05-24.
- `web` — useful broad Django profile; currently fails only in Flux.base provider-tree selection.
- `e2e` — currently only `e2e-mine-build`; it covers mine/build/cell browser flows, not all Comp Surfaces.
- `live` — attempts Fluxy/Ignition/sim/web/closed-loop work when gates are present; strict mode now fails zero-test/all-skipped output, core Fluxy and sim pass, PostgreSQL is an explicit blocked suite, and web integration currently fails on supervisor OPC `FAULTED` state.
- `audit` — report-only or broad aggregate profile; use report-only first to understand env gates.

## Important Fixtures And Gates

- Flux.cell demo: `seed_demo_cell_bundle()`; used by phone simulator unit/e2e tests.
- Fluxolot Fishtank: persistent verification fixture for sim/live/trace/closed-loop acceptance.
- Provider export fixtures: used by Flux.base and Flux.sim selection/tree tests.
- Browser gate: `FLUX_PLAYWRIGHT=1`; prefer `test/runner.py --live-audit-env` so agents do not need shell env prefixes.
- Live gates: `FLUXY_BASE_URL`, `FLUXY_TOKEN`, `FLUX_FULL_INTEGRATION`, plus test-specific flags such as `FLUX_SIM_IGNITION_INTEGRATION`, `FLUX_FIELD_INTEGRATION`, `FLUX_FIELD_SUPERVISOR_INTEGRATION`, `FLUX_LIVE_EXTRACTION_INTEGRATION`, and `FLUX_LIVE_CLOSED_LOOP_OPC`.
- Activation helper: `scripts/activate_ignition_selenium.py` is exposed through Flux.test as `activate-ignition` with transient Selenium support.
- Never print `FLUXY_TOKEN` values; document only whether token gates were present or missing.

## Current Known Signals

- Fast/core non-live suites pass.
- Full web pytest currently has one failure: `flux.base.tests.BaseTagModelTests.test_provider_tree_marks_sim_selection`.
- Manifest e2e passes after aligning Flux.cell phone simulator e2e with the no-counter UI contract.
- Live Fluxy integration, sim-to-Ignition integration, and closed-loop Fluxolot acceptance pass after running `activate-ignition`.
- `integration-web` now runs pytest integration selections and currently fails on `test_field_supervisor_multi_process_devices_read_through_fluxy` because Ignition reports the supervised FieldAgent OPC server as `FAULTED`.
- Fluxy PostgreSQL integration is explicit as `integration-fluxy-postgres` and blocks unless `FLUXY_POSTGRES_ENABLED=1` and PostgreSQL datasource settings are available.

## Test Intent Conventions

- When adding or materially changing a test, append context to `test_log.md` with test name, protected risk, cases, fixtures/gates, reason, and maintenance notes.
- For broad/holistic reviews, refresh `test_audit.md` using the standard audit sections.
- For every non-trivial test session, append to the daily ledger under `testing/daily/`.
- Keep application/production code out of Tester changes unless the user explicitly changes the mission.
