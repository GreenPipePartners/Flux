# Performance Persistance

This file records persistent data required to keep performance tests repeatable.

The filename intentionally uses `persistance` to match the project file contract requested for the Performance agent.

Owned by the `performance` OpenCode agent.

## Persistent Data Inventory

### Flux.sim POST synchronous gateway work scaffold

- **Test name:** Flux.sim POST synchronous gateway work scaffold
- **Data location:** `tests/test_sim_performance_gateway_post_scaffolding.py` contains the
  expected current sync-work inventory; the scanned source is
  `web/Flux/src/flux/sim/views.py`.
- **Data owner:** Performance agent for the test inventory; Flux.sim owners for the source
  handlers.
- **Generation command:** None.
- **Source system or fixture source:** Repository source only.
- **Refresh rules:** Update the expected inventory whenever sim POST handlers add, remove,
  rename, or relocate heavy sync operations. Remove the strict xfail when the async/job
  boundary makes the zero-inline-heavy-work contract pass.
- **Sensitivity or production-data concerns:** None; no production data or live gateway
  traces are used.
- **Minimum data needed for repeatability:** The sim views source file and the static list
  of known heavy sync operation names.
- **Environment or service assumptions:** Python test environment with pytest; no database,
  Ignition gateway, trial/license state, or network service required.

For each requirement, record:

- test name
- data location
- data owner
- generation command, if any
- source system or fixture source
- refresh rules
- sensitivity or production-data concerns
- minimum data needed for repeatability
- environment or service assumptions
