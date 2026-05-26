# Architecture Review

## Scope

Reviewed the remaining `base_*` tables in the PostgreSQL `public` schema and compared them to current Flux.base model ownership, Flux.sim/Flux.serve usage, and the newer schema-qualified `base`, `sim`, `cell`, `plane`, and `bridge` tables.

Evidence inspected:

- `web/Flux/src/flux/base/models.py`
- `web/Flux/src/flux/base/services.py`
- `web/Flux/src/flux/base/field_config.py`
- `web/Flux/src/flux/base/field_selectors.py`
- `web/Flux/src/flux/base/migrations/0001_initial.py`, `0002_fieldagent_config_to_base.py`, `0003_sim_device_catalog.py`, `0006_simserver_tagprovider.py`, `0008_tagselection_config.py`, `0010_kernel_device_tag.py`, `0011_drop_legacy_device_tag_tables.py`, `0012_entity.py`
- `web/Flux/src/flux/sim/models.py`
- `web/Flux/src/flux/sim/output.py`, `rehydrate.py`, `tag_data_ingest.py`, `field_bridge.py`, `testing.py`, `views.py`
- `web/Flux/src/flux/serve/field_supervisor.py`, `monitor.py`, `server_commands.py`
- PostgreSQL catalog inspection of `public.base_%` tables, row counts, relation sizes, and FKs.

## Executive Summary

Do **not** drop the remaining `public.base_*` tables as dead legacy tables. They are still active, but most no longer belong logically to Flux.base.

Implementation note: phase 1 moved the Flux.sim provider catalog cluster into schema-qualified `sim.*` tables. Phase 2 moved endpoint config to `sim.endpoint` and FieldAgent heartbeat evidence to `serve.sim_agent_heartbeat`. No `public.base_*` tables should remain after migrations are applied.

The current split is implemented:

- `base.device`, `base.tag`, and `base.entity` are now correctly schema-qualified kernel identity tables.
- The former `public.base_*` catalog/endpoint/runtime tables now have schema-owned names, with compatibility aliases left in Python where needed.

Recommended direction: keep the data, then migrate/rename by ownership cluster.

| Current public table | Rows | Need? | Target direction |
|---|---:|---|---|
| `base_tagnode` | 510,073 | Yes | Move to `sim.provider_node` / `sim.catalog_node` |
| `base_tagprovider` | 2 | Yes | Move to `sim.provider` / `sim.provider_catalog` |
| `base_tagselection` | 4 | Yes, or merge carefully | Move to `sim.provider_selection`; reconcile with dormant `sim_simproviderselection` |
| `base_simserver` | 3 | Yes short-term | Move/merge into `sim.server` or `sim.endpoint` |
| `base_simdriver` | 7 | Yes short-term | Move to `sim.driver` or replace with a bounded code registry |
| `base_fieldendpoint` | 8 | Yes | Implemented as `sim.endpoint`; runtime truth still should not rely on stored endpoint status alone |
| `base_fieldagentheartbeat` | 8 | Yes | Implemented as `serve.sim_agent_heartbeat` |

## Findings

### High — `public.base_*` tables are active and unsafe to remove directly

**References:** `web/Flux/src/flux/base/models.py:51-299`, `web/Flux/src/flux/sim/models.py:68-190`, `web/Flux/src/flux/sim/output.py`, `web/Flux/src/flux/serve/monitor.py`

Postgres currently has these `public.base_*` tables:

- `base_fieldagentheartbeat`
- `base_fieldendpoint`
- `base_simdriver`
- `base_simserver`
- `base_tagnode`
- `base_tagprovider`
- `base_tagselection`

They still back active Django models and active selectors/importers. `base_tagnode` alone has about `510k` rows and `464 MB` total relation size, so deleting it would erase the imported provider catalog, not merely clean up a naming artifact.

**Architectural risk:** treating app-prefix names as legacy would destroy active Flux.sim provider-tree and FieldAgent endpoint state.

**Minimal corrective direction:** freeze deletion. Move by cluster with schema-qualified migrations and data-preserving `SeparateDatabaseAndState` operations.

### Medium — Flux.base still owns Flux.sim provider catalog tables by accident

**References:** `web/Flux/src/flux/base/models.py:51-238`, `web/Flux/src/flux/base/services.py`, `web/Flux/src/flux/sim/output.py`, `web/Flux/src/flux/sim/rehydrate.py`

`TagProvider`, `TagNode`, `TagSelection`, `SimServer`, and `SimDriver` are conceptually simulation/import catalog tables. Their dominant callers are Flux.sim import, tree browsing, provider selection, output materialization, and rehydration paths.

**Architectural risk:** Flux.base becomes a junk drawer for provider-tree UI state and simulation behavior. This weakens the clean Base kernel direction established by `base.device`, `base.tag`, and `base.entity`.

**Minimal corrective direction:** migrate the provider catalog cluster to `sim` ownership:

- `base_tagprovider` -> `sim.provider` or `sim.provider_catalog`
- `base_tagnode` -> `sim.provider_node` or `sim.catalog_node`
- `base_tagselection` -> `sim.provider_selection`
- `base_simserver` -> `sim.server` or merge into `sim.endpoint`
- `base_simdriver` -> `sim.driver` or a bounded code registry

### Medium — `base_fieldendpoint` mixes desired endpoint config with runtime truth

**References:** `web/Flux/src/flux/base/models.py:255-279`, `web/Flux/src/flux/sim/models.py:73-77`, `web/Flux/src/flux/serve/field_supervisor.py`, `web/Flux/src/flux/serve/monitor.py`

`FieldEndpoint` stores endpoint configuration (`endpoint_url`, URIs, security, enabled) and observed runtime fields (`status`, `last_seen_at`, `last_error`). Its rows are referenced by `sim.DeviceConfig.endpoint`, the FieldAgent supervisor, dashboard runtime views, and serve monitor code.

**Architectural risk:** user-facing runtime truth can drift because configuration rows also carry mutable observed state. We already saw this pattern with `running` needing heartbeat evidence.

**Minimal corrective direction:** keep the table for now, but target a split:

- desired OPC/FieldAgent endpoint config: `sim.endpoint`
- observed process/heartbeat status: `serve.endpoint_runtime` or `serve.sim_agent_heartbeat`

Do not show endpoint `status` as runtime truth without fresh heartbeat/status evidence.

### Medium — `base_fieldagentheartbeat` is needed, but it is Flux.serve evidence, not Base

**References:** `web/Flux/src/flux/base/models.py:282-299`, `docs/Master Design.md:166-177`, `architecture/core_area_files.md:28`, `architecture/daily/architecture_2026-05-25/architecture_2026-05-25.md:187-213`

`base_fieldagentheartbeat` has 8 active rows. It is used by Flux.serve monitor classification and PID/last-seen runtime evidence. Prior architecture review already found `version` and `started_at` are mostly placeholder fields unless FieldAgent emits true self-reports.

**Architectural risk:** storing runtime heartbeat evidence in Base blurs identity/configuration with process supervision and makes stale evidence look canonical.

**Minimal corrective direction:** move the model/table to `serve.sim_agent_heartbeat` or `serve.endpoint_runtime`, then decide whether to keep or drop `version`, `started_at`, and `current_node_count` based on actual FieldAgent self-report needs.

### Medium — `base_tagnode` is large enough to deserve explicit bounds and owner naming

**References:** Postgres row/size inspection; `web/Flux/src/flux/base/models.py:169-216`; `web/Flux/src/flux/base/services.py`

`base_tagnode` contains about `510,073` rows with about `464 MB` total size (`258 MB` table, `203 MB` indexes). This is currently manageable, but it is the dominant remaining `public.base_*` table.

**Architectural risk:** provider-tree import/search/render code can become a silent performance trap if treated like small Base metadata. The table has large-catalog behavior and should be named/owned like a simulation catalog index.

**Minimal corrective direction:** keep it, move it to `sim`, and preserve/verify indexes around provider/parent/depth/sort/tag_type/data_type/value_source. Any UI read path should keep explicit limits and lazy tree loading.

### Low — `base_tagselection` overlaps conceptually with `sim_simproviderselection`

**References:** `web/Flux/src/flux/base/models.py:218-238`, `web/Flux/src/flux/sim/models.py:6-17`

`base_tagselection` is active and has 4 rows. `sim_simproviderselection` exists but currently has 0 rows locally. The names suggest duplicate concepts, though the active implementation mostly uses `TagSelection` with provider FK and purpose/config.

**Architectural risk:** two selection tables can split desired state and confuse sim output jobs.

**Minimal corrective direction:** before moving `base_tagselection`, choose one selection table. Prefer migrating the active `TagSelection` shape into `sim.provider_selection` and dropping/absorbing the dormant `SimProviderSelection` if it remains unused.

## Overloaded Areas

- `flux.base.models`: still holds kernel identity (`Entity`, `Device`, `Tag`) plus sim catalog (`TagProvider`, `TagNode`, `TagSelection`, `SimServer`, `SimDriver`) plus serve/runtime endpoint evidence (`FieldEndpoint`, `FieldAgentHeartbeat`). That is too much for Base.
- `public` schema: still contains active Flux-owned domain tables with old app-prefix names, while newer ownership schemas (`base`, `sim`, `cell`, `plane`, `bridge`) are already in use.
- `FieldEndpoint`: carries both desired endpoint configuration and observed runtime status.

## Boundary Risks

- Flux.base should remain kernel identity and shared reference, not provider-tree UI, simulation driver strategy, endpoint process status, or heartbeat evidence.
- Flux.sim should own imported provider catalogs, provider selections, sim servers/drivers, and desired endpoint/device/tag configuration.
- Flux.serve should own FieldAgent heartbeat/runtime truth and any PID/port/process evidence.
- The `public.base_*` names now actively hide ownership mistakes because tables look like Base even when behavior is Sim/Serve.

## Performance Risks

- `base_tagnode` is the hot structural risk: roughly `510k` rows and `464 MB` total relation size. Keep lazy tree loading, bounded search, and provider-scoped indexes.
- Migrating `base_tagnode` should be done with back-of-envelope cost awareness and ideally measured `ALTER TABLE ... SET SCHEMA`/rename operations in staging. Avoid row-by-row copy migrations.
- `FieldAgentHeartbeat.current_node_count` can become repeated-query churn if recomputed per endpoint in tight supervisor loops without a bounded plan.

## Recommended Next Moves

1. **Do not drop any remaining `public.base_*` tables yet.** They are active.
2. **Document a target schema map before Build migrates:**
   - `base_tagprovider` -> `sim.provider` / `sim.provider_catalog`
   - `base_tagnode` -> `sim.provider_node` / `sim.catalog_node`
   - `base_tagselection` -> `sim.provider_selection`
   - `base_simserver` -> `sim.server` or merge into `sim.endpoint`
   - `base_simdriver` -> `sim.driver` or a code registry
   - `base_fieldendpoint` -> split desired config into `sim.endpoint`
   - `base_fieldagentheartbeat` -> `serve.sim_agent_heartbeat` / `serve.endpoint_runtime`
3. **Migrate provider catalog as one cluster.** It has tight FK ownership and the largest table.
4. **Then migrate/split endpoint runtime.** Keep endpoint config and runtime evidence separate.
5. **Add migration verification:** row counts, FK checks, tree browse/search tests, sim output materialization tests, FieldAgent supervisor JSON parity, and Playwright cleanup coverage for schema-qualified tables.

## Open Questions

- Should `SimServer` survive as a separate concept, or should it become/merge into `sim.endpoint`?
- Should `SimDriver` remain a table for operator-imported mapping, or become a bounded Python registry with only overrides in the database?
- Do we want endpoint heartbeat under `serve.sim_agent_heartbeat` exactly as Master Design currently says, or a more generic `serve.endpoint_runtime` table that can later cover non-sim workers?
- Is `sim_simproviderselection` still planned, or should it be retired when `base_tagselection` moves to `sim.provider_selection`?
