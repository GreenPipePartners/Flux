# Performance Report

This file records the latest performance test run, suspected failure causes, and recommendations.

Owned by the `performance` OpenCode agent.

## Latest Run

- **Date:** 2026-05-23
- **Command:** `uv run pytest ../../tests/test_sim_performance_gateway_post_scaffolding.py -q -rx`
- **Working directory:** `/home/bobby/Projects/11006-PRW-flux/web/Flux`
- **Data inputs:** Static source scan of `web/Flux/src/flux/sim/views.py`.
- **Service state:** No live Ignition gateway, database, or network service required.
- **Result:** `1 passed, 1 xfailed in 0.02s`

## Results

- Added a deterministic AST scaffold for sim POST handlers.
- Current debt inventory test passed, confirming these inline operations remain visible:
  - `import_provider_json`: `import_provider_json_bytes` at `flux/sim/views.py:234`
  - `import_provider_ignition`: `fluxy.Fluxy` and `import_provider_from_fluxy` at
    `flux/sim/views.py:253-254`
  - `remove_ignition_sim_tags`: `fluxy.Fluxy` and `delete_tag_branch` at
    `flux/sim/views.py:275-276`
  - `apply_selection`: `fluxy.Fluxy`, `delete_rehydrated_paths`,
    `materialize_rehydration_backing`, `build_rehydration_plan`, another `fluxy.Fluxy`,
    and `apply_rehydration_plan` at `flux/sim/views.py:342-363`
- Target zero-inline-heavy-work contract is present as strict xfail:
  `test_sim_post_handlers_do_not_run_heavy_gateway_or_rehydration_work_inline`.

## Suspected Failure Causes

- **High confidence:** Flux.sim POST handlers are doing orchestration and execution in the
  same request path. Evidence: static source scan found gateway-client construction,
  provider import, tag delete, rehydration backing materialization, plan construction, and
  configure calls directly under `@require_POST` view functions.
- **Medium confidence:** User-visible request latency and timeout risk will scale with
  provider size, gateway round trips, and rehydration/tag configure volume. Evidence is
  structural rather than timed; no live gateway timing was collected in this run.
- **Not proven in this run:** Whether the dominant cost is gateway IO, local database
  materialization, JSON parsing, or tag configuration payload size for a specific provider.

## Recommendations

- Introduce an explicit async/job boundary for sim import, delete, and rehydrate/configure
  POSTs: persist intent, return a job/status surface, and let a worker perform gateway IO.
- Keep gateway operations batch-oriented: block tag deletes/configures and one provider
  import job per request, with counters for requested, completed, failed, and retried work.
- After the seam exists, remove the xfail and make the zero-inline-heavy-work test a normal
  passing regression guard.
