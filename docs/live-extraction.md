# Live Ignition Extraction Trial

The live extraction trial stays strictly at the Fluxy interface level.

It can close the loop for tag state:

- Build source tags in a live namespace.
- Populate live tag values and historian points.
- Extract tag configuration and raw history.
- Recreate tags in a sim namespace.
- Replay history into the sim namespace.
- Delete source and target tag branches.
- Verify the deleted tags no longer read Good.

It also reports whether raw historian rows are still queryable after tag deletion.

It cannot close the loop for raw historian data points using public Fluxy/Ignition APIs.

## Limitation

Ignition exposes public APIs for historian writes and reads:

- `system.historian.storeDataPoints`
- `system.historian.queryRawPoints`
- metadata and annotation store/query/delete APIs

Ignition does not expose a public `deleteDataPoints` API for raw historian samples. Fluxy therefore cannot delete raw historian data points without reaching into the historian database directly.

That direct deletion is intentionally not part of this trial because it depends on the historian storage backend:

- Core Historian table shape differs from SQL historian backends.
- SQL historian cleanup requires database-specific table and partition handling.
- A production live server may use a different datasource, schema, retention policy, or historian provider.

Fluxy can identify the Ignition datasource type through `fx.db.get_connection_info(name)`. On the local gateway this returns `DBType`, for example:

```text
FluxyPostgres -> POSTGRES
FluxyHello    -> SQLITE
```

That is enough to choose a manual cleanup adapter such as `postgres`, `sqlite`, or later `mssql`. The adapter still owns database-specific table discovery, partition handling, and safe deletion predicates.

## Current Trial Shape

The current trial uses one local Ignition gateway as both source and target:

```text
[default]FluxLiveSourceTrial/* -> extract -> [default]FluxSimReplayTrial/*
```

Steps:

1. Delete prior source and target trial tag folders.
2. Build source memory tags.
3. Write current source tag values in one `write_blocking` call.
4. Populate Core Historian source history with `storeDataPoints`.
5. Wait briefly for source history to become query-visible.
6. Extract source tag config through `getConfiguration`.
7. Extract source history through `queryRawPoints`.
8. Configure target tags through `configure`.
9. Replay target history through `storeDataPoints`.
10. Verify target tags read Good.
11. Verify target history is query-visible.
12. Delete source and target tag branches.
13. Verify source and target tags no longer read Good.
14. Report remaining queryable historian rows.

Important Ignition behavior discovered during this trial:

- Tall historian query rows can return synthetic paths like `value_0`, `value_1`, and `value_2`.
- The extractor maps those rows back to requested tag order.
- Fresh historian writes may not be immediately query-visible.
- The command/test wait briefly for source and target history rows before asserting.

## Cleanup Adapter Direction

Raw-history cleanup needs manual adapters selected by datasource type:

```text
DBType=POSTGRES -> Postgres SQL historian cleanup adapter
DBType=SQLITE   -> SQLite SQL historian cleanup adapter
DBType=MSSQL    -> SQL Server SQL historian cleanup adapter
```

Adapter responsibilities:

- identify historian tag IDs for the exact trial source/target paths
- identify relevant partition/data tables for the trial time window
- delete only rows matching the trial tag IDs and timestamps
- verify no rows remain queryable through Fluxy
- avoid deleting production history outside the trial namespace and time window

Until those adapters exist, `--cleanup` is only fully closed-loop for tag state. It intentionally reports remaining raw historian rows instead of hiding the limitation.

## Commands

Run the Fluxy-level closed-loop trial:

```bash
uv run python web/Flux/manage.py trial_live_extraction --cleanup
```

This verifies tag cleanup and reports remaining historian rows as a known Fluxy-level limitation.

Run the gated integration test against the local gateway:

```bash
FLUX_LIVE_EXTRACTION_INTEGRATION=1 uv run pytest web/Flux/src/flux/sim/test_integration_live_extract.py -q
```

To prove that public Fluxy APIs cannot fully clean raw history on the current gateway, run:

```bash
uv run python web/Flux/manage.py trial_live_extraction --cleanup --require-history-cleanup
```

That command is expected to fail if historian rows remain queryable.
