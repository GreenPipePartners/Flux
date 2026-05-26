# Test Audit

## Scope

Follow-up daily holistic test review for Flux on 2026-05-24 after converting hidden live-test skips into explicit Flux.test outcomes. Covered the Flux.test runner/manifest, root manifest tests, live Fluxy/Ignition, sim-to-Ignition, selected web live integration, closed-loop Fluxolot acceptance, and the known full-web provider-tree failure.

## Executive Summary

Flux.test now fails successful subprocesses that report zero tests or all selected tests skipped. Hidden live gates were moved into manifest requirements/live-audit defaults, Fluxy PostgreSQL coverage is split into an explicitly blocked suite, sim integration runs in an environment that can import both `flux-sim` and `fluxy`, and web integration now uses pytest selections instead of Django tag discovery.

Latest strict live profile result:

- `integration-fluxy`: passed, `52 passed, 112 deselected`, no PostgreSQL skips hidden in the suite
- `integration-fluxy-postgres`: blocked, missing `FLUXY_POSTGRES_ENABLED`
- `integration-sim`: passed, `1 passed`
- `integration-web`: failed, `4 passed, 1 failed`
- `closed-loop`: passed, `2 passed`

Remaining real blockers:

- `flux.serve.test_integration_field_supervisor::test_field_supervisor_multi_process_devices_read_through_fluxy` starts a FieldAgent OPC UA server, but Ignition reports the OPC connection as `FAULTED`.
- `flux.base.tests.BaseTagModelTests.test_provider_tree_marks_sim_selection` remains the sole full-web pytest failure.
- PostgreSQL integration is explicit and blocked until PostgreSQL env/service is configured.

No token values or credentials were printed in this report.

## Commands Run

- **Working directory:** `/home/bobby/Projects/11006-PRW-flux/web/Flux`
  - **Command:** `uv run pytest ../../tests/test_flux_test_manifest.py -q`
  - **Outcome:** Passed
  - **Result:** `18 passed`; validates new live-audit gates, manifest suites, and zero-test/all-skipped failure detection.

- **Working directory:** `/home/bobby/Projects/11006-PRW-flux`
  - **Command:** `uv run python test/runner.py activate-ignition --execute`
  - **Outcome:** Passed
  - **Result:** `Clicked Reset Trial.`

- **Working directory:** `/home/bobby/Projects/11006-PRW-flux`
  - **Command:** `uv run python test/runner.py --live-audit-env integration-sim --execute`
  - **Outcome:** Passed after activation retry
  - **Result:** `1 passed`; prior all-skip behavior now fails loudly until activation/gates are correct.

- **Working directory:** `/home/bobby/Projects/11006-PRW-flux`
  - **Command:** `uv run python test/runner.py --live-audit-env integration-fluxy --execute`
  - **Outcome:** Passed
  - **Result:** `52 passed, 112 deselected`; PostgreSQL tests are excluded from this core suite and represented by `integration-fluxy-postgres`.

- **Working directory:** `/home/bobby/Projects/11006-PRW-flux`
  - **Command:** `uv run python test/runner.py --live-audit-env integration-web --execute`
  - **Outcome:** Failed
  - **Result:** `4 passed, 1 failed`; failure is supervisor OPC state `FAULTED`.

- **Working directory:** `/home/bobby/Projects/11006-PRW-flux`
  - **Command:** `uv run python test/runner.py --live-audit-env --profile live --execute`
  - **Outcome:** Failed overall, correctly
  - **Result:** Fluxy passed, PostgreSQL blocked, sim passed, web failed on supervisor OPC, closed-loop passed.

## Tests Added Or Updated

- **Updated:** `test/flux_test.py`
  - `--live-audit-env` now sets sim/field/live integration gates.
  - Zero-test and all-skipped successful subprocess output is treated as suite failure.
  - Live profile includes `integration-fluxy-postgres` as an explicit suite.
- **Updated:** `test/manifest.toml`
  - `integration-fluxy` excludes PostgreSQL tests to avoid hidden optional skips.
  - Added `integration-fluxy-postgres` with explicit `FLUXY_POSTGRES_ENABLED` gate.
  - `integration-sim` runs the self-contained sim-to-Ignition test from `web/Flux`.
  - `integration-web` runs pytest integration selections instead of Django tag discovery.
- **Updated:** `tests/test_flux_test_manifest.py`
  - Covers new live-audit gates and failed zero-test/all-skipped output.
- **Updated:** `fluxy/tests/test_integration_scripting_run_function_file.py`
  - Uses the existing eventual runner after deploy/request-scan in the deploy/run/delete cycle.
- **Updated:** `test/README.md`
  - Documents the activation command and no hidden all-skipped/zero-test success policy.

## Failures And Suspected Causes

### Flux.field supervisor OPC fault

- **Test:** `test_field_supervisor_multi_process_devices_read_through_fluxy`
- **Observed:** FieldAgent starts and logs an endpoint such as `opc.tcp://0.0.0.0:4872/flux/sim/supervised-field`, but Ignition reports OPC server state `FAULTED`.
- **Failure class:** Real live integration failure, not a skip/discovery artifact.
- **Confidence:** High.

### Flux.base provider-tree partial selection

- **Test:** `flux.base.tests.BaseTagModelTests.test_provider_tree_marks_sim_selection`
- **Observed:** `tree.nodes[0].partial` is false after selecting `Area/Device01`.
- **Likely cause:** Selection aggregation treats `Area` as fully selected when all known children are effectively selected, while the test expects exact-selection boundaries to keep ancestors partial.
- **Failure class:** Product/test contract drift.
- **Confidence:** High.

### PostgreSQL integration blocked

- **Suite:** `integration-fluxy-postgres`
- **Observed:** blocked by missing `FLUXY_POSTGRES_ENABLED`.
- **Failure class:** Explicit external-service gate.
- **Confidence:** High.

## Blockers

- Supervisor FieldAgent OPC connection faults in Ignition.
- Provider-tree exact-selection semantics need product/test decision before full web pytest can be green.
- PostgreSQL integration needs PostgreSQL env/service configured.
- Comp Surface browser coverage is still incomplete outside the current manifest e2e suite.

## Autonomy Recommendations

- Keep optional live surfaces split into explicit suites with `required_env` gates.
- Do not reintroduce Django `manage.py test --tag integration` for pytest-marker integration files unless Django tags are added.
- Investigate the supervisor OPC `FAULTED` state next.
- Resolve provider-tree selection semantics and rerun full web pytest.

## Next Test Targets

- `uv run python test/runner.py --live-audit-env integration-web --execute`
- `uv run pytest src/flux/base/tests.py -q` from `web/Flux`
- `uv run pytest src -q` from `web/Flux`
