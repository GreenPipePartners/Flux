# Architecture Daily Log - 2026-05-25

## Session: Architectural state review

- Intent: Answer “Where are we architecturally” with a current-state review after broad Build/Cleanup work.
- Scope reviewed:
  - `architecture/agent_notices.md`
  - `architecture/core_area_files.md`
  - `work_assignment/2026_may_20/review.md`
  - `work_assignment/2026_May_19/to_do_first.md`
  - `arch_review.md`
  - `web/Flux/src/dashboard/services.py`
  - `web/Flux/src/templates/dashboard/home.html`
  - `web/Flux/src/templates/flux/partials/comp_card_controls.html`
  - `web/Flux/src/flux/serve/monitor.py`
  - `web/Flux/src/flux/charts/views.py`
  - `web/Flux/src/flux/charts/urls.py`
  - `web/Flux/src/flux/trace/urls.py`
  - `web/Flux/src/flux/trace/apps.py`
  - `web/Flux/src/flux/urls.py`
  - `web/Flux/src/flux/settings.py`
  - `web/Flux/src/flux/sim/views.py`
  - `web/Flux/src/templates/sim/index.html`
  - `web/Flux/src/flux/sim/jobs.py`
  - `web/Flux/src/flux/sim/provider_tree.py`
  - `web/Flux/src/flux/base/services.py`
  - `web/Flux/src/flux/build/services.py`
  - `web/Flux/src/flux/mine/services.py`
  - `web/Flux/src/flux/pagination.py`
- Architectural findings:
  - High: The worktree is too broad to treat as one releasable architectural unit; split into coherent commits/review slices.
  - High: Live/interface freshness still needs a hard required sampler contract; monitor currently classifies relevant samplers as `EXPECTED`/`OPTIONAL`.
  - Medium: Charts migration is useful but `flux.trace` versus `flux.charts` ownership remains muddy during compatibility.
  - Medium: Sim queued jobs are the right direction, but apply-selection still mixes selection persistence, plan/materialization, deletion, and external Ignition mutation.
  - Medium: Comp Surface controls converged, but dashboard/sim templates remain overloaded and configure/detail consistency is uneven.
- Report path: `arch_review.md`.
- Blockers: No application code was changed; no tests or runtime process probes were run in architecture mode.
- Next architecture actions: Re-review after the dirty tree is split and after Build hardens sampler requiredness, charts ownership docs, and Sim job phase boundaries.

## Session: Bridge connection test interaction refactor plan

- Intent: Review `docs/Master Design.md` `Flux Interactions > bridge connection test` and produce a refactor plan.
- Scope reviewed:
  - `architecture/agent_notices.md`
  - `architecture/core_area_files.md`
  - `docs/Master Design.md`
  - `web/Flux/src/dashboard/services.py`
  - `web/Flux/src/dashboard/views.py`
  - `web/Flux/src/dashboard/models.py`
  - `web/Flux/src/flux/serve/monitor.py`
  - `web/Flux/src/flux/serve/management/commands/flux_serve_monitor.py`
  - `web/Flux/src/flux/serve/models.py`
  - `web/Flux/src/flux/serve/tests.py`
- Architectural findings:
  - High: `flux_serve_monitor` already runs on the desired 5-second cadence, but bridge snapshots currently replay stored `IgnitionBridgeConfig.last_test_*` state instead of performing a fresh bridge probe.
  - High: `dashboard.views`/`dashboard.services.test_bridge()` still own synchronous external Fluxy IO in the web request path.
  - Medium: Bridge behavior lacks a clear Flux.bridge module boundary; config, probe, rendering, and service snapshot adaptation are split across dashboard and serve.
  - Medium: The design's Flux.logs requirement is not represented by latest-only `ServeServiceSnapshot`/`IgnitionBridgeConfig` fields.
- Report path: `arch_review.md`.
- Blockers: Architecture-only review; no code changes, tests, or runtime bridge probes were executed.
- Next architecture actions: Re-review after Build extracts a Flux.bridge probe, wires it into `flux.serve.monitor.bridge_result()`, and defines the Flux.logs health history contract.

## Session: Master Design Flux.web review

- Intent: Review updated `docs/Master Design.md`, especially the initial `Flux.web` section.
- Scope reviewed:
  - `architecture/agent_notices.md`
  - `architecture/core_area_files.md`
  - `docs/Master Design.md`
  - `docs/flux-architecture.md`
  - `docs/apps/live.md`
- Architectural findings:
  - High: The site-wide 5-second Flux.web pulse is a good UX contract, but must be defined as cached HTMX display refresh only, not backend IO or sampler ownership.
  - Medium: `Flux.live` hot/warm/cold poll language should be separated from Flux.opt/Flux.serve backend read-lane language.
  - Medium: The refresh bar should show backend freshness/source evidence, not only a countdown to the next UI swap.
  - Low: “Every page” should not imply auto-swapping mutation/configuration forms while users are editing.
- Report path: `arch_review.md`.
- Blockers: Architecture-only review; no application code edits, tests, or runtime probes were performed.
- Next architecture actions: Re-review after Master Design clarifies display pulse versus backend sampler rates and defines the refresh bar data contract.

## Session: Dashboard, Flux.spot, and Flux.chart refactor plan

- Intent: Produce a Build-ready architecture plan for dashboard refactor, `Flux.live` -> `Flux.spot`, and `Flux.charts` -> `Flux.chart`.
- Scope reviewed:
  - `architecture/agent_notices.md`
  - `architecture/core_area_files.md`
  - `web/Flux/src/templates/dashboard/home.html`
  - `web/Flux/src/flux/urls.py`
  - `web/Flux/src/flux/settings.py`
  - `web/Flux/src/flux/live/apps.py`
  - `web/Flux/src/flux/live/**/*` inventory
  - `web/Flux/src/flux/charts/**/*` inventory
  - `web/Flux/src/flux/charts/urls.py`
  - `web/Flux/src/flux/trace/apps.py`
  - Grep inventory for `Flux.live`, `/live/`, `flux.live`, `Flux.charts`, `/charts/`, and `flux.charts` references.
- Architectural findings:
  - High: Dashboard must be decomposed/descriptor-driven before or during the rename because `dashboard/home.html` hard-codes labels, card ids, URL namespaces, and configure forms in one large Comp Surface.
  - High: `Flux.live` -> `Flux.spot` can break Django migrations/tables/content types if app label and DB rename strategy are not explicit.
  - High: `Flux.charts` -> `Flux.chart` should be treated as UI/service namespace migration while keeping `flux.trace` models stable for now.
  - Medium: Tests/docs/copy payloads encode old names heavily and need first-class migration coverage.
  - Medium: Dashboard 5-second pulse must remain cached display refresh, not per-card polling or backend IO.
- Report path: `arch_review.md`.
- Blockers: Architecture-only plan; no code changes, tests, or runtime probes were performed.
- Next architecture actions: Re-review after Build completes phase 1 dashboard decomposition and compatibility aliases for Spot/Chart routes.

## Session: Base table legacy/removal review

- Intent: Analyze `base_*` PostgreSQL table purpose and classify which appear legacy/removable.
- Scope reviewed:
  - `architecture/agent_notices.md`
  - `architecture/core_area_files.md`
  - `docs/Master Design.md`
  - `docs/flux-architecture.md`
  - `docs/apps/sim.md`
  - `docs/apps/serve.md`
  - `web/Flux/src/flux/base/models.py`
  - `web/Flux/src/flux/base/services.py`
  - `web/Flux/src/flux/base/field_config.py`
  - `web/Flux/src/flux/base/migrations/0001_initial.py` through `0008_tagselection_config.py`
  - `web/Flux/src/flux/field/models.py`
  - `web/Flux/src/flux/field/admin.py`
  - `web/Flux/src/flux/field/views.py`
  - `web/Flux/src/flux/sim/models.py`
  - `web/Flux/src/flux/sim/views.py`
  - `web/Flux/src/flux/sim/jobs.py`
  - `web/Flux/src/flux/sim/output.py`
  - `web/Flux/src/flux/sim/field_bridge.py`
  - `web/Flux/src/flux/sim/provider_tree.py`
  - `web/Flux/src/flux/serve/field_supervisor.py`
  - `web/Flux/src/flux/serve/management/commands/flux_field_supervisor.py`
  - `web/Flux/src/flux/field/management/commands/configure_field_ignition.py`
- Architectural findings:
  - High: Most `base_*` tables are active Flux.sim catalog/materialization or Flux.serve FieldAgent runtime state and should not be deleted as legacy.
  - High: Current `base_*` public-table naming conflicts with the Master Design direction toward schema-qualified namespace tables; cleanup should be schema/ownership migration, not blind deletion.
  - Medium: `base_fieldnode` appears to be historical FieldAgent node residue and is the first credible base-table removal candidate after row-count/dependency verification.
  - Medium: Duplicate `flux.field` models/tables are likely the larger legacy surface; the app admin says it is migration-only, but models/views still exist.
  - Medium: Master Design `tags.Tags` is not yet mapped to current `runtime.RuntimeTag` and `base.TagNode` split.
- Report path: `arch_review.md`.
- Blockers: Live PostgreSQL row counts and dependency queries could not be executed because non-git bash/database commands are blocked in this environment.
- Next architecture actions: Run a DB inventory for `base_*` and `field_*`; then plan removal of `base_fieldnode` and legacy `flux.field` tables separately from schema migration of active sim/runtime tables.

## Session: Remove base_fieldnode

- Intent: Follow up on the base table review by removing `base_fieldnode` if unused.
- Scope reviewed:
  - `web/Flux/src/flux/base/models.py`
  - `web/Flux/src/flux/base/admin.py`
  - `web/Flux/src/flux/field/tests.py`
  - Grep inventory for `flux.base.FieldNode`, `FieldNode.objects`, `base_fieldnode`, and `unique_base_field_node_id`.
- Result:
  - Active base-owned `FieldNode` references were limited to model/admin/test and historical migration state.
  - Removed `flux.base.FieldNode` from active models.
  - Removed the base admin registration.
  - Removed the isolated test that only exercised `FieldNode.label`.
  - Added `web/Flux/src/flux/base/migrations/0009_drop_fieldnode.py` to drop the table.
- Blockers: Non-git bash commands are blocked by current tool policy, so Django check/test/migrate commands were not run in this session.
- Next architecture actions: Review duplicate legacy `flux.field` tables/models separately; remaining `FieldNode` references are in `flux.field`, not `flux.base`.

## Session: Retire duplicate flux.field model tables

- Intent: Perform the recommended retirement/quarantine of duplicate `flux.field` models/tables after confirming active code no longer depends on them.
- Scope reviewed:
  - `web/Flux/src/flux/field/models.py`
  - `web/Flux/src/flux/field/views.py`
  - `web/Flux/src/flux/field/urls.py`
  - `web/Flux/src/flux/field/admin.py`
  - `web/Flux/src/flux/field/apps.py`
  - `web/Flux/src/flux/field/tests.py`
  - `web/Flux/src/flux/field/migrations/0001_initial.py` through `0004_seed_default_field_devices.py`
  - `web/Flux/src/templates/field/index.html`
  - Route inventory for `flux.field.urls`
  - Legacy table counts for `field_fieldendpoint`, `field_fielddevice`, `field_fieldtag`, `field_fieldnode`, and `field_fieldagentheartbeat`
- Result:
  - Confirmed `/field/` is not routed through `flux.urls` and operator command paths use `flux.base` models.
  - Confirmed legacy endpoint/device/tag names were already present in active `base_*` tables.
  - Removed active model classes from `flux.field.models`; the app is now helper/historical-migration only.
  - Removed legacy `flux.field.views`, `flux.field.urls`, and `templates/field/index.html`.
  - Added `web/Flux/src/flux/field/migrations/0005_drop_legacy_field_models.py` to drop the legacy `field_*` tables after `base.0009_drop_fieldnode`.
  - Applied the migration locally and confirmed all five legacy field tables are gone.
- Verification:
  - `uv run python manage.py check` passed.
  - `uv run python manage.py makemigrations --check --dry-run` passed.
  - `uv run python manage.py migrate field` passed.
  - `uv run python manage.py test flux.base flux.field flux.sim --keepdb` passed: 93 tests, 1 skipped.
- Next architecture actions: Keep `flux.field` as helper/command namespace only unless a concrete FieldAgent domain model is explicitly reintroduced in Master Design.

## Session: `base_fieldagentheartbeat` field-usage review

- Intent: Answer what `base_fieldagentheartbeat` rows do and whether `version`, `started_at`, and `last_error` are actually used.
- Scope reviewed:
  - `architecture/agent_notices.md`
  - `architecture/core_area_files.md`
  - `web/Flux/src/flux/base/models.py`
  - `web/Flux/src/flux/base/migrations/0002_fieldagent_config_to_base.py`
  - `web/Flux/src/flux/base/admin.py`
  - `web/Flux/src/flux/serve/management/commands/flux_field_supervisor.py`
  - `web/Flux/src/flux/serve/field_supervisor.py`
  - `web/Flux/src/flux/serve/monitor.py`
  - `web/Flux/src/dashboard/services.py`
  - `web/Flux/src/dashboard/tests.py`
  - `web/Flux/src/templates/dashboard/home.html`
  - `web/Flux/src/flux/sim/views.py`
  - `web/Flux/src/templates/sim/partials/field_runtime_status.html`
  - `docs/apps/serve.md`
  - `docs/apps/dashboard.md`
- Architectural findings:
  - Medium: `base_fieldagentheartbeat` is active runtime evidence, but it is supervisor-written rather than a true FieldAgent self-heartbeat, so the table belongs conceptually with Flux.serve runtime ownership rather than Flux.base configuration ownership.
  - Medium: `version` and `started_at` are currently copied from legacy rows/admin-visible only; the active supervisor writer does not set them and monitor/dashboard selectors do not use them.
  - Medium: `last_error` is active: the supervisor writes process failure/disabled evidence and `flux.serve.monitor.field_agent_result()` treats heartbeat errors as service errors, but dashboard surfaces mostly show `FieldEndpoint.last_error` rather than heartbeat error details.
  - Low: `current_node_count` is written by the supervisor but has little visible product use; its current per-device count inside a 1-second supervisor loop is a potential repeated-query smell if endpoint/device counts grow.
- Report path: none; answered inline in chat.
- Blockers: Live PostgreSQL row values were not verified from a DSN; local SQLite is not considered durable evidence for this cleanup because it is being retired.
- Next architecture actions: Decide whether FieldAgent will ever emit real self-reports. If yes, wire bounded version/start-time reporting. If no, prune or relocate unused runtime fields during the Flux.serve ownership migration.

## Session: `base_fielddevice` purpose review

- Intent: Continue one-by-one base table review by identifying what `base_fielddevice` does.
- Scope reviewed:
  - `web/Flux/src/flux/base/models.py`
  - `web/Flux/src/flux/base/field_config.py`
  - `web/Flux/src/flux/sim/field_bridge.py`
  - `web/Flux/src/flux/sim/rehydrate.py`
  - `web/Flux/src/flux/sim/field_demo.py`
  - `web/Flux/src/flux/field/ignition.py`
  - `web/Flux/src/flux/serve/field_acceptance.py`
  - `web/Flux/src/flux/sim/export_compare.py`
  - `web/Flux/src/flux/base/admin.py`
- Architectural findings:
  - Medium: `base_fielddevice` is active and should not be removed as legacy; it is the device/grouping layer between `FieldEndpoint` OPC servers and `FieldTag` simulated nodes.
  - Medium: It is conceptually Flux.sim runtime materialization but stored under Flux.base; ownership should eventually be named/schema-qualified more clearly.
  - Low: `config` is a flexible behavior envelope for simulated device modes such as slow network response; keep it bounded and documented so it does not become an untyped junk drawer.
- Report path: none; answered inline in chat.
- Blockers: Did not inspect live Postgres row contents in this session.
- Next architecture actions: Review `base_fieldtag` next because `base_fielddevice` is only meaningful through the tags it groups and serializes.

## Session: Master Design `Flux.base` database modeling review

- Intent: Review the `Flux.base` section of `docs/Master Design.md` and provide architecture feedback for an upcoming database modeling refactor.
- Scope reviewed:
  - `architecture/agent_notices.md`
  - `architecture/core_area_files.md`
  - `docs/Master Design.md`
  - `web/Flux/src/flux/base/models.py`
  - `web/Flux/src/runtime/models.py`
  - `web/Flux/src/flux/bridge/models.py`
  - `web/Flux/src/flux/bridge/migrations/0001_dashboard_table_state.py`
  - `web/Flux/src/flux/bridge/migrations/0003_move_ignition_bridge_to_bridge_schema.py`
  - `web/Flux/src/flux/serve/models.py`
  - `web/Flux/src/flux/settings.py`
- Architectural findings:
  - High: The Postgres/schema-by-namespace direction is correct, but physical schema migration should not outrun the logical model for central tag/device identity and domain-owned extension tables.
  - High: `base.tag` should be stable tag identity, not a broad table carrying sampling, chart, Spot, sim, latest value, and health concerns.
  - High: Flux.base should be a shared identity/kernel layer; domain config and observations belong in `bridge`, `serve`, `sim`, `spot`, `chart`, `mine`, and related schemas.
  - Medium: Schema-qualified Django tables need a written migration/test convention because the current bridge pattern uses bespoke quoted `db_table` and `RunSQL` migrations.
  - Medium: Bridge config/latest status and health/log history should be separated, with Flux.serve owning observations and Flux.web rendering cached latest state.
- Report path: `arch_review.md`.
- Blockers: Architecture-only review; no database migrations, code edits, tests, or live DB row inspections were performed.
- Next architecture actions: Draft a logical ERD and identity-vs-config-vs-observation table classification before Build performs table moves.

## Session: Base device/tag kernel migration path

- Intent: Provide a path forward for migrating `base_fielddevice` and `base_fieldtag` into kernel `base.device` and `base.tag`, with supplemental `sim.device` and `sim.tag` layers.
- Scope reviewed:
  - `docs/Master Design.md`
  - `web/Flux/src/flux/base/models.py`
  - `architecture/agent_notices.md`
  - `architecture/core_area_files.md`
- Architectural findings:
  - High: The migration direction is correct, but Base must receive identity-only kernel truth, not the full current FieldAgent/simulation behavior from `FieldDevice`/`FieldTag`.
  - High: Use additive migrations and compatibility selectors; do not directly rename/drop the active FieldAgent config tables before parity tests.
  - Medium: `sim.device`/`sim.tag` should own endpoint membership, simulation mode, update cadence, min/max/variance/initial values, and behavior/mode configuration.
  - Medium: Keep high-churn runtime values and health observations out of `base.tag`.
- Report path: `arch_review.md`.
- Blockers: Architecture-only path; no schema migrations, code edits, tests, or live DB inspections were performed.
- Next architecture actions: Turn the path into a Build migration plan with field mapping, constraints, backfill queries, and FieldAgent JSON parity tests.

## Session: Base device/tag kernel migration implementation

- Intent: Implement the additive migration from legacy `base_fielddevice`/`base_fieldtag` and `base_simdevice`/`base_simdevicetag` into kernel `base.device`/`base.tag` plus supplemental `sim.device`/`sim.tag` tables.
- Scope changed:
  - `web/Flux/src/flux/base/models.py`
  - `web/Flux/src/flux/base/admin.py`
  - `web/Flux/src/flux/base/field_config.py`
  - `web/Flux/src/flux/base/migrations/0010_kernel_device_tag.py`
  - `web/Flux/src/flux/sim/models.py`
  - `web/Flux/src/flux/sim/admin.py`
  - `web/Flux/src/flux/sim/migrations/0008_device_tag_config.py`
  - `web/Flux/src/flux/sim/migrations/0009_tagconfig_materialized.py`
  - `web/Flux/src/flux/sim/migrations/0010_tagconfig_base_tag_fk_enabled.py`
  - `web/Flux/src/flux/sim/migrations/0011_tagconfig_materialized_names.py`
  - `web/Flux/src/flux/sim/migrations/0012_sync_materialized_tag_values.py`
  - `arch_review.md`
  - `architecture/core_area_files.md`
  - `architecture/daily/architecture_2026-05-25/architecture_2026-05-25.md`
- Result:
  - Added schema-qualified `base.device` and `base.tag` kernel identity tables.
  - Added schema-qualified `sim.device` and `sim.tag` supplemental tables as `DeviceConfig` and `TagConfig`.
  - Backfilled legacy FieldAgent materialization and sim catalog rows, including 448,756 `base_simdevicetag` rows via bulk migration.
  - Updated FieldAgent endpoint config generation to prefer the new sim extension selector with legacy fallback.
  - Added `sim.tag.materialized` to prevent full catalog rows from leaking into runtime FieldAgent config.
  - Corrected `sim.tag.base_tag` to FK because one kernel tag identity can appear in multiple sim contexts.
- Verification:
  - `uv run python manage.py check` passed.
  - `uv run python manage.py makemigrations --check --dry-run` passed.
  - `uv run python manage.py migrate` applied `base.0010` and `sim.0008` through `sim.0012` locally.
  - FieldAgent JSON parity check across 8 endpoints passed: 2,085 enabled materialized tags and 0 mismatches against legacy serialization.
  - `uv run python manage.py test flux.base flux.sim flux.field flux.serve dashboard --keepdb` passed: 189 tests, 2 skipped.
- Current row counts:
  - `base.device`: 54
  - `base.tag`: 449,949
  - `sim.device`: 54
  - `sim.tag`: 449,949
  - `sim.tag` materialized+enabled: 2,085
- Next architecture actions: Plan the next cutover so Sim materialization writes new tables directly, then retire legacy `base_fielddevice`/`base_fieldtag` only after all active imports and tests stop depending on them.

## Session: Device/tag compatibility sync continuation

- Intent: Continue the device/tag refactor by preventing future legacy `FieldDevice`/`FieldTag` writes from leaving the new `base.device`/`base.tag` and `sim.device`/`sim.tag` tables stale.
- Scope changed:
  - `web/Flux/src/flux/sim/kernel_sync.py`
  - `web/Flux/src/flux/sim/field_bridge.py`
  - `web/Flux/src/flux/sim/rehydrate.py`
  - `web/Flux/src/flux/sim/field_demo.py`
  - `web/Flux/src/flux/sim/fluxolot_fishtank.py`
  - `web/Flux/src/flux/sim/tests_field_bridge.py`
  - `arch_review.md`
  - `architecture/core_area_files.md`
  - `architecture/daily/architecture_2026-05-25/architecture_2026-05-25.md`
- Result:
  - Added `flux.sim.kernel_sync` compatibility helpers for syncing legacy FieldAgent materialization writes into kernel/sim schema rows.
  - Wired sync after `field_bridge.materialize_sim_device()`, rehydration backing materialization, demo field config creation, and Fluxolot fishtank field config creation.
  - Added cleanup handling so deleted rehydration backing tags and empty rehydration devices disable corresponding new materialized rows.
  - Added test coverage that materialization creates kernel `base.device`/`base.tag` rows and materialized `sim.tag` rows used by `endpoint_config()`.
- Verification:
  - `uv run python manage.py check` passed.
  - `uv run python manage.py makemigrations --check --dry-run` passed.
  - `uv run python manage.py test flux.sim.tests_field_bridge flux.sim.tests flux.base flux.field flux.serve dashboard --keepdb` passed: 159 tests, 1 skipped.
  - FieldAgent JSON parity check across 8 endpoints still passed: 2,085 enabled materialized tags and 0 mismatches.
- Next architecture actions: Update bulk sim catalog import paths (`tag_data_ingest`, value profile generation, and related provider import flows) to sync full non-materialized catalog identity without per-row hot loops before retiring legacy sim catalog tables.

## Session: Bulk sim catalog sync continuation

- Intent: Complete the next device/tag refactor step by keeping non-materialized Sim catalog imports synced into the new kernel/sim schema without per-row hot loops or clobbering materialized FieldAgent rows.
- Scope changed:
  - `web/Flux/src/flux/sim/kernel_sync.py`
  - `web/Flux/src/flux/sim/tag_data_ingest.py`
  - `web/Flux/src/flux/sim/output.py`
  - `web/Flux/src/flux/sim/value_profiles.py`
  - `web/Flux/src/flux/sim/tests_tag_data_ingest.py`
  - `arch_review.md`
  - `architecture/core_area_files.md`
  - `architecture/daily/architecture_2026-05-25/architecture_2026-05-25.md`
- Result:
  - Added batch-oriented `sync_sim_catalog_for_provider()` and supporting bulk helpers.
  - Catalog sync now updates `base.device`, `base.tag`, `sim.device`, and non-materialized `sim.tag` rows for imported providers.
  - Catalog refresh preserves existing materialized `sim.tag` runtime rows instead of dematerializing or overwriting FieldAgent-specific tag names/behavior.
  - Tag-data ingestion disables stale non-materialized catalog extension rows when source paths disappear.
  - Selected-output and value-profile sim tag paths now sync their Sim catalog rows before/alongside materialization.
  - Added test assertions that tag-data import creates kernel and non-materialized sim extension rows.
- Verification:
  - `uv run python manage.py check` passed.
  - `uv run python manage.py makemigrations --check --dry-run` passed.
  - `uv run python manage.py test flux.sim.tests_tag_data_ingest flux.sim.tests_field_bridge flux.sim.tests_export_compare --keepdb` passed: 20 tests.
  - `uv run python manage.py test flux.sim flux.base flux.field flux.serve dashboard --keepdb` passed: 189 tests, 2 skipped.
  - FieldAgent JSON parity check across 8 endpoints still passed: 2,085 enabled materialized tags and 0 mismatches.
- Next architecture actions: Plan legacy table retirement order: first move remaining read/write surfaces to new selectors, then quarantine/drop legacy `base_fielddevice`/`base_fieldtag` and later old `base_simdevice`/`base_simdevicetag` only after all direct imports are gone.

## Session: Selector-backed device/tag read cutover

- Intent: Move non-mutating runtime/status reads off direct `base_fielddevice`/`base_fieldtag` queries and onto new schema-backed selectors while preserving compatibility fallback.
- Scope changed:
  - `web/Flux/src/flux/base/field_selectors.py`
  - `web/Flux/src/dashboard/services.py`
  - `web/Flux/src/flux/sim/views.py`
  - `web/Flux/src/flux/serve/field_supervisor.py`
  - `web/Flux/src/flux/serve/management/commands/flux_field_supervisor.py`
  - `web/Flux/src/flux/field/management/commands/configure_field_ignition.py`
  - `arch_review.md`
  - `architecture/core_area_files.md`
  - `architecture/daily/architecture_2026-05-25/architecture_2026-05-25.md`
- Result:
  - Added `endpoint_runtime_counts()`, `enabled_runtime_totals()`, `enabled_field_endpoint_queryset()`, and `endpoint_materialized_tag_count()` selectors.
  - Dashboard readiness and field-device status now use selector-backed runtime counts.
  - Sim catalog/runtime status now uses `DeviceConfig`/`TagConfig` counts instead of legacy description-based `FieldTag` queries.
  - FieldAgent supervisor endpoint selection and heartbeat node counts now use selector-backed materialized runtime state.
  - `configure_field_ignition` now selects enabled endpoints through the same compatibility selector as the supervisor.
- Verification:
  - `uv run python manage.py check` passed.
  - `uv run python manage.py makemigrations --check --dry-run` passed.
  - `uv run python manage.py test flux.sim.tests_field_bridge flux.sim.tests_tag_data_ingest dashboard flux.serve.tests --keepdb` passed: 114 tests, 1 skipped.
  - `uv run python manage.py test flux.sim flux.base flux.field flux.serve dashboard --keepdb` passed: 189 tests, 2 skipped.
  - FieldAgent JSON parity across 8 endpoints still passed: 2,085 enabled materialized tags and 0 mismatches.
  - Selector-backed runtime totals: 8 endpoints, 40 devices, 2,085 tags.
- Next architecture actions: Remaining direct legacy usages are compatibility writers, Field/Ignition utilities that accept a legacy `FieldDevice`, constants/enum access, and admin. Retire only after replacement write APIs exist and tests no longer construct legacy rows directly.

## Session: Flux.spot tag identity advice

- Intent: Answer whether Flux.spot should introduce a Spot-owned table that foreign-keys to kernel `base.tag` after the tag refactor.
- Scope reviewed:
  - `architecture/agent_notices.md`
  - `architecture/core_area_files.md`
  - `docs/Master Design.md`
  - `web/Flux/src/flux/base/models.py`
  - `web/Flux/src/flux/spot/models.py`
  - `web/Flux/src/flux/live/models.py`
  - Grep inventory for Spot/Live/runtime tag references.
- Architectural findings:
  - Medium: The proposed direction is correct: `base.tag` should be the shared tag identity, and Spot should own membership/presentation rows keyed to that tag identity.
  - Medium: Current `flux.spot.models` is only a compatibility re-export while `flux.live.models.LiveCardPointDefinition` still stores `full_path` text, so Build needs an additive migration rather than a hard rename.
  - Medium: A Spot tag/point table should own label, role, card/scope membership, order, units/display overrides, and required/optional semantics; latest values, samples, health observations, and sampler cadence should stay outside Spot membership.
  - Low: Use FK to `base.Tag`, but retain/import by full path as a boundary adapter so CSV and UI workflows remain natural while storage becomes ID-backed.
- Report path: none; answered inline in chat.
- Blockers: Architecture advice only; no application code edits, migrations, tests, or DB writes were performed.
- Next architecture actions: Define a small `spot.point`/`SpotTag` ERD and migration plan from `LiveCardPointDefinition.full_path` to `base.Tag` FK before Build changes models.

## Session: Flux.plane shared series advice for Spot and Chart

- Intent: Answer whether Flux.spot and Flux.chart should share a consolidated reference layer for tags whose data is stored through Flux.plane.
- Scope reviewed:
  - `docs/Master Design.md`
  - `web/Flux/src/flux/base/models.py`
  - `web/Flux/src/runtime/models.py`
  - `web/Flux/src/flux/trace/models.py`
  - `web/Flux/src/flux/plane/runtime.py`
  - `web/Flux/src/flux/plane/sample_seed.py`
  - `web/Flux/src/flux/live/models.py`
  - `web/Flux/src/flux/spot/models.py`
- Architectural findings:
  - High: Spot and Chart should not each create separate runtime/sampler identities for the same physical tag; duplicate identities risk duplicate block reads, inconsistent latest/history values, and unclear retention ownership.
  - Medium: The consolidated layer should be Plane-owned as a series/stream acquisition-storage contract keyed to `base.Tag`, not a second canonical tag identity competing with `base.tag`.
  - Medium: Spot and Chart should keep separate membership/presentation tables because Spot needs current-state/card roles while Chart needs axes, visibility, history windows, and downsampling bounds.
  - Medium: Current `runtime.RuntimeTag` is overloaded across identity, sampler schedule, display metadata, and sample storage; it is the likely migration source for a future `plane.series` plus Plane latest/sample tables.
- Report path: none; answered inline in chat.
- Blockers: Architecture advice only; no application code edits, migrations, tests, or DB writes were performed.
- Next architecture actions: Draft an ERD for `base.tag` -> `plane.series` -> `spot.point`/`chart.signal`, including latest-only versus history-enabled storage policy and QuestDB key strategy.

## Session: Flux.spot Plane cache/status clarification

- Intent: Refine the Plane/Spot contract after user clarified Spot needs latest value plus min/max summaries for today, week, and 30 days, and asked where tag status belongs.
- Scope reviewed:
  - `docs/Master Design.md` lines 169-171
  - Current architecture context for `base.tag`, `runtime.RuntimeTag`, `LatestTagValue`, `TagSample`, `DailyTagExtreme`, and Trace/Plane helpers
- Architectural findings:
  - Medium: Spot card reads should use a Plane-owned bounded snapshot/summary contract: latest value, quality/status, today min/max, rolling 7-day min/max, and rolling 30-day min/max.
  - Medium: Rollup windows should be precomputed or incrementally maintained by Plane/Serve workers; web requests should not scan raw samples or QuestDB per card.
  - Medium: Status is shared data-plane evidence, not Spot or Chart presentation state. Flux.serve should supervise/update the worker/probe loop; Flux.plane should persist per-series status/snapshot rows; Spot and Chart should consume them.
  - Low: “Week” needs explicit semantics. Recommended default is rolling 7 days; calendar week can be a separate named window if needed.
- Report path: none; answered inline in chat and provided paste-ready Master Design text.
- Blockers: Architecture advice only; no application code edits, migrations, tests, or DB writes were performed.
- Next architecture actions: Update Master Design with a `base.tag` -> `plane.series` -> `spot.point`/`chart.signal` model and define `plane.series_status` plus fixed rollup windows.

## Session: Flux.opt acquisition ownership clarification

- Intent: Respond to user direction that optimized Ignition retrieval and Flux.plane storage should be a Flux.opt task.
- Scope reviewed:
  - Existing architecture context for Flux.opt sampling, Flux.serve supervision, Flux.plane storage, and Flux.spot/Flux.chart read patterns.
- Architectural findings:
  - Medium: The ownership direction is correct. Flux.opt should own acquisition planning and optimization: block reads, cadence, demand leases, batching, retry/timeouts, and backpressure.
  - Medium: Flux.plane should own schema and storage/query APIs for series, latest values, samples/history, status, and rollups; it should not reach directly into Ignition.
  - Medium: Flux.serve should supervise Opt workers and expose worker health/status evidence; Spot and Chart should declare demand and consume cached Plane data only.
  - Low: This split keeps browser/web routes from becoming hidden data-plane workers and preserves Flux's performance-first block-read discipline.
- Report path: none; answered inline in chat.
- Blockers: Architecture advice only; no application code edits, migrations, tests, or DB writes were performed.
- Next architecture actions: Add Master Design wording for `Flux.opt` as the Ignition acquisition optimizer feeding `plane.series` snapshots/history under Flux.serve supervision.

## Session: Flux.serve bridge worker documentation check

- Intent: Answer whether dedicated Flux.serve processes for retrieving data over Flux.bridge are documented.
- Scope reviewed:
  - `docs/Master Design.md`
  - `docs/apps/live.md`
  - `docs/operator-guide.md`
  - `docs/charts-architecture.md`
  - `docs/runbooks/fluxolot-fishtank.md`
  - `web/Flux/src/flux/serve/management/commands/flux_sampling_worker.py`
  - `web/Flux/src/flux/serve/management/commands/flux_charts_worker.py`
  - `web/Flux/src/flux/serve/management/commands/flux_trace_worker.py`
  - `web/Flux/src/flux/serve/management/commands/flux_worker.py`
- Architectural findings:
  - Medium: The worker idea is documented, but scattered: Spot docs mention `Flux.serve worker -> Flux.opt sampler`, operator docs document `flux_charts_worker`, and runbooks document the Fluxolot sampler.
  - Medium: Master Design does not yet explicitly define the canonical pipeline `Flux.serve process -> Flux.bridge/Fluxy -> Flux.opt planner -> Flux.plane writes -> Spot/Chart reads`.
  - Medium: Current worker commands still take `FLUXY_BASE_URL`/`FLUXY_TOKEN` directly, so the code path is functionally over Fluxy/WebDev but not yet cleanly documented as resolving a configured `Flux.bridge` row.
  - Low: FieldAgent supervision is documented separately; it should not be confused with Plane acquisition workers.
- Report path: none; answered inline in chat and provided paste-ready Master Design text.
- Blockers: Architecture advice only; no application code edits, migrations, tests, or process probes were performed.
- Next architecture actions: Add a Master Design subsection naming the serve worker types, bridge resolution contract, and ownership split between Serve, Bridge, Opt, Plane, Spot, and Chart.

## Session: Master Design consolidated status review

- Intent: Review user's Master Design update that proposes `base.status` as a single status table for endpoints, connections, devices, and tags.
- Scope reviewed:
  - `architecture/agent_notices.md`
  - `docs/Master Design.md`
  - Grep inventory for current status models and status usage including `ServeServiceSnapshot`, `FieldAgentHeartbeat`, `IgnitionBridgeConfig`, `LatestTagValue`, and runtime status selectors.
- Architectural findings:
  - Medium: A consolidated latest-status read model is directionally useful because dashboard/Spot/Chart/Serve need one vocabulary for ok/warning/error/stale/unknown across heterogeneous targets.
  - Medium: The table should not become the source of domain truth. Domain tables still own identity/configuration and Plane still owns values/rollups; the status table should own latest operational evidence only.
  - Medium: `base.status` placement is debatable. It is acceptable as shared kernel/read-model storage if Base is explicitly allowed to hold latest status, but `serve.status` or a future observability/logs namespace is cleaner because Flux.serve workers produce most status evidence.
  - Medium: A single GUID FK to “various source-of-truth tables” is not a real relational FK unless there is a shared entity registry. First pass should use bounded `target_kind` + `target_guid` with validation, or adopt a deliberate `base.entity` registry.
  - Low: The design should distinguish configuration `enabled` flags from runtime/observed status to avoid mixing operator intent with observed evidence.
- Report path: none; answered inline in chat.
- Blockers: Architecture advice only; no application code edits, migrations, tests, or DB writes were performed.
- Next architecture actions: Tighten Master Design wording around `status.latest`/`base.status`: target key, status kind, observed state, freshness, evidence bounds, uniqueness, and retention/log separation.

## Session: Status namespace and entity registry advice

- Intent: Respond to user preference for a dedicated status namespace and readiness to formalize cross-domain entities.
- Scope reviewed:
  - Prior Master Design status update and current architecture context for `base.tag`, `base.device`, Plane series, Serve snapshots, bridge config, and FieldEndpoint runtime evidence.
- Architectural findings:
  - Medium: A dedicated `status` namespace is cleaner than `base.status` because status rows are operational evidence/read models, not kernel identity/configuration.
  - Medium: Formalizing `base.entity` is now reasonable if kept narrow: stable GUID, bounded target kind, natural key/display name, enabled flag, and timestamps.
  - Medium: `status.latest` should FK to `base.entity` and carry latest observed state by status kind/source; domain tables should still own their configuration and behavior.
  - Medium: The migration should be additive and staged; do not force every table through entities in one pass. Start with `base.tag`, `base.device`, `plane.series`, bridge connections, serve workers, and field endpoints.
  - Low: Entity registry avoids polymorphic FK ambiguity but can become a god table if app-specific metadata leaks into it.
- Report path: none; answered inline in chat.
- Blockers: Architecture advice only; no application code edits, migrations, tests, or DB writes were performed.
- Next architecture actions: Add Master Design sections for `base.entity`, `status.latest`, and later `status.event`/Flux.logs handoff, including uniqueness and stale/retention rules.

## Session: Master Design entity/status update recommendation

- Intent: Provide paste-ready recommendations for updating `docs/Master Design.md` after settling on `base.entity`, `status.latest`, and `plane.series`.
- Scope reviewed:
  - Current `docs/Master Design.md` structure from prior session context.
  - Existing architecture decisions for Base identity, Plane data series, Serve/Opt acquisition, Bridge connectivity, Spot/Chart consumption, and Status latest evidence.
- Architectural findings:
  - Medium: Master Design should remove Flux.base responsibility for recording current statuses and instead place operational status under a dedicated `Flux.status` namespace.
  - Medium: `base.entity` should be introduced before status because it gives `status.latest` a real FK target and prevents polymorphic-FK drift.
  - Medium: `plane.series` should be documented as the shared data-plane stream referenced by Spot and Chart, with latest/status/window-stat reads bounded and cached.
  - Low: The design should explicitly distinguish `status.latest` from future retained `status.event`/Flux.logs.
- Report path: none; paste-ready text provided in chat.
- Blockers: Architecture advice only; no application code edits, docs edits, migrations, tests, or DB writes were performed.
- Next architecture actions: After Master Design is updated, Build can create additive migrations in this order: `base.entity`, status schema/latest table, Plane series/snapshots, then Spot/Chart FK migrations.

## Session: Final Master Design status/entity review

- Intent: Review the user's updated `docs/Master Design.md` one more time for remaining structural risks before Build acts on the Entity/Status/Plane direction.
- Scope reviewed:
  - `architecture/agent_notices.md`
  - `docs/Master Design.md`
  - Grep inventory for `base.entity`, `status.latest`, `plane.series`, `base.status`, and duplicate Serve acquisition sections.
- Architectural findings:
  - Medium: The overall direction is now sound and buildable: `base.entity`, `status.latest`, `plane.series`, Spot/Chart consumers, and Serve→Bridge→Opt→Plane pipeline are present.
  - Medium: Stale/conflicting text remains: `base.status` still appears under Flux.base, bridge health still says latest health is kept in Flux.base/bridge fields, and `Flux.serve data acquisition workers` appears twice.
  - Medium: `base.entity.enabled` risks conflicting with domain-specific enablement on tag/device/series/worker rows. Prefer `retired_at` or lifecycle state if the registry needs lifecycle tracking.
  - Low: `status.latest` uniqueness should include a stable producer key such as `source_instance` if multiple workers can report the same status kind for the same entity.
  - Low: Clarify that Plane owns latest value/rollup storage while Flux.status owns operational status evidence; avoid wording that says Plane owns "latest value/status snapshot" now that status is its own namespace.
- Report path: none; answered inline in chat.
- Blockers: Architecture advice only; no application code edits, docs edits, migrations, tests, or DB writes were performed.
- Next architecture actions: Clean the remaining conflicting Master Design sections, then give Build an additive migration plan starting with `base.entity` and `status.latest` before touching Spot/Chart membership.

## Session: Entity/status/Plane implementation kickoff

- Intent: Start the recommended Build sequence for `base.entity`, `status.latest`, `plane.series`, Plane snapshots/rollups, and Spot/Chart series membership.
- Scope changed:
  - `web/Flux/src/flux/settings.py`
  - `web/Flux/src/flux/base/models.py`
  - `web/Flux/src/flux/base/admin.py`
  - `web/Flux/src/flux/base/migrations/0012_entity.py`
  - `web/Flux/src/flux/status/*`
  - `web/Flux/src/flux/plane/apps.py`
  - `web/Flux/src/flux/plane/models.py`
  - `web/Flux/src/flux/plane/services.py`
  - `web/Flux/src/flux/plane/admin.py`
  - `web/Flux/src/flux/plane/migrations/0001_initial.py`
  - `web/Flux/src/flux/plane/migrations/0002_backfill_spot_chart_series.py`
  - `web/Flux/src/flux/live/models.py`
  - `web/Flux/src/flux/live/management/commands/import_live_scope_csv.py`
  - `web/Flux/src/flux/live/migrations/0002_point_series.py`
  - `web/Flux/src/flux/trace/models.py`
  - `web/Flux/src/flux/trace/migrations/0003_signal_series.py`
  - `web/Flux/src/flux/chart/importer.py`
- Result:
  - Added kernel `base.Entity` with stable GUID, kind, natural key hash, display name, and retired timestamp.
  - Linked `base.Device` and `base.Tag` to nullable transition `entity` FKs and backfilled all existing rows.
  - Added `flux.status` Django app and schema-qualified `status.latest` latest evidence table keyed to `base.Entity`.
  - Added `flux.plane` Django app models for `plane.series`, `plane.latest`, and `plane.window_stat`.
  - Backfilled one Plane series per existing `base.tag`, then created missing Base tags/Plane series for current Spot/Chart memberships and linked every current Spot point and Trace signal to `plane.series`.
  - Updated Spot and Chart CSV import paths to create/attach `plane.series` for future imports.
- Verification:
  - `uv run python manage.py check` passed.
  - `uv run python manage.py makemigrations --check --dry-run` passed.
  - `uv run python manage.py migrate` applied new migrations locally.
  - Schema-qualified tables confirmed with `to_regclass`: `base.entity`, `status.latest`, `plane.series`, `plane.latest`, and `plane.window_stat`.
  - Backfill counts after migration: `base.tag` entity links `458026/458026`, `base.device` entity links `54/54`, `plane.series` `458026`, Spot series links `26/26`, Chart series links `8083/8083`.
  - `uv run python manage.py test flux.base flux.live flux.trace flux.sim flux.field flux.serve dashboard --keepdb` passed: 259 tests, 4 skipped.
- Next architecture actions: Move read paths from legacy `runtime.RuntimeTag`/`LatestTagValue`/`TagSample` toward Plane latest/window APIs, then start writing `status.latest` from Serve/Opt/Bridge workers.

## Session: Plane/status write-path continuation

- Intent: Continue after the schema kickoff by populating Plane and Status from existing runtime sampler/monitor paths without breaking current RuntimeTag read surfaces.
- Scope changed:
  - `web/Flux/src/flux/plane/services.py`
  - `web/Flux/src/flux/plane/runtime.py`
  - `web/Flux/src/flux/plane/migrations/0003_backfill_runtime_snapshots.py`
  - `web/Flux/src/flux/status/services.py`
  - `web/Flux/src/flux/opt/services.py`
  - `web/Flux/src/flux/serve/monitor.py`
  - `serve/worker.py`
  - `architecture/core_area_files.md`
  - `architecture/daily/architecture_2026-05-25/architecture_2026-05-25.md`
- Result:
  - Added Plane services for resolving `plane.series` from full tag paths, mirroring runtime samples into `plane.latest`, recomputing `plane.window_stat` for today/rolling 7d/rolling 30d, and writing per-series quality status to `status.latest`.
  - Updated `flux.opt.services.sample_runtime_tags()` to keep legacy `LatestTagValue`/`TagSample` writes and mirror the same samples into Plane/Status.
  - Updated `flux.plane.runtime.sample_runtime_bad_quality()` to mirror bad-quality evidence into Plane/Status.
  - Added Status services for entity resolution plus single/bulk latest-status upserts.
  - Updated generic `serve.worker.run_worker_heartbeat()` to publish worker status into `status.latest`.
  - Updated `flux.serve.monitor.upsert_snapshot()` to publish service/bridge/field-endpoint probe status into `status.latest` while preserving existing `ServeServiceSnapshot` behavior.
  - Added runtime backfill migration for `plane.latest` and `plane.window_stat` from existing `LatestTagValue`, `TagSample`, and `DailyTagExtreme` rows.
  - Updated Spot scoped-card selectors to prefer linked Plane latest/window snapshots, while retaining RuntimeTag fallback for unlinked or not-yet-populated points.
- Verification:
  - `uv run python manage.py check` passed.
  - `uv run python manage.py makemigrations --check --dry-run` passed.
  - `uv run python manage.py migrate` applied `plane.0003_backfill_runtime_snapshots` locally.
  - `uv run python manage.py test flux.base flux.live flux.trace flux.sim flux.field flux.serve dashboard --keepdb` passed after the Plane write-path changes and again after Spot selector changes: 259 tests, 4 skipped.
  - Local counts after a monitor refresh: `plane.series=458026`, `plane.latest=101`, `plane.window_stat=0`, `status.latest=18`. Window stats are zero because the current local runtime history has no numeric samples inside the active today/rolling windows.
- Next architecture actions: Move Spot selectors to read Plane latest/window/status snapshots with RuntimeTag fallback, then migrate Chart read APIs to Plane/QuestDB keys before retiring RuntimeTag as the primary acquisition identity.

## Session: Chart Plane identity continuation

- Intent: Continue the Plane transition by moving Chart profile payload identity and seeded chart config toward `TraceSignal.series` / `plane.series` while preserving existing TraceCachePoint and RuntimeTag fallback behavior.
- Scope changed:
  - `web/Flux/src/flux/trace/models.py`
  - `web/Flux/src/flux/chart/cache.py`
  - `web/Flux/src/flux/chart/data_plane.py`
  - `web/Flux/src/flux/chart/questdb_data_plane.py`
  - `web/Flux/src/flux/chart/control.py`
  - `web/Flux/src/flux/chart/providers/nav_wells.py`
  - `web/Flux/src/flux/sim/fluxolot_fishtank.py`
  - `web/Flux/src/flux/cell/services.py`
  - `web/Flux/src/flux/base/annotations.py`
  - `web/Flux/src/flux/trace/tests.py`
  - `architecture/core_area_files.md`
  - `architecture/daily/architecture_2026-05-25/architecture_2026-05-25.md`
- Result:
  - Added `TraceSignal` helpers for Plane-backed display label, storage key, chart full path, and historian path selection.
  - Updated Django and raw PostgreSQL chart payloads to include `seriesId`/`storageKey` and prefer `plane.series.storage_key` / `base.tag` metadata over RuntimeTag metadata when linked.
  - Updated QuestDB chart metadata payloads to expose Plane series identity while keeping QuestDB trace rows scoped by TraceSignal for compatibility.
  - Updated nav-well, Fluxolot, and demo Cell chart seed paths to attach Plane series for new TraceSignal rows.
  - Updated annotation signal resolution to recognize Plane chart paths while retaining legacy RuntimeTag full-path matching for persisted annotation compatibility.
- Verification:
  - `uv run python manage.py check` passed.
  - `uv run python manage.py makemigrations --check --dry-run` passed.
  - `uv run python manage.py migrate --plan` reported no planned operations.
  - `uv run python manage.py test flux.trace --keepdb` passed: 43 tests, 1 skipped.
  - `uv run python manage.py test flux.base flux.live flux.trace flux.sim flux.cell --keepdb` passed: 172 tests, 4 skipped.
  - `uv run python manage.py test flux.base flux.live flux.trace flux.sim flux.field flux.serve dashboard --keepdb` passed: 260 tests, 4 skipped.
- Next architecture actions: Replace remaining Chart runtime sample/history reads with Plane-owned series/time-range APIs, then decide whether TraceCachePoint should remain a Chart-local cache or become a materialized view over Plane/QuestDB history.

## Session: Chart Plane sample-read continuation

- Intent: Route the remaining generic Flux.chart historical/streaming sample reads through a Plane-owned series sample boundary without introducing a new raw history table yet.
- Scope changed:
  - `web/Flux/src/flux/plane/samples.py`
  - `web/Flux/src/flux/chart/selectors.py`
  - `web/Flux/src/flux/chart/views.py`
  - `web/Flux/src/flux/trace/tests.py`
  - `architecture/core_area_files.md`
  - `architecture/daily/architecture_2026-05-25/architecture_2026-05-25.md`
- Result:
  - Added `flux.plane.samples` as the transition sample-read boundary for Chart generic/streaming reads.
  - Mapped legacy `TagSample` rows onto Plane series metadata using `plane.series`/`base.tag` by full path, exposing `seriesId`, `storageKey`, and Plane-backed names when linked.
  - Updated `flux.chart.selectors.trace_sample_series()` to consume Plane sample rows instead of importing/querying `TagSample` directly.
  - Updated the Chart recent-samples card to obtain its queryset through the Plane sample boundary.
  - Confirmed direct `TagSample`/`LatestTagValue` imports are gone from `flux.chart` runtime read code; remaining `RuntimeTag` references in Chart are import/seed config writers.
- Verification:
  - `uv run python manage.py check` passed.
  - `uv run python manage.py makemigrations --check --dry-run` passed.
  - `uv run python manage.py test flux.trace --keepdb` passed: 44 tests, 1 skipped.
  - `uv run python manage.py test flux.base flux.live flux.trace flux.sim flux.field flux.serve dashboard --keepdb` passed: 261 tests, 4 skipped.
- Next architecture actions: Decide the final ownership of `TraceCachePoint`: either keep it as Chart-local cache keyed by `TraceSignal`, or replace/materialize it from a Plane/QuestDB history contract before retiring RuntimeTag as acquisition identity.

## Session: Plane sample replacement cleanup

- Intent: Complete the requested replacement of Chart-local `TraceCachePoint` storage with Plane-owned `plane.sample` storage and clean active references.
- Scope changed:
  - `web/Flux/src/flux/plane/models.py`
  - `web/Flux/src/flux/plane/admin.py`
  - `web/Flux/src/flux/plane/services.py`
  - `web/Flux/src/flux/plane/sample_seed.py`
  - `web/Flux/src/flux/plane/migrations/0004_sample_backfill_trace_cache.py`
  - `web/Flux/src/flux/trace/models.py`
  - `web/Flux/src/flux/trace/admin.py`
  - `web/Flux/src/flux/trace/migrations/0004_drop_trace_cache_point.py`
  - `web/Flux/src/flux/chart/cache.py`
  - `web/Flux/src/flux/chart/data_plane.py`
  - `web/Flux/src/flux/chart/questdb_data_plane.py`
  - `web/Flux/src/flux/chart/control.py`
  - `web/Flux/src/flux/chart/providers/nav_wells.py`
  - `web/Flux/src/flux/cell/services.py`
  - `web/Flux/src/flux/cell/views.py`
  - `web/Flux/src/flux/trace/tests.py`
  - `web/Flux/src/flux/cell/tests.py`
  - `web/Flux/src/flux/sim/tests_fluxolot_fishtank.py`
  - `web/Flux/src/flux/sim/management/commands/install_fluxolot_fishtank.py`
  - `web/Flux/src/flux/serve/management/commands/flux_worker.py`
  - `web/Flux/src/flux/serve/management/commands/flux_trace_worker.py`
  - `docs/charts-architecture.md`
  - `docs/apps/charts.md`
  - `docs/trace-architecture.md`
  - `docs/operator-guide.md`
  - `docs/runbooks/fluxolot-fishtank.md`
  - `web/Flux/README.md`
  - `architecture/core_area_files.md`
  - `architecture/agent_notices.md`
- Result:
  - Added `plane.Sample` / `plane.sample` as the durable local chart history table keyed by `plane.series` and timestamp.
  - Backfilled existing `TraceCachePoint` rows into `plane.sample`; local count after migration was `4,174,697` rows.
  - Dropped active `TraceCachePoint` model/table through `trace.0004_drop_trace_cache_point`.
  - Moved Chart cache payloads, Postgres data-plane SQL, QuestDB export, nav-well seeding, Fluxolot seeding, Cell demo sampling, and runtime mirroring to `plane.sample`.
  - Renamed operator-facing Plane proof flags to `--plane-samples-all`, `--plane-sample-limit`, and `--plane-sample-batch-size`.
  - Left compatibility-named Python functions in place for a follow-up rename; they already read/write Plane samples.
- Verification:
  - `uv run python manage.py migrate` applied `plane.0004_sample_backfill_trace_cache` and `trace.0004_drop_trace_cache_point` locally.
  - `uv run python manage.py migrate --plan` reported no planned operations after applying.
  - Local `to_regclass` check returned `trace_tracecachepoint=None` and `plane.sample='plane.sample'`.
  - `uv run python manage.py test flux.trace flux.cell flux.sim.tests_fluxolot_fishtank --keepdb` passed: 71 tests, 2 skipped.
  - `uv run python manage.py test flux.base flux.live flux.trace flux.sim flux.field flux.serve dashboard --keepdb` passed: 261 tests, 4 skipped.
  - `uv run python manage.py check` and `uv run python manage.py makemigrations --check --dry-run` passed after cleanup.
- Next architecture actions: Rename compatibility-named Python functions/modules around Plane sample sync and move QuestDB from signal-scoped rows to Plane-series rows.

## Session: Plane sample API and QuestDB series-key cleanup

- Intent: Complete the requested Plane cleanup by moving generic Chart sample reads fully onto `plane.sample`, renaming cache-named Python APIs/modules, and changing QuestDB storage from signal-scoped rows to Plane-series rows.
- Scope changed:
  - `web/Flux/src/flux/plane/samples.py`
  - `web/Flux/src/flux/plane/sample_seed.py`
  - `web/Flux/src/flux/plane/__init__.py`
  - `web/Flux/src/flux/chart/cache.py`
  - `web/Flux/src/flux/chart/control.py`
  - `web/Flux/src/flux/chart/data_plane.py`
  - `web/Flux/src/flux/chart/questdb_data_plane.py`
  - `web/Flux/src/flux/chart/providers/nav_wells.py`
  - `web/Flux/src/flux/chart/selectors.py`
  - `web/Flux/src/flux/chart/views.py`
  - `web/Flux/src/static/flux/chart/data.js`
  - `web/Flux/src/templates/trace/index.html`
  - `web/Flux/src/dashboard/management/commands/flux_doctor_state.py`
  - `web/Flux/src/flux/sim/management/commands/install_fluxolot_fishtank.py`
  - `web/Flux/src/flux/serve/management/commands/flux_worker.py`
  - `web/Flux/src/flux/serve/management/commands/flux_trace_worker.py`
  - `web/Flux/src/flux/trace/management/commands/seed_nav_well_trace.py`
  - `web/Flux/src/flux/trace/management/commands/sync_trace_questdb.py`
  - `web/Flux/src/flux/trace/tests.py`
  - `web/Flux/src/flux/trace/test_e2e_playwright.py`
  - `web/Flux/src/flux/serve/test_full_integration_fluxolot_fishtank.py`
  - `scripts/flux`
  - `tests/test_flux_cli.py`
  - `docs/charts-architecture.md`
  - `docs/operator-guide.md`
  - `architecture/core_area_files.md`
- Result:
  - `flux.plane.samples.recent_series_samples()` now reads `plane.sample` rows directly instead of legacy `TagSample` rows.
  - The Chart recent-samples card also uses `plane.sample` rows and renders series metadata.
  - Renamed Python APIs from cache wording to Plane sample wording: `plane_sample_payload()`, `sync_plane_samples()`, `PlaneSampleSyncResult`, and `seed_plane_samples_from_runtime_history()`.
  - Replaced the old Plane trace-cache module with `flux.plane.sample_seed`.
  - Changed QuestDB export/read schema to `plane_samples(series_id, storage_key, ts, value, quality)`, with Chart payloads mapping `TraceSignal.series_id` to shared Plane-series samples at read time.
  - Updated Flux doctor QuestDB state to report `plane_samples`.
- Verification:
  - `uv run python manage.py check` passed.
  - `uv run python manage.py makemigrations --check --dry-run` passed.
  - `uv run python manage.py test flux.trace flux.cell flux.sim.tests_fluxolot_fishtank flux.serve.tests --keepdb` passed: 105 tests, 2 skipped.
  - `uv run python manage.py test flux.base flux.live flux.trace flux.sim flux.field flux.serve dashboard --keepdb` passed: 261 tests, 4 skipped.
  - `uv run pytest tests/test_flux_cli.py` passed: 23 tests.
  - `uv run python manage.py migrate --plan` reported no planned operations.
  - Grep checks found no active references to the removed cache API names, QuestDB `trace_points`/`signal_key`, or `TagSample` in `flux.plane.samples`.

## Session: public `base_*` table ownership review

- Intent: Review remaining `public.base_*` PostgreSQL tables and determine whether Flux still needs them after the schema-qualified Base/Sim/Cell/Plane work.
- Scope reviewed:
  - `architecture/agent_notices.md`
  - `architecture/core_area_files.md`
  - `web/Flux/src/flux/base/models.py`
  - `web/Flux/src/flux/base/services.py`
  - `web/Flux/src/flux/base/field_config.py`
  - `web/Flux/src/flux/base/field_selectors.py`
  - `web/Flux/src/flux/base/migrations/0001_initial.py`, `0002_fieldagent_config_to_base.py`, `0003_sim_device_catalog.py`, `0006_simserver_tagprovider.py`, `0008_tagselection_config.py`, `0010_kernel_device_tag.py`, `0011_drop_legacy_device_tag_tables.py`, `0012_entity.py`
  - `web/Flux/src/flux/sim/models.py`
  - `web/Flux/src/flux/sim/output.py`, `rehydrate.py`, `tag_data_ingest.py`, `field_bridge.py`, `testing.py`, `views.py`
  - `web/Flux/src/flux/serve/field_supervisor.py`, `monitor.py`, `server_commands.py`
  - PostgreSQL catalog/read-only inspection of public `base_%` tables, row counts, sizes, and FKs.
- Database evidence:
  - Remaining public `base_*` tables: `base_fieldagentheartbeat`, `base_fieldendpoint`, `base_simdriver`, `base_simserver`, `base_tagnode`, `base_tagprovider`, `base_tagselection`.
  - Row counts: `base_tagnode=510073`, `base_tagprovider=2`, `base_tagselection=4`, `base_simserver=3`, `base_simdriver=7`, `base_fieldendpoint=8`, `base_fieldagentheartbeat=8`.
  - `base_tagnode` size was about `464 MB` total, making it the dominant migration/performance risk.
- Architectural findings:
  - High: none of the remaining `public.base_*` tables are safe to drop directly; they are active provider catalog, sim config, endpoint config, or runtime evidence tables.
  - Medium: provider catalog tables are logically Flux.sim and should move as a cluster to a `sim` schema naming contract.
  - Medium: `base_fieldendpoint` mixes desired endpoint config with observed runtime status; split config to Sim and runtime truth to Serve.
  - Medium: `base_fieldagentheartbeat` is active Flux.serve runtime evidence, not Base identity/configuration.
- Report path: `arch_review.md`.
- Blockers: DB evidence is from the local `flux` database via read-only `psql`; other environments may have different row counts, but ownership conclusions are code-backed.
- Next architecture actions: Before Build moves these tables, settle names for `sim.provider_node` vs `sim.catalog_node`, `sim.endpoint` vs `sim.server`, and `serve.sim_agent_heartbeat` vs `serve.endpoint_runtime`.

## Session: Flux.sim provider catalog schema migration

- Intent: Implement phase 1 from the public `base_*` table review by moving Flux.sim provider catalog/configuration tables out of the public Base app-prefix namespace and into the `sim` PostgreSQL schema.
- Scope changed:
  - `web/Flux/src/flux/sim/models.py`
  - `web/Flux/src/flux/base/models.py`
  - `web/Flux/src/flux/base/admin.py`
  - `web/Flux/src/flux/sim/admin.py`
  - `web/Flux/src/flux/base/services.py`
  - `web/Flux/src/flux/base/tests.py`
  - `web/Flux/src/flux/sim/output.py`
  - `web/Flux/src/flux/sim/rehydrate.py`
  - `web/Flux/src/flux/sim/tag_data_ingest.py`
  - `web/Flux/src/flux/sim/views.py`
  - `web/Flux/src/flux/sim/testing.py`
  - `web/Flux/src/flux/sim/tests.py`
  - `web/Flux/src/flux/sim/tests_field_bridge.py`
  - `web/Flux/src/flux/sim/tests_tag_data_ingest.py`
  - `web/Flux/src/flux/sim/tests_export_compare.py`
  - `web/Flux/src/flux/sim/test_e2e_playwright.py`
  - `web/Flux/src/flux/sim/jobs.py`
  - `web/Flux/src/flux/sim/provider_tree.py`
  - `web/Flux/src/flux/sim/value_profiles.py`
  - `web/Flux/src/flux/sim/field_bridge.py`
  - `web/Flux/src/flux/serve/test_full_integration_fluxolot_fishtank.py`
  - `web/Flux/src/flux/sim/migrations/0014_provider_catalog_schema.py`
  - `web/Flux/src/flux/base/migrations/0013_remove_sim_catalog_state.py`
  - `docs/Master Design.md`
  - `architecture/core_area_files.md`
  - `architecture/daily/architecture_2026-05-25/architecture_2026-05-25.md`
- Result:
  - `public.base_tagprovider` -> `sim.provider`.
  - `public.base_tagnode` -> `sim.provider_node`.
  - `public.base_tagselection` -> `sim.provider_selection`.
  - `public.base_simserver` -> `sim.server`.
  - `public.base_simdriver` -> `sim.driver`.
  - Used `ALTER TABLE ... SET SCHEMA` plus `RENAME TO` inside `SeparateDatabaseAndState`; no row-copy migration was introduced.
  - Flux.sim models now own the provider catalog classes. Legacy names remain as aliases for compatibility.
  - Base model state no longer owns the provider catalog cluster; remaining public Base tables are `base_fieldendpoint` and `base_fieldagentheartbeat` for the deferred phase-2 endpoint/runtime split.
- Verification:
  - Pre-migration row counts: `base_simdriver=7`, `base_simserver=3`, `base_tagnode=510073`, `base_tagprovider=2`, `base_tagselection=4`.
  - Post-migration row counts: `sim.driver=7`, `sim.server=3`, `sim.provider_node=510073`, `sim.provider=2`, `sim.provider_selection=4`.
  - PostgreSQL catalog check showed no remaining public provider catalog tables; only `public.base_fieldendpoint` and `public.base_fieldagentheartbeat` remain.
  - FK catalog check showed `sim.device` and `sim.tag` now reference `sim.driver`, `sim.server`, `sim.provider`, and `sim.provider_node`.
  - `uv run python web/Flux/manage.py test flux.base flux.sim --noinput` passed: 83 tests, 1 skipped.
  - `uv run python web/Flux/manage.py test dashboard flux.base flux.sim flux.serve --noinput` passed: 179 tests, 2 skipped.
  - `uv run python web/Flux/manage.py makemigrations base sim --check --dry-run`, `migrate --check`, `check`, and targeted `ruff check` passed.
- Next architecture actions: Phase 2 should split `base_fieldendpoint` desired endpoint config from `base_fieldagentheartbeat`/runtime evidence into `sim.endpoint` and `serve.sim_agent_heartbeat` or `serve.endpoint_runtime`.

## Session: Flux.sim endpoint / Flux.serve heartbeat schema migration

- Intent: Complete phase 2 from the public `base_*` table review by moving endpoint configuration and FieldAgent heartbeat runtime evidence out of public Base app-prefix tables.
- Scope changed:
  - `web/Flux/src/flux/sim/models.py`
  - `web/Flux/src/flux/serve/models.py`
  - `web/Flux/src/flux/base/models.py`
  - endpoint/heartbeat imports across dashboard, flux.sim, flux.serve, flux.field, and tests
  - `web/Flux/src/flux/sim/migrations/0015_endpoint_schema.py`
  - `web/Flux/src/flux/serve/migrations/0004_sim_agent_heartbeat_schema.py`
  - `web/Flux/src/flux/base/migrations/0014_remove_endpoint_runtime_state.py`
  - `docs/Master Design.md`
  - `architecture/core_area_files.md`
  - `arch_review.md`
- Result:
  - `public.base_fieldendpoint` -> `sim.endpoint`.
  - `public.base_fieldagentheartbeat` -> `serve.sim_agent_heartbeat`.
  - Used `ALTER TABLE ... SET SCHEMA` plus `RENAME TO` inside `SeparateDatabaseAndState`; no row-copy migration was introduced.
  - `flux.sim.models.Endpoint` now owns endpoint configuration. `flux.serve.models.SimAgentHeartbeat` now owns FieldAgent runtime evidence.
  - `flux.base.models` retains compatibility aliases only; active imports were moved to Flux.sim/Flux.serve ownership.
- Verification:
  - Pre-migration row counts: `base_fieldendpoint=8`, `base_fieldagentheartbeat=8`.
  - Post-migration row counts: `sim.endpoint=8`, `serve.sim_agent_heartbeat=8`.
  - PostgreSQL catalog check showed no remaining public `base_*` tables.
  - FK catalog check showed `sim.device.endpoint_id -> sim.endpoint.id` and `serve.sim_agent_heartbeat.endpoint_id -> sim.endpoint.id`.
  - `uv run python web/Flux/manage.py test dashboard flux.base flux.sim flux.serve flux.field --noinput` passed: 189 tests, 2 skipped.
  - `uv run python web/Flux/manage.py makemigrations base sim serve --check --dry-run`, `migrate --check`, `check`, and targeted `ruff check` passed.
- Next architecture actions: Remove transition aliases after downstream code stops importing Sim/Serve ownership names from `flux.base.models`; then tighten endpoint runtime truth so UI/monitoring uses heartbeat/status evidence instead of stored `Endpoint.status` alone.

## Session: Flux.mine Logix hello_world exploration

- Intent: Establish a dedicated Mine exploration note and answer whether the new `logix_samples/hello_world.L5X`/`.L5K` sample makes sense as a seed for Flux.mine, Flux.build, and Deep.plc.
- Scope reviewed:
  - `architecture/agent_notices.md`
  - `architecture/core_area_files.md`
  - `logix_samples/hello_world.L5X`
  - `logix_samples/hello_world.L5K`
  - `mine/src/flux_mine/plc/models.py`
  - `mine/src/flux_mine/plc/l5x.py`
  - `mine/src/flux_mine/plc/l5k.py`
  - `mine/src/flux_mine/imports.py`
  - `web/Flux/src/flux/mine/models.py`
  - `web/Flux/src/flux/mine/services.py`
  - `web/Flux/src/flux/build/models.py`
  - `web/Flux/src/flux/build/services.py`
  - `build/src/flux_build/targets/rockwell.py`
  - `deep/src/flux_deep/hello_world.py`
  - `deep/tests/test_hello_world.py`
  - `docs/deep-openplc.md`
  - `docs/Master Design.md`
- Architectural findings:
  - Medium: The Mine -> Build -> Deep.plc direction is sound, but responsibilities must stay separate: Mine deserializes/persists source facts, Build serializes artifacts, and Deep.plc functionally tests bounded behavior.
  - Medium: Current Mine PLC persistence captures controller/data type/member/tag facts but not tasks, routines, rungs, instruction references, or tag initial data payloads, so it cannot yet rebuild or emulate the sample.
  - Medium: Current Build has no L5X/L5K reconstruction target; it should consume Mine’s canonical persisted model rather than introducing a separate parser-owned build model.
  - Medium: Current Deep hello_world workspace is useful precedent but uses a different generated source model and is not yet driven by the new mined Logix sample.
  - Low: `.ACD` should remain reference-only until Flux defines an explicit supported Rockwell export/import path.
- Report/path: `architecture/mine/flux_mine_exploration.md`.
- Blockers: Architecture-only exploration; no application code edits, tests, serializers, migrations, or Deep runtime execution were performed.
- Next architecture actions: After Build starts, review the canonical PLC model extension, additive Mine tables for program/task/routine/rung/reference facts, and first L5X parse->persist->serialize->parse parity tests.

## Session: Flux.mine schema migration strategy

- Intent: Strategize moving current Flux.mine data stores out of `public` into a dedicated PostgreSQL `mine` schema before expanding PLC modeling.
- Scope reviewed:
  - `architecture/agent_notices.md`
  - `architecture/core_area_files.md`
  - `architecture/mine/flux_mine_exploration.md`
  - `web/Flux/src/flux/mine/models.py`
  - `web/Flux/src/flux/mine/migrations/0001_initial.py`
  - `web/Flux/src/flux/mine/migrations/0002_hmicomponentactionfact_hmicomponentparameterfact_and_more.py`
  - `web/Flux/src/flux/build/models.py`
  - `web/Flux/src/flux/build/migrations/0001_initial.py`
  - `web/Flux/src/flux/build/migrations/0002_alter_buildrun_target_hmimapselection.py`
  - `web/Flux/src/flux/cell/models.py`
  - `web/Flux/src/flux/cell/migrations/0002_draftcellsource.py`
  - `web/Flux/src/flux/cell/migrations/0003_draftcellrelationship_draftcellvisual.py`
  - `web/Flux/src/flux/cell/migrations/0005_cell_schema_tables.py`
  - `web/Flux/src/flux/sim/migrations/0014_provider_catalog_schema.py`
  - `web/Flux/src/flux/e2e.py`
- Architectural findings:
  - Medium: The schema move should happen before adding PLC program/task/routine/rung tables, otherwise Flux creates more public Mine tables and more naming drift to clean up.
  - Medium: Use a manual `SeparateDatabaseAndState` migration with `CREATE SCHEMA`, `ALTER TABLE SET SCHEMA`, `RENAME`, and `AlterModelTable`; a naive autogenerated table rename is not explicit enough for schema-qualified ownership.
  - Medium: Keep Python model/class renames out of this migration. First move storage to `mine.*`; later decide whether to rename `*Fact` classes or introduce canonical PLC models.
  - Medium: Cross-app FKs from Build and Cell should survive PostgreSQL table movement, but Build must verify catalog FK targets and focused tests after migration.
- Report/path: `architecture/mine/flux_mine_exploration.md`.
- Blockers: Architecture-only strategy; no application code edits, migrations, tests, or live DB row-count queries were performed.
- Next architecture actions: Re-review after Build drafts `mine.0003_mine_schema_tables` and model `Meta.db_table` updates, especially postcondition checks and fresh-DB migration ordering.

## Session: Flux.mine schema migration implementation

- Intent: Implement the first Build slice for Flux.mine by moving current Mine storage into PostgreSQL schema `mine` without adding PLC graph tables or renaming Python model classes.
- Scope changed:
  - `web/Flux/src/flux/mine/models.py`
  - `web/Flux/src/flux/mine/migrations/0003_mine_schema_tables.py`
  - `architecture/mine/flux_mine_exploration.md`
  - `architecture/core_area_files.md`
  - `architecture/daily/architecture_2026-05-25/architecture_2026-05-25.md`
- Result:
  - Current Mine model `Meta.db_table` values now point to `"mine"."..."` tables.
  - Added manual `SeparateDatabaseAndState` migration `mine.0003_mine_schema_tables`.
  - Migration creates schema `mine`, moves old `public.mine_*` tables with `ALTER TABLE ... SET SCHEMA`, renames them to concise Mine-owned names, updates migration state, and verifies target/old table postconditions.
  - No parser expansion, serializer work, Deep.plc runtime work, PLC graph tables, or Python class renames were included.
- Local DB evidence:
  - Before counts: `mine_minerun=1`, `mine_hmiscreenfact=8`, `mine_hmicomponentfact=1612`, `mine_hmitagreferencefact=858`, `mine_hmicomponentactionfact=355`, `mine_hmicomponentparameterfact=40`, `mine_hmicomponentstatefact=676`, `mine_hmiglobalobjectlinkfact=22`; PLC and parameter/VBA tables were 0 rows.
  - After counts: `mine.run=1`, `mine.hmi_screen=8`, `mine.hmi_component=1612`, `mine.hmi_tag_reference=858`, `mine.hmi_component_action=355`, `mine.hmi_component_parameter=40`, `mine.hmi_component_state=676`, `mine.hmi_global_object_link=22`; corresponding PLC and parameter/VBA target tables remained 0 rows.
  - Catalog check found only target `mine.*` tables from the expected set and no expected old public Mine tables.
  - FK catalog check showed Build/Cell and Mine-internal FKs resolving to `mine.*` relation targets.
- Verification:
  - `uv run python web/Flux/manage.py makemigrations mine --check --dry-run` passed.
  - `uv run python web/Flux/manage.py makemigrations --check --dry-run` passed.
  - `uv run ruff check web/Flux/src/flux/mine/models.py web/Flux/src/flux/mine/migrations/0003_mine_schema_tables.py` passed.
  - `uv run python web/Flux/manage.py migrate mine --noinput` applied locally.
  - `uv run python web/Flux/manage.py migrate --check` passed after local migration.
  - `uv run python web/Flux/manage.py check` passed.
  - `uv run python web/Flux/manage.py test flux.mine flux.build flux.cell dashboard --noinput` passed before local migration in a rebuilt test DB: 94 tests, 4 skipped.
  - A later no-keepdb rerun hit a PostgreSQL `test_flux` create/drop lifecycle failure after stale DB cleanup; retry with `--keepdb` passed: 94 tests, 4 skipped.
- Next Build action: Add PLC graph tables directly under `mine.*` and begin L5X hello_world parser persistence against the new schema boundary.

## Session: Deep.schematics schema work scope

- Intent: Capture Bobby's corrected `Deep.schematics` direction as a separate work scope, centered on Flux-native schematic primitives rather than source drawing ingestion.
- Scope reviewed:
  - `architecture/agent_notices.md`
  - `architecture/core_area_files.md`
  - `docs/Master Design.md`
  - `deep/README.md`
  - `docs/deep-openplc.md`
  - Current chat architecture decisions for source/circuit/component primitives, component generation, terminals, roles, and circuit potentials.
- Architectural findings:
  - High: `Deep.schematics` should start from Source, Circuit, and Component primitives, not imported PDF/SVG/CAD drawings.
  - High: component templates must declare potential interfaces; circuit/source compilation resolves concrete terminal potentials and conditional bindings.
  - High: starters and power supplies are multi-circuit relational components; 24 VDC control and 480 VAC power circuits must be related behaviorally, not merged electrically.
  - Medium: the first persistence boundary should be isolated to `schematics.*` with no first-slice FKs to Base, Plane, Sim, Mine, Status, Ignition, or PLC runtime tables.
- Report/path: `architecture/schematics_architecture.md`.
- Blockers: Architecture-only scope; no application code, migrations, tests, or database changes were performed.
- Next architecture actions: Re-review after Build drafts the `schematics` schema migration and first motor-starter fixture/compiler tests.

## Session: Flux.mine PLC source graph implementation

- Intent: Continue from the Mine schema move by adding the first persisted PLC source graph for the `hello_world` Logix samples.
- Scope changed:
  - `mine/src/flux_mine/plc/models.py`
  - `mine/src/flux_mine/plc/l5x.py`
  - `mine/src/flux_mine/plc/l5k.py`
  - `mine/tests/test_l5x.py`
  - `mine/tests/test_l5k.py`
  - `web/Flux/src/flux/mine/models.py`
  - `web/Flux/src/flux/mine/services.py`
  - `web/Flux/src/flux/mine/tests.py`
  - `web/Flux/src/flux/mine/migrations/0004_plc_source_graph.py`
  - `architecture/mine/flux_mine_exploration.md`
  - `architecture/core_area_files.md`
  - `architecture/daily/architecture_2026-05-25/architecture_2026-05-25.md`
- Result:
  - Pure PLC model now includes tasks, program main routine names, routines, and rungs.
  - L5X parser now recovers hello_world task/program/routine/rung structure and preserves tag data payloads in tag raw metadata.
  - L5K parser now recovers the hello_world program/routine/rung/task subset.
  - Mine persistence now stores PLC programs, tasks, scheduled programs, routines, and rungs under `mine.*`.
  - `mine.0004_plc_source_graph` applied locally and created `mine.plc_program`, `mine.plc_task`, `mine.plc_scheduled_program`, `mine.plc_routine`, and `mine.plc_rung`.
- Boundaries preserved:
  - No Flux.build serializer was added.
  - No Deep.plc execution/emulation was added.
  - No broad Logix grammar or instruction-reference persistence was added.
  - Program-scope tags still use text `scope`; tag-to-program FK remains a later migration.
- Verification:
  - `uv run pytest mine/tests/test_l5x.py mine/tests/test_l5k.py` passed: 5 tests.
  - `uv run ruff check mine/src/flux_mine/plc/models.py mine/src/flux_mine/plc/l5x.py mine/src/flux_mine/plc/l5k.py` passed.
  - `uv run python web/Flux/manage.py makemigrations mine --check --dry-run` passed.
  - `uv run ruff check web/Flux/src/flux/mine/models.py web/Flux/src/flux/mine/services.py web/Flux/src/flux/mine/tests.py web/Flux/src/flux/mine/migrations/0004_plc_source_graph.py` passed.
  - `uv run python web/Flux/manage.py check` passed.
  - `uv run python web/Flux/manage.py migrate mine --noinput` applied `mine.0004_plc_source_graph` locally.
  - Catalog checks showed the new graph tables exist under `mine`; counts were 0 before importing new PLC samples into the local dev DB.
  - `uv run python web/Flux/manage.py migrate --check` passed.
  - `uv run python web/Flux/manage.py makemigrations --check --dry-run` passed.
  - `uv run python web/Flux/manage.py test flux.mine flux.build flux.cell dashboard --noinput --keepdb` passed: 95 tests, 4 skipped.
- Next Build action: Add bounded RLL instruction/tag-reference extraction and persistence for the hello_world subset before starting Flux.build L5X serializer parity.

## Session: Flux.mine RLL instruction reference implementation

- Intent: Continue from the PLC source graph by extracting and persisting bounded RLL instruction/tag references for the hello_world subset.
- Scope changed:
  - `mine/src/flux_mine/plc/models.py`
  - `mine/src/flux_mine/plc/l5x.py`
  - `mine/src/flux_mine/plc/l5k.py`
  - `mine/tests/test_l5x.py`
  - `mine/tests/test_l5k.py`
  - `web/Flux/src/flux/mine/models.py`
  - `web/Flux/src/flux/mine/services.py`
  - `web/Flux/src/flux/mine/tests.py`
  - `web/Flux/src/flux/mine/migrations/0005_plc_instruction_references.py`
  - `architecture/mine/flux_mine_exploration.md`
  - `architecture/core_area_files.md`
  - `architecture/daily/architecture_2026-05-25/architecture_2026-05-25.md`
- Result:
  - Added a small parser for `XIO`, `XIC`, `TON`, `OTL`, `OTU`, and `COP` instruction calls.
  - Pure L5X/L5K parsing now attaches instruction and tag-reference dataclasses to rungs.
  - Mine persistence now stores `mine.plc_instruction` and `mine.plc_tag_reference` rows.
  - Tag references resolve against the containing program scope first, then `Global`.
  - The hello_world L5X persistence test verifies 12 instructions, 14 tag references, and all sample references resolved to `PlcTagFact` rows.
- Boundaries preserved:
  - No broad Logix grammar was claimed.
  - No Flux.build serializer was added.
  - No Deep.plc execution/emulation was added.
  - No tag-to-program FK migration was added.
- Verification:
  - `uv run pytest mine/tests/test_l5x.py mine/tests/test_l5k.py` passed: 5 tests.
  - `uv run ruff check mine/src/flux_mine/plc/models.py mine/src/flux_mine/plc/l5x.py mine/src/flux_mine/plc/l5k.py` passed.
  - `uv run python web/Flux/manage.py makemigrations mine --check --dry-run` passed.
  - `uv run ruff check web/Flux/src/flux/mine/models.py web/Flux/src/flux/mine/services.py web/Flux/src/flux/mine/tests.py web/Flux/src/flux/mine/migrations/0005_plc_instruction_references.py` passed.
  - `uv run python web/Flux/manage.py check` passed.
  - `uv run python web/Flux/manage.py migrate mine --noinput` applied `mine.0005_plc_instruction_references` locally.
  - Local table checks showed `mine.plc_instruction` and `mine.plc_tag_reference` exist and were empty before importing PLC samples into the local dev DB.
  - `uv run python web/Flux/manage.py migrate --check` passed.
  - `uv run python web/Flux/manage.py makemigrations --check --dry-run` passed.
  - `uv run python web/Flux/manage.py test flux.mine flux.build flux.cell dashboard --noinput` passed on a fresh test DB: 97 tests, 4 skipped.
  - A prior `--keepdb` run failed on unrelated stale dashboard fixture counts from the preserved test DB; fresh DB verification passed.
- Next Build action: Start generated L5X serializer parity from persisted Mine rows, then parse the generated artifact back through Mine and compare canonical graph/reference counts.

## Session: Flux.build L5X parity implementation

- Intent: Start Flux.build generated-source reconstruction by serializing persisted Mine PLC rows to L5X and parsing the generated artifact back through Flux.mine.
- Scope changed:
  - `build/src/flux_build/targets/logix_l5x.py`
  - `web/Flux/src/flux/build/models.py`
  - `web/Flux/src/flux/build/services.py`
  - `web/Flux/src/flux/build/tests.py`
  - `web/Flux/src/flux/build/management/commands/flux_build_logix_l5x.py`
  - `web/Flux/src/flux/build/migrations/0003_buildrun_logix_l5x_target.py`
  - `architecture/mine/flux_mine_exploration.md`
  - `architecture/core_area_files.md`
  - `architecture/daily/architecture_2026-05-25/architecture_2026-05-25.md`
- Result:
  - Added minimal generated L5X serializer in `flux_build.targets.logix_l5x`.
  - Added `BuildRun.Target.LOGIX_L5X` and command `flux_build_logix_l5x`.
  - Extended Build's Mine reconstruction to include tasks, scheduled programs, routines, rungs, instructions, and tag references.
  - `build_logix_l5x_from_mine_run()` writes a `logix_l5x` artifact only after generated L5X parses back through Flux.mine with matching canonical counts.
  - Hello_world Build test verifies generated-source parse-back parity for controller/program/task/routine/rung/instruction/reference counts.
- Boundaries preserved:
  - No L5K serializer was added.
  - No Deep.plc execution/emulation was added.
  - No byte-perfect Rockwell export guarantee was made.
- Verification:
  - `uv run ruff check build/src/flux_build/targets/logix_l5x.py web/Flux/src/flux/build/models.py web/Flux/src/flux/build/services.py web/Flux/src/flux/build/tests.py web/Flux/src/flux/build/management/commands/flux_build_logix_l5x.py web/Flux/src/flux/build/migrations/0003_buildrun_logix_l5x_target.py` passed.
  - `uv run python web/Flux/manage.py makemigrations build --check --dry-run` passed.
  - `uv run python web/Flux/manage.py test flux.build --noinput` passed: 8 tests, 1 skipped.
  - `uv run python web/Flux/manage.py migrate build --noinput` applied `build.0003_buildrun_logix_l5x_target` locally.
  - `uv run python web/Flux/manage.py showmigrations build` showed all Build migrations applied through `0003`.
  - `uv run python web/Flux/manage.py migrate --check` passed.
  - `uv run python web/Flux/manage.py makemigrations --check --dry-run` passed.
  - `uv run python web/Flux/manage.py check` passed.
  - `uv run python web/Flux/manage.py test flux.mine flux.build flux.cell dashboard --noinput` passed: 98 tests, 4 skipped.
  - `uv run pytest build/tests` passed: 4 tests.
- Next Build action: Either add L5K serializer parity for hello_world or move into Deep.plc functional testing using the persisted instruction/reference model and bounded scan/time assertions.
