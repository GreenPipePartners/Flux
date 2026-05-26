# Performance Log

This is the operator-facing index and running log for Flux performance work.

Owned by the `performance` OpenCode agent.

## Current Records

- Latest report: `performance/performance_report.md`
- Test catalog: `performance/performance_tests.md`
- Persistent data inventory: `performance/performance_persistance.md`

## Log

### 2026-05-23

- Created the Performance agent utility and initialized the performance record set.
- Replaced the initial empty state with the first Flux.sim performance scaffold.
- Added Flux.sim synchronous POST gateway-work scaffolding in
  `tests/test_sim_performance_gateway_post_scaffolding.py`.
- Captured the current sim POST debt inventory: provider import, Ignition tag deletion,
  and rehydration/configure operations still execute inline before the HTTP response.
- Latest scaffold run: `uv run pytest ../../tests/test_sim_performance_gateway_post_scaffolding.py -q -rx`
  from `web/Flux` passed the inventory test and xfailed the target zero-sync-work contract.
