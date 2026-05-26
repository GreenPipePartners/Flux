# Flux.web
1) Flux.web owns a site-wide display pulse.
   - Default UI refresh cadence: 5 seconds.
   - Implemented with HTMX polling of cached, server-rendered fragments.
   - Flux.web polling must not perform Ignition/Fluxy reads directly.
2) Flux.web renders cached state from Flux.spot, Flux.serve, Flux.opt, Flux.bridge, and Flux.base.
   - Backend freshness is produced by Flux.serve/Flux.opt workers.
   - Flux.web only displays the most recent persisted state.
3) Flux.spot operational surfaces use a default cached refresh cadence of 5 seconds.
   - Backend read lanes are separate from UI polling.
   - Initial backend lane targets: hot 5s, warm 30s, cold 60s.
4) Operational pages should include a compact refresh timer in the hero surface.
   - Shows next Flux.web display refresh.
   - Backend sample/probe freshness belongs in operational cards, not the global display pulse.
   - Stale/offline state must remain visible in the owning app surface.

# Flux.status
Flux.status owns latest operational status evidence.

Status rows are read models written by Flux.serve, Flux.opt, Flux.bridge, and other backend workers. Flux.status does not own domain configuration and does not replace Flux.logs.

### status.latest
Latest status for a Flux entity.
Columns:
- `entity_id -> base.entity`
- `status_kind`
- `observed_state`
- `severity`
- `summary`
- `detail`
- `last_seen_at`
- `stale_after_seconds`
- `source`
- `source_instance`
- bounded `evidence`
- `updated_at`
Unique key:
- `(entity_id, status_kind, source, source_instance)`
Status kinds:
- `connectivity`
- `sampling`
- `freshness`
- `quality`
- `worker`
- `storage`
- `configuration`
Observed states:
- `ok`
- `warning`
- `error`
- `stale`
- `missing`
- `unknown`
- `disabled`
`status.latest` stores current evidence only. Historical status/event retention belongs to future `status.event` or Flux.logs.

# Flux.bridge
Flux.bridge supplies Ignition/Fluxy connectivity

# Flux.opt
Flux.opt plans optimized block reads and cadence for ingestion. Also performs optimization for visualization to improve data display. Flux.opt does not own UI rendering, but can aid gathering UI data packets

# Flux.plane
Flux.plane owns time-series storage and query serving.
### plane.series
Shared data-plane stream for a `base.tag`.
One physical tag should have one Plane series even if used by both Flux.spot and Flux.chart.
Fields:
- `entity_id -> base.entity`
- `base_tag_id -> base.tag`
- `enabled`
- `latest_enabled`
- `history_enabled`
- `sample_interval_ms`
- `storage_key`
- `retention_policy`
- `created_at`
- `updated_at`
### plane.latest
Latest value snapshot for a Plane series.
### plane.window_stat
Precomputed bounded summaries for Spot and dashboard surfaces.
Windows:
- `today`
- `rolling_7d`
- `rolling_30d`
Fields:
- `series_id`
- `window`
- `min_value`
- `max_value`
- `sample_count`
- `window_start`
- `window_end`
- `computed_at`

# Flux.base
1) Flux.base is a postgres-exclusive database layer
2) Flux.base architecturally defines schemas matching Flux namespacing
  - e.g. Flux.bridge tables are located in {schema} `bridge`
3) tables shall follow snake-case structure
  - e.g. the Ignition Bridge table shall be bridge.ignition_bridge
4) owns shared kernel identity

## base
### base.tag
Canonical tag identity

Each known tag path is stored once and linked to `base.entity`.

Base datastore of a tag for Flux. Every tagpath shall be stored in a central table with a guid key. Base.tag stores tag identity and stable source metadata, including:
Fields include:
- `entity_id`
- `provider`
- `tagpath`
- `full_path`
- `data_type`
- `update_rate`
- `enabled`
- optional `device_id`
- optional description
### base.device
Canonical device identity.
Each known device is stored once and linked to `base.entity`.
- name
- device type
- enabled status
- (optional) description
### base.entity
Gives cross-domain tables a stable FK target for status, logs, and references

Columns:
- `guid`
- `kind`
- `natural_key`
- `display_name`
- `retired_at`
- `created_at`
- `updated_at`

Examples of `kind`:
- `base.tag`
- `base.device`
- `plane.series`
- `bridge.connection`
- `serve.worker`
- `field.endpoint`

`base.entity` must stay identity-only. Do not store latest values, status details, UI config, tokens, sampler cadence, or domain-specific metadata here.

## bridge
### bridge.ignition_bridge
Configured bridge gateways are stored in a database table, indicating:
| Column | Type / Shape | Description |
|---|---|---|
| `id` | integer / bigint PK | Django primary key. |
| `name` | varchar(64), unique | Human/stable bridge config name. No default|
| `role` | varchar(20) | Bridge intent: `production` or `simulator`. Database layer constraint|
| `base_url` | URL string | Fluxy WebDev endpoint, e.g. `http://localhost:8088/system/webdev/flux`. |
| `token` | varchar(255), blank allowed | Auth token for Fluxy/WebDev bridge calls. |
| `last_test_ok` | boolean | Whether the last bridge connection test succeeded. |
| `last_test_message` | varchar(255), blank allowed | Result message from last test; currently may include Ignition version text. |
| `last_test_at` | timestamp nullable | When the last connection test ran. |
| `updated_at` | timestamp | Auto-updated whenever the row is saved. |

## serve
### serve.sim_agent_heartbeat
stores the latest Flux.serve runtime evidence for each supervised SimAgent OPC endpoint.
| Column | Description |
|---|---|
| `id` | primary key for the heartbeat/evidence row. |
| `endpoint_id` | FK to the supervised `sim.endpoint`; ties runtime evidence to one configured OPC endpoint. |
| `instance_id` | Stable supervisor/runtime key, currently like `field-agent:<endpoint.id>`. Used to upsert and identify the FieldAgent slot. |
| `process_id` | OS PID last reported by the supervisor. Useful evidence, but not sufficient alone to claim “running.” |
| `last_seen_at` | Last time Flux.serve/supervisor refreshed this row. Primary freshness/staleness signal. |
| `last_error` | Latest FieldAgent/supervisor error evidence, such as process exit or disabled/no longer configured. Used by monitor logic. |
| `current_node_count` | Latest configured/runtime node count for the endpoint. Keep only if we surface it or make it cheap/bounded; otherwise it is a weak candidate for pruning or renaming. |

## sim
Flux.sim owns the simulation catalog and simulation-specific extensions in the dedicated `sim` PostgreSQL schema. Flux.base remains the shared kernel identity layer for `base.device`, `base.tag`, and `base.entity`.

### sim.provider
Imported provider catalog root and summary metadata. Formerly `public.base_tagprovider`.

### sim.provider_node
Imported provider tree nodes, including folders, UDT instances, atomic tags, OPC metadata, raw config, and tree lookup fields. This is a large catalog table and must keep provider-scoped lazy tree/search access. Formerly `public.base_tagnode`.

### sim.provider_selection
Desired imported-provider branch/tag selection state for simulation output. Formerly `public.base_tagselection`.

### sim.server
Simulation OPC server definition/config used by provider catalogs and materialized devices. Formerly `public.base_simserver`.

### sim.driver
Simulation driver/strategy mapping for imported devices. Formerly `public.base_simdriver`.

### sim.endpoint
Desired OPC/FieldAgent endpoint configuration for simulated endpoint processes. Formerly `public.base_fieldendpoint`. Runtime truth belongs to `serve.sim_agent_heartbeat` and status surfaces, not the endpoint row alone.

### sim.device
Supplemental information for devices being simulated, extending from base.device for sim-specific information, such as:
- tag provider
- opc server

### sim.tag
suplemental information for tags being simulated, such as:
- simulation mode
- sim device connection

## cell
Flux.cell owns process-cell configuration in the dedicated `cell` PostgreSQL schema.

### cell.bundle
Import/export package or process-cell collection. Bundles are the CSV/API boundary for moving a related set of cells, points, relationships, sources, and visuals.

### cell.cell
Canonical process object such as a pump, tank, meter, or recovered HMI-derived process card.

### cell.point
Tag/signal membership for a cell. Points define the cached runtime tag path, live inclusion, chart inclusion, role, units, ordering, axis metadata, and visualization hints.

### cell.relationship
Current graph/process relationship between cells, such as `parent`, `child`, `prev_area`, or `next_area`. This is current topology, not an append-only event ledger.

### cell.source
Provenance/evidence linking a cell back to mined/imported sources, especially HMI screens and components.

### cell.visual
Optional visual placement/symbol information recovered from source systems or seed data.

### cell.comment
Human note attached to a cell. This may later be generalized into shared Flux annotations if comments become cross-app.

## mine
### mine.hmi_tag
hmi tags mined from e.g. ftview, redlion, ignition. Optional fk to mine.plc_tag. Optional fk to mine.hmi_udt

### mine.hmi_udt
hmi template tags mined from e.g. ignition.

### mine.plc_tag
plc tags mined from e.g. L5X/L5K


# Flux.mine
1) Flux.mine is the ingestion element of Flux
2) Flux.mine ingests various control platform data, including:
  - L5X/L5K allen-bradley program files
  - xml exports and files from FTView SE applications, including:
    - gfx exports
    - alarm exports
    - par files


# Flux.spot
Flux.spot owns current-state operational display.
Flux.spot points reference `plane.series`, not raw path strings.
Spot reads cached Plane state:
- latest value
- status/freshness/quality
- today min/max
- rolling 7-day min/max
- rolling 30-day min/max
Flux.spot never reads Ignition directly.
## Configuration
1) import configuration through csv import:

| Spot Scope | ID (optional) | Name | group | kind | Tag 1 | Tag {n} | display order (optional) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| wells | 1 | Tank_01 | Tank | Oil Tank | [default]Path/to/tag/atomic_tag_1 | [default]Path/to/tag/atomic_tag_n | 4 |

2) We should provide a web interface closely resembling this import form, where modifications can be made

3) This is all backed on a postgres table which can be modified on the backend
  - Tags need to be id stored



# Flux.chart (formerly Flux.charts; backed by Flux.trace persistence for now)
Flux.chart owns historical/time-series display.
Chart signals reference `plane.series`.
Flux.chart reads bounded time-series arrays from Flux.plane. It does not read Ignition directly from web requests.

## Configuration
1) Import configuration through csv import:

| Chart Scope | ID (optional) | Name | Tag 1 | Tag {n} | display order (optional) |
| --- | --- | --- | --- | --- | --- |
| wells | 1 | AL1-16-29-107 | [default]Path/to/tag/atomic_tag_1 | [default]Path/to/tag/atomic_tag_n | 4 |

2) We should provide a web interface closely resembling this import form, where modifications can be made

3) This is all backed on a postgres table which can be modified on the backend
  - Tags need to be id stored

# Flux.serve
Flux.serve supervises workers
##  field_agent_heart_beat
Run by:
updates:


# Flux Interactions
## bridge connection test
- As Found:
Performed by `dashboard.services.test_bridge()`
- Desired State:
1) Flux.serve owns periodic call of status, checking every 5 seconds
  - trace logs system health
2) Logged in Flux.logs as trace health monitors
3) Latest bridge health is written to `status.latest` for the bridge connection entity. `bridge.ignition_bridge` owns configuration, not operational truth. `bridge.IgnitionBridge` -> `last_test_message`

## Flux.serve data acquisition workers
Flux.serve owns the long-running worker processes that keep Flux.plane fresh.
1) Flux.serve supervises acquisition workers.
   - Workers have heartbeats, status, last error, and restart/visibility through Flux.serve.
   - Django/web requests must not perform runtime Ignition reads.
2) Flux.bridge owns configured Ignition/Fluxy connectivity.
   - Acquisition workers read through a configured Flux.bridge connection.
   - Bridge config includes base URL, token, role, and latest connection health.
   - Workers should not hard-code ad hoc Ignition connection details when a bridge config exists.
3) Flux.opt owns the acquisition plan.
   - Groups series by bridge/provider.
   - Performs block reads, not per-tag read loops.
   - Applies hot/warm/cold cadence, demand leases, batch limits, timeouts, retries, and backpressure.
4) Flux.plane owns storage and query serving.
   - `plane.series`
   - latest value/status snapshot
   - samples/history
   - today, rolling 7-day, and rolling 30-day min/max rollups
   - bounded query APIs for Spot and Chart
5) Flux.spot and Flux.chart are consumers.
   - Flux.spot reads latest/status/rollup snapshots.
   - Flux.chart reads bounded time-series arrays.
   - Neither surface performs Ignition reads directly.

# Notable migrations
1) Migrated django application from single-schema to schema-by-namespace
2) Migrated Flux.trace to Flux.charts to Flux.chart
3) Migrated Flux.live to Flux.spot


# Flux.logs
  - Not mentioned before, but we need to start retaining logs
  - We need a retention policy with configuration
  - Include a link to logs and a config page on the dashboard


# Deep.plc

# Deep.schematics
