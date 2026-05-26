# Performance Tests

This file catalogs repeatable performance tests owned by the `performance` OpenCode agent.

## Test Catalog

### Flux.sim POST synchronous gateway work scaffold

- **Sensitive area covered:** Flux.sim HTTP POST handlers that currently perform provider
  imports, Ignition tag deletion, rehydration backing materialization, rehydration plan
  construction, and gateway tag configure/delete work inline.
- **Test file:** `tests/test_sim_performance_gateway_post_scaffolding.py`
- **Command:** `uv run pytest ../../tests/test_sim_performance_gateway_post_scaffolding.py -q -rx`
- **Working directory:** `/home/bobby/Projects/11006-PRW-flux/web/Flux`
- **Required data or service state:** None. Static AST scan of
  `web/Flux/src/flux/sim/views.py`; no live Ignition gateway, database, or fixtures.
- **Measurement method:** Finds calls to known heavy sync operations inside
  `@require_POST` handlers. One test records the current debt inventory; one strict xfail
  test encodes the target contract that POST handlers do not run gateway IO or
  rehydration work inline.
- **Threshold or regression signal:** Current inventory must stay explicit while the debt
  exists. Target contract is zero heavy sync calls inside sim POST handlers; it is strict
  xfail until an async/job boundary exists.
- **Expected stability limits:** Deterministic source scan; timing signal is limited to test
  execution time only and does not measure gateway latency.
- **Known blockers:** Requires an application seam such as a durable job queue/background
  worker or gateway command service before the target zero-sync-work contract can pass.

For each test, record:

- name
- sensitive area covered
- command
- working directory
- required data or service state
- measurement method
- threshold or regression signal
- expected stability limits
- known blockers
