# Test Log

This is the project-level test intent log for Flux.

Owned by the `tester` OpenCode agent.

Use this file to preserve why tests exist, what cases they cover, and what context future test work should retain.

## Test Intent Entries

### 2026-05-23

- Created the Tester agent utility and initialized the project-level test intent log.
- Superseded by later entries as Tester added/updated test scaffolding.

### 2026-05-23 - Broad test audit and Flux.sim POST scaffold

- Test names:
  - `tests/test_sim_performance_gateway_post_scaffolding.py::test_sim_post_handlers_do_not_run_heavy_gateway_or_rehydration_work_inline`
  - `tests/test_sim_performance_gateway_post_scaffolding.py::test_sim_post_handler_sync_work_inventory_stays_empty`
- Behavior or risk protected:
  - Flux.sim HTTP POST handlers must not perform heavy gateway IO, provider import,
    Ignition tag deletion, rehydration backing materialization, rehydration plan building,
    or gateway configure operations synchronously before returning the HTTP response.
- Cases covered:
  - Static scan of every `@require_POST` handler in `web/Flux/src/flux/sim/views.py`.
  - Known heavy operations include `fluxy.Fluxy`, provider import helpers, tag deletion,
    rehydration backing, plan build, and apply-configure functions.
  - The expected inventory is now empty after the sim job seam was introduced.
- Fixtures/data/services required:
  - No database, fixture, Ignition gateway, FieldAgent, or network service required.
  - The test reads only repository source.
- Reason added:
  - Architect called out heavy synchronous gateway work in sim views. The scaffold first
    documented the debt, then was updated during this audit after the async/job seam landed.
- Maintenance notes:
  - Preserve this as a cheap root-suite guard. If a new heavy operation is added to sim POST
    handlers, either move it behind the job seam or add it to the scan list only with an
    explicit decision and matching audit note.
  - `test_audit.md` now records the broad 2026-05-23 run, current provider-tree failure,
    live Ignition trial-expiration blocker, and e2e/integration environment gaps.

### 2026-05-23 - Tester bulk profile shortcuts

- Test names:
  - `tests/test_flux_test_manifest.py::test_main_lists_named_profiles`
  - `tests/test_flux_test_manifest.py::test_main_profile_selects_suite_bundle_without_running`
  - `tests/test_flux_test_manifest.py::test_main_profile_json_reports_selected_suites`
  - `tests/test_flux_test_manifest.py::test_profile_suite_names_deduplicates_multiple_profiles`
- Behavior or risk protected:
  - Tester agents can run many suites through one safe project-owned command instead of
    spending one agent step per test command.
  - Profile selection stays deterministic and deduplicated when profiles are combined.
- Cases covered:
  - Profile listing includes `fast`, `web`, `live`, and `audit` bundles.
  - `--profile fast` reports only the fast bundle without running commands by default.
  - `--profile web --json` emits the expected suite order for downstream audit tooling.
  - Multiple profiles deduplicate shared suites such as `django-check`.
- Fixtures/data/services required:
  - Root manifest only. These tests do not execute product test suites.
- Reason added:
  - The tester agent repeatedly hit maximum-step limits while issuing individual test
    commands. Named profiles move orchestration into `test/runner.py` so one allowed command
    can run broad coverage sequentially.
- Maintenance notes:
  - Preferred tester command: `uv run python test/runner.py --profile fast --execute`.
  - Verified fast profile from `web/Flux` with
    `uv run python ../../test/runner.py --profile fast --execute`; it passed Django check,
    root, mine, build, sim non-integration, and Fluxy non-integration suites in one agent
    command.
  - The allowlist should permit `uv run python test/runner.py*` for tester agents.
  - The main Flux CLI still needs a future `flux test` wrapper if we want the shorter
    `flux test fast` style command.

### 2026-05-23 - Audit continuation: route migration failures

- Test names:
  - `flux.trace.tests.TraceSmokeTests.*`
  - `dashboard.tests.*`
  - `web/Flux` full pytest via `uv run pytest src -q`
- Behavior or risk protected:
  - Flux trace/chart routes should remain navigable from dashboard and should serve the
    expected HTML/JSON endpoints without breaking template URL reversal.
- Cases covered:
  - `/trace/*` page and payload routes currently redirect to `/charts/*`.
  - Dashboard templates still reverse `trace:*` names, causing `NoReverseMatch` because
    `flux.urls` no longer registers the `trace` namespace.
  - Focused `flux.live.tests` and `flux.sim.tests` still pass, narrowing the issue to trace
    route naming/compatibility and dashboard links.
- Fixtures/data/services required:
  - Django test database only; no Ignition gateway required for the observed route failures.
- Reason added:
  - Continuing the broad audit exposed new failures after the Flux.trace -> Flux.charts
    routing change.
- Maintenance notes:
  - Preserve either a compatibility `trace` namespace or update tests/templates together to
    the new `charts:*` contract. Avoid leaving dashboard links on a namespace that is not
    registered.
  - The tester shortcut runner exists, but the current agent allowlist still blocks
    `uv run python test/runner.py*`; grant that permission before expecting Tester to use
    the bulk profiles in normal audits.

### 2026-05-24 - Broad audit refresh

- Test names/areas:
  - Root: `tests/test_flux_cli.py`, `tests/test_flux_test_manifest.py`,
    `tests/test_sim_performance_gateway_post_scaffolding.py`
  - Packages: `mine`, `build`, `sim`, and `fluxy` non-integration suites
  - Web: `uv run pytest src -q`, explicit Django app-label suite, and Flux.test
    `fast`, `web`, `e2e`, and `live` profiles
  - Failure focus: `flux.base.tests.BaseTagModelTests.test_provider_tree_marks_sim_selection`
  - Comp Surface discovery: dashboard has Playwright mode-control coverage; trace/sim/live
    Comp Surfaces still need equivalent integrated browser tests.
- Behavior or risk protected:
  - Current broad test health and blockers are preserved in `test_audit.md` so future agents
    do not re-triage old route-migration failures that no longer reproduce.
  - Provider-tree selection UI semantics remain visible as the sole broad web failure.
- Cases covered:
  - Root tests passed: `35 passed`.
  - `mine` passed: `14 passed`; `build` passed: `4 passed`; `sim` passed with live skips:
    `36 passed, 2 skipped`; `fluxy` non-integration passed: `112 passed, 57 deselected`.
  - Full web pytest failed with exactly one failure: `1 failed, 236 passed, 22 skipped`.
  - Web profile failed only in `unit-web`; focused live/trace/opt/cell profile suites passed.
  - E2E/live profiles were manifest-blocked by missing env rather than run against live services.
- Fixtures/data/services required:
  - Non-live tests use local test databases, temp files, and mocked/non-live clients.
  - Browser tests require `FLUX_PLAYWRIGHT=1` and installed browser binaries.
  - Live suites require Fluxy/Ignition/FieldAgent env and disposable-resource approval.
- Reason added:
  - User requested a complete test audit continuation on 2026-05-24.
- Maintenance notes:
  - `uv run python test/runner.py --profile fast --execute` is now allowed and verified.
  - `flux test --json` still is not implemented; prefer `test/runner.py` until the CLI wrapper exists.
  - Plain `uv run python manage.py test --exclude-tag integration --noinput` discovered zero tests;
    use `uv run pytest src -q` or explicit Django app labels for broad web coverage.
  - The old Flux.trace/Flux.charts dashboard failures from 2026-05-23 did not reproduce in this audit;
    preserve the current passing trace/dashboard signal unless a new route contract changes.

### 2026-05-24 - Live audit runner env shortcut

- Test names:
  - `tests/test_flux_test_manifest.py::test_live_audit_env_loads_dotenv_and_sets_gates`
  - `tests/test_flux_test_manifest.py::test_main_live_audit_env_unblocks_e2e_gate`
- Behavior or risk protected:
  - Tester agents can request a complete e2e/live audit through the safe Flux.test runner without
    shell-sourcing env files or placing `FLUXY_TOKEN` directly in a command string.
- Cases covered:
  - `--live-audit-env` loads project env files when present, preserves provided `FLUXY_BASE_URL`,
    and sets `FLUX_PLAYWRIGHT=1` plus `FLUX_FULL_INTEGRATION=1`.
  - Runner env gates are computed after live-audit env setup, so e2e suites become defined when
    `FLUX_PLAYWRIGHT` is supplied by the shortcut.
- Fixtures/data/services required:
  - Temporary manifest/env files only; no live Ignition gateway, browser, or database required.
- Reason added:
  - A truly complete live audit needs `FLUXY_BASE_URL`, `FLUXY_TOKEN`, `FLUX_PLAYWRIGHT=1`, and
    `FLUX_FULL_INTEGRATION=1`; this gives Tester a single allowed runner command for that setup.
- Maintenance notes:
  - Preferred complete live-audit command: `uv run python test/runner.py --live-audit-env --profile e2e --profile live --execute`.
  - `FLUXY_TOKEN` remains intentionally external; do not print token values in audit reports.

### 2026-05-24 - Daily holistic review and Flux.cell phone e2e maintenance

- Test names/areas:
  - `web/Flux/src/flux/cell/test_e2e_playwright.py::CellPlaywrightTests::test_phone_simulator_swipes_right_next_and_left_previous`
  - Root `tests/`, package-local `mine`, `build`, `sim`, `fluxy`, `deep`, web/Django `src`, and Flux.test `fast`, `web`, `e2e`, and `live` profiles.
- Behavior or risk protected:
  - The Flux.cell phone-demo Playwright test now protects the current swipe-card contract rather
    than a removed visible counter.
  - Daily broad quality context is preserved in `test_audit.md`, including the current provider-tree
    failure and live Ignition trial blocker.
- Cases covered:
  - Phone demo has no site header, exposes the Flux Home link, renders no `data-cell-phone-counter`,
    renders chart series, starts on Pump 101, swipes right to Tank 101, and swipes left back to Pump 101.
  - Fast profile passed; deep passed; web profile failed only in `unit-web`; full web pytest failed
    only in `flux.base.tests.BaseTagModelTests.test_provider_tree_marks_sim_selection`.
  - Live-audit profile passed e2e after the Flux.cell update but live Fluxy/closed-loop failed with
    HTTP 402 `Trial Expired` from the Ignition/Fluxy WebDev bridge.
- Fixtures/data/services required:
  - Flux.cell e2e uses `seed_demo_cell_bundle()`, Django live server, Playwright Chromium, and
    `FLUX_PLAYWRIGHT=1` supplied through `test/runner.py --live-audit-env`; it does not require Ignition.
  - Live suites require Fluxy/Ignition/FieldAgent env and an unexpired gateway trial/license; token
    presence was observed only as a gate and token value was not recorded.
- Reason added:
  - User requested a daily holistic test review. The review discovered a stale e2e assertion that
    conflicted with unit coverage asserting the counter is absent.
- Maintenance notes:
  - Preserve the no-counter phone-demo contract unless the UI intentionally reintroduces an accessible
    position indicator; if it does, update unit and e2e expectations together.
  - Do not treat `integration-sim` and `integration-web` live-profile green statuses as meaningful
    until all-skipped/zero-test execution is handled by the harness.
  - Resolve the provider-tree partial-selection contract next; it remains the only non-live broad web failure.

### 2026-05-24 - Ignition activation suite and live manifest recovery

- Test names/areas:
  - `test/manifest.toml` suite `activate-ignition`
  - `test/manifest.toml` suite `integration-fluxy`
  - `tests/test_flux_test_manifest.py::test_repo_manifest_loads_required_first_pass_suites`
  - Live profile command: `uv run python test/runner.py --live-audit-env --profile e2e --profile live --execute`
- Behavior or risk protected:
  - Tester can reset an expired local Ignition trial through the auditable Flux.test runner when direct
    script execution is blocked by the current opencode session permissions.
  - Fluxy integration tests run from the package directory so relative defaults like
    `../ignition_flux_project` resolve to the intended project link.
- Cases covered:
  - `activate-ignition` initially exposed missing Selenium, then passed with transient Selenium and clicked
    `Reset Trial`.
  - Fluxy live integration passed from `fluxy/`: `52 passed, 5 skipped, 112 deselected`.
  - Corrected aggregate e2e/live profile passed for e2e, Fluxy integration, closed-loop acceptance, and the
    existing sim/web entries; sim/web still need false-green cleanup because sim all-skips and web runs zero tests.
  - Full web pytest still fails only in `BaseTagModelTests.test_provider_tree_marks_sim_selection`.
- Fixtures/data/services required:
  - Local Ignition Gateway at the configured/default gateway URL.
  - Selenium-compatible Chromium/WebDriver available through transient `uv run --with selenium` execution.
  - `FLUXY_TOKEN` gate present for live suites; token value was not recorded.
- Reason added:
  - User asked Tester to use activation privileges and complete Ignition/live testing after the prior trial-expired blocker.
- Maintenance notes:
  - Use `uv run python test/runner.py activate-ignition --execute` before live retries when Fluxy reports HTTP 402 `Trial Expired`.
  - Preserve `integration-fluxy` `cwd = "fluxy"` unless tests stop depending on package-relative defaults.
  - Add runner detection for all-skipped or zero-test live suites; current green statuses for `integration-sim` and
    `integration-web` are not meaningful coverage.

### 2026-05-24 - Strict live skip barriers converted to explicit outcomes

- Test names/areas:
  - `test/flux_test.py::successful_output_without_executed_tests`
  - `tests/test_flux_test_manifest.py::test_main_execute_zero_tests_success_is_failed`
  - `tests/test_flux_test_manifest.py::test_main_execute_all_skipped_success_is_failed`
  - `test/manifest.toml` suites `integration-fluxy`, `integration-fluxy-postgres`, `integration-sim`, and `integration-web`
  - `fluxy/tests/test_integration_scripting_run_function_file.py::test_deploy_run_delete_then_run_fails_for_hello_world_function_file`
- Behavior or risk protected:
  - Flux.test no longer accepts zero-test or all-skipped commands as green.
  - Optional PostgreSQL coverage is explicit and blocked by env instead of hidden as skips inside the core Fluxy live suite.
  - Sim and web live integration suites execute real tests under environments that satisfy their imports/gates.
- Cases covered:
  - Manifest tests pass: `18 passed`.
  - `integration-fluxy` passes without PostgreSQL skips: `52 passed, 112 deselected`.
  - `integration-sim` passes with real execution: `1 passed`.
  - `integration-web` now runs five tests and fails on a real supervisor OPC fault: `4 passed, 1 failed`.
  - Strict live profile reports `integration-fluxy-postgres` as blocked when `FLUXY_POSTGRES_ENABLED` is absent.
- Fixtures/data/services required:
  - Live Ignition/Fluxy and FieldAgent for sim/web/closed-loop suites.
  - PostgreSQL suite requires separate PostgreSQL env/service gate.
- Reason added:
  - User correctly called out that skipped tests should not be treated as completed testing.
- Maintenance notes:
  - Keep optional live surfaces split into explicit suites with `required_env` gates.
  - Do not reintroduce Django `manage.py test --tag integration` for pytest-marker integration files unless Django tags are added.
  - Investigate the remaining supervisor OPC `FAULTED` state as a real integration issue.

### 2026-05-24 - Fluxolot live supervisor recovery

- Test names/areas:
  - `src/flux/serve/tests.py::FieldSupervisorTests`
  - `test/manifest.toml` suites `integration-web`, `closed-loop`, and `live`
  - `src/flux/serve/test_full_integration_fluxolot_fishtank.py`
- Behavior or risk protected:
  - Supervised FieldAgent processes use per-endpoint OPC UA certificate stores so concurrent Sir/Missus Fluxolot processes do not race over shared `pki/own` certificate state.
  - Fluxolot acceptance tests no longer delete the operator-facing `[default]FluxolotFishtank` Ignition folder.
- Cases covered:
  - `FieldSupervisorTests` passed: `16 passed`.
  - `integration-web` passed: `5 passed`.
  - `closed-loop` passed after isolation: `2 passed`.
  - Persistent Sir and Missus Fluxolot OPC connections both reported `CONNECTED`; pasted Missus pump/treat-feeder paths read `Good`.
  - Full live profile now passes Fluxolot-related suites; remaining failure was unrelated Fluxy UserDB cleanup in `tests/test_integration_user.py::test_userdb_role_and_user_closed_loop`.
- Fixtures/data/services required:
  - Live Ignition/Fluxy, FieldAgent supervisor, and local Fluxolot persistent fixture.
- Reason added:
  - Missus Fluxolot live cards showed `Bad_NotFound` then `Uncertain_InitialValue` because the shared operator Ignition folder had been removed by acceptance cleanup and the Missus supervised FieldAgent process failed during shared certificate-store startup.
- Maintenance notes:
  - Do not point acceptance cleanup at `[default]FluxolotFishtank`; keep test-only live validation in `FluxolotFishtankAcceptance`.
  - Supervisor-managed FieldAgents should keep isolated certificate stores under `.runtime/field-agent/pki/<endpoint>`.

## Entry Template

```markdown
### YYYY-MM-DD - <test file or area>

- Test names:
- Behavior or risk protected:
- Cases covered:
- Fixtures/data/services required:
- Reason added:
- Maintenance notes:
```
