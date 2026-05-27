# Flux.mine PLC Recovery Exploration

Date: 2026-05-25

## Purpose

Document the architecture direction for using the new `logix_samples/hello_world.L5X` and `logix_samples/hello_world.L5K` files as a small, controlled proof for Flux.mine, Flux.build, and Deep.plc.

## Short Answer

Yes, the direction makes sense.

The clean split is:

1. **Flux.mine** deserializes PLC source files into a relational, provenance-rich PLC source model.
2. **Flux.build** serializes that model back into generated L5X/L5K artifacts.
3. **Deep.plc** functionally tests a bounded subset of PLC behavior from the mined/buildable model.

The important correction is that “mine tags” is not enough. For this to support rebuild and emulation, Mine needs controller, task, program, routine, rung, tag, datatype, and instruction-reference structure. It also needs enough raw source preservation to make round-trip behavior honest.

## Sample Observations

Reviewed source seeds:

- `logix_samples/hello_world.L5X`
- `logix_samples/hello_world.L5K`
- `logix_samples/hello_world.ACD` exists as a binary/source reference, but ACD import should remain out of scope unless a supported export/conversion path is defined.

The L5X/L5K pair describes a deliberately small ControlLogix project:

- Controller: `hello_world`
- Processor: `1756-L71`
- Revision: L5X reports major `37`, minor `11`; L5K reports `RSLogix 5000 v37.00` and controller `Major := 37`.
- Controller-scope tags: none in the sample.
- Program: `MainProgram`
- Main routine: `MainRoutine`
- Routine type: `RLL`
- Task: `MainTask`, continuous, scheduling `MainProgram`.
- Program-scope tags:
  - `hello : STRING`, initial value `hello`
  - `world : STRING`, initial value `world`
  - `hello_world : STRING`, initial empty string
  - `world_latch : BOOL`
  - `hello_TON : TIMER`, preset `1000`
  - `world_TON : TIMER`, preset `1000`
- Rungs:
  1. `XIO(world_latch)TON(hello_TON,?,?);`
  2. `XIC(hello_TON.DN)OTL(world_latch);`
  3. `XIC(world_latch)TON(world_TON,?,?);`
  4. `XIC(world_TON.DN)OTU(world_latch);`
  5. `[XIO(world_latch) COP(hello,hello_world,1) ,XIC(world_latch) COP(world,hello_world,1) ];`

This is a good first target because it exercises program scope, timers, a latch, string data payloads, and rung-level behavior without bringing in UDTs, AOIs, modules beyond Local, or complex task scheduling.

## Boundary Contract

### Flux.mine

Flux.mine should own ingestion and source facts:

- Parse L5X and L5K into one canonical PLC source model.
- Persist source provenance: original filename, format, hash, parser version, import diagnostics, and raw source metadata.
- Persist relational PLC structure: controller → tasks/programs → routines → rungs → instructions/tag references.
- Persist tag structure and initial data payloads, not only tag names/types.
- Preserve enough raw source fragments to support rebuild, diff, and explanation.

Flux.mine should not own simulation, runtime execution, or generated output writes except as import diagnostics/provenance.

### Flux.build

Flux.build should own generated artifacts:

- Read the canonical mined PLC model.
- Emit generated L5X first, then L5K after the canonical model is stable.
- Store build run, artifacts, diagnostics, hashes, and serializer version.
- Round-trip test by parsing the generated artifact back through Flux.mine and comparing canonical structure.

Build should not parse source files directly as its own private model. It should depend on Mine’s persisted/canonical model.

### Deep.plc

Deep.plc should own functional behavior checks:

- Execute or emulate a bounded subset of PLC behavior from the mined/buildable model.
- For this sample, support only the minimal RLL subset needed: `XIO`, `XIC`, `TON`, `OTL`, `OTU`, and `COP` against BOOL, TIMER, and STRING data.
- Use explicit scan cadence, simulated time bounds, and deterministic assertions.
- Keep OpenPLC/ST as a runtime target, but do not pretend OpenPLC runs Rockwell L5X directly.

Deep.plc should remain isolated from Django, Ignition, FieldAgent, and Flux.sim until a narrow runtime adapter exists.

## Minimal Relational Model Needed

Current Mine has useful PLC fact tables for controller, data type, member, and tag facts, but rebuild/emulation needs these additional concepts.

### Source artifact / import run

Existing `MineRun` can continue to act as the import run. The model should also make the source format and parser version visible in summary/raw diagnostics.

Needed fields or related rows:

- source format: `l5x` / `l5k`
- source hash
- parser version
- original export metadata
- diagnostics with severity/code/context
- optional raw source bytes or controlled raw fragment references if exact source preservation becomes a goal

### Controller

Existing `PlcControllerFact` is close, but controller raw metadata should include revision, data exchange id, project dates, redundancy/security metadata, and module/task counts when parsed.

### Task

New table/concept needed:

- controller FK
- name
- type: continuous/periodic/event
- priority
- rate/interval
- watchdog
- disabled/inhibited flags
- ordered scheduled programs
- raw attributes/source payload

### Program

Current `PlcProgram` exists only in the in-memory dataclass and is reconstructed indirectly from tag scopes. A persisted program table is needed:

- controller FK
- name
- main routine name
- disabled/test-edit/use-as-folder flags
- raw attributes

Program-scope tags should FK to program, not only store `scope='MainProgram'` text.

### Routine

New table/concept needed:

- program FK
- name
- type: `RLL`, ST, FBD, SFC, etc.
- raw attributes

### Rung

New table/concept needed:

- routine FK
- rung number
- order/index
- type
- text body
- comment
- raw XML/text fragment

This is architecture-critical: rungs are the smallest useful unit for reconstruction, explanation, and functional testing.

### Tag

Existing `PlcTagFact` should evolve from “tag catalog row” into a tag definition row with explicit scope ownership:

- controller FK
- nullable program FK for program-local tags
- scope kind: controller/program
- name
- data type
- tag type: base/alias/produced/consumed
- dimensions
- alias target
- radix
- constant/external access
- initial value representation:
  - raw L5K payload
  - decorated data JSON when present
  - normalized scalar/string value when safely available
- raw attributes/source fragment

### Data types and members

Existing data type/member facts are a good starting point. Keep them separate from tag rows. Built-in Logix structures such as `TIMER` can be represented as known built-ins for analysis/build without forcing rows for every built-in member unless needed.

### Instruction and tag references

For Deep.plc and analysis, Mine needs at least a bounded parsed representation of rung references:

- rung FK
- instruction mnemonic: `XIO`, `XIC`, `TON`, `OTL`, `OTU`, `COP`
- ordered operands as text
- resolved tag FK when possible
- member path, such as `.DN`
- reference role: read/write/control/timer/source/destination/unknown
- parser diagnostics when a reference cannot be resolved

This can start small for the hello_world subset. It does not need to be a complete Logix grammar on day one.

## Round-Trip Contract

Do not start by promising byte-perfect round trips. Use three explicit levels:

1. **Source-preserving replay**: if no mutation is requested, Flux can emit the original bytes from the stored source artifact and verify the hash. This is exact but not a rebuild.
2. **Canonical semantic round trip**: parse source → persist canonical model → serialize generated source → parse generated source → compare canonical structure. This is the right first Build target.
3. **Transforming rebuild**: generated L5X/L5K may intentionally change naming, layout, ordering, or metadata while preserving declared behavior/configuration.

For the sample, the first build milestone should be canonical semantic parity, not byte identity.

## L5X and L5K Strategy

Use L5X as the first canonical parser/serializer path because XML exposes structure directly. Use L5K as a parity check and later serializer target.

The sample pair should eventually produce the same canonical model:

- same controller identity
- same program/routine/rung graph
- same scoped tags
- same task schedule
- same rung text bodies after normalization

Differences in export metadata, whitespace, and representation details should be normalized or recorded as format-specific raw metadata.

## Current Code Gaps Observed

Files inspected:

- `mine/src/flux_mine/plc/models.py`
- `mine/src/flux_mine/plc/l5x.py`
- `mine/src/flux_mine/plc/l5k.py`
- `web/Flux/src/flux/mine/models.py`
- `web/Flux/src/flux/mine/services.py`
- `web/Flux/src/flux/build/models.py`
- `web/Flux/src/flux/build/services.py`
- `build/src/flux_build/targets/rockwell.py`
- `deep/src/flux_deep/hello_world.py`
- `docs/deep-openplc.md`
- `docs/Master Design.md`

Architectural gaps:

- Mine currently persists controllers, data types, members, and tags, but not tasks, routines, rungs, or instruction references.
- The L5X parser currently reads program tags but does not parse routine/rung/task content.
- The L5K parser currently ignores routine bodies and task scheduling for this sample.
- `PlcProgram` currently has tags and raw metadata only; it lacks main routine, routines, and scheduled-task relationships.
- Flux.build currently builds Ignition provider JSON and HMI symbolic map artifacts, not L5X/L5K reconstruction artifacts.
- Deep currently has a separate generated hello_world workspace using `CycleCount`, `CycleTimer`, `DisplayText`, `HelloText`, and `WorldText`; it is not generated from the new mined sample and does not match the new program-scope tag model.

These are expected gaps, not failures. The sample is exactly the right size to close them safely.

## Safety and Performance Constraints

- Put explicit import limits around PLC source parsing too, not only FactoryTalk ZIP imports.
- Avoid hidden unbounded parse behavior. Large L5X files can be huge; consider `iterparse` or staged parsing once real exports grow.
- Bulk-create persisted rows for tags/rungs/references; do not create per-reference hot loops for large projects.
- Do not swallow parser errors. Persist diagnostics and fail loudly when canonical rebuild would be unsafe.
- Keep grammar support bounded and named. “RLL subset v1” is safer than pretending to support all Logix instructions.
- For Deep.plc, every functional test needs a finite scan/time bound and deterministic termination.

## Recommended Build Phases

1. **Fixture lock**
   - Add tests around `logix_samples/hello_world.L5X` and `.L5K`.
   - Assert counts: one controller, one program, one routine, five rungs, one task, six program tags, zero controller tags.

2. **Canonical PLC model extension**
   - Extend pure Python `flux_mine.plc` dataclasses for task, routine, rung, and tag data payloads.
   - Parse the L5X sample fully first.
   - Parse the L5K sample into the same canonical model second.

3. **Mine persistence extension**
   - Add additive Mine tables for programs, tasks, routines, rungs, and instruction/tag references.
   - Make program-scope tags FK to program while keeping compatibility scope text during migration.

4. **Build L5X serializer**
   - Build generated L5X from the canonical model.
   - Parse generated L5X back through Mine and compare canonical model equality.

5. **Build L5K serializer**
   - Add generated L5K once L5X parity is stable.
   - Compare parsed L5K and parsed L5X canonical models.

6. **Deep.plc functional subset**
   - Implement either a tiny RLL interpreter or a Logix-to-ST translator for the hello_world subset.
   - Assert bounded behavior: after the hello timer completes, `hello_world` becomes `hello`; after the world timer completes, it becomes `world`; latch/timer state changes are deterministic.

## Open Questions

- Should Flux.store original PLC source bytes in the database/object store for exact replay, or is source path + hash enough for now?
- Should the first serializer target preserve Rockwell export metadata such as dates/DataExchangeId, or intentionally generate new metadata?
- Should program-scope tags be migrated immediately to a `program_id` FK, or introduced as nullable transition fields beside the existing text scope?
- Is Deep.plc’s first runtime target a small internal RLL interpreter or OpenPLC ST generation?
- Should `.ACD` be explicitly marked unsupported unless an external Rockwell-supported export step produces L5X/L5K?

## Mine Schema Migration Strategy

Date: 2026-05-25

### Intent

Before adding the richer PLC source graph, move current Mine-owned data stores out of `public` into a dedicated PostgreSQL schema named `mine`.

This is the right order. Schema ownership is a foundation decision; if we add `program`, `task`, `routine`, `rung`, and reference tables first, we create more public tables to move and more places for naming drift.

### Target boundary

`Flux.mine` should own all source-recovery facts under the `mine` schema:

- PLC source facts from L5X/L5K and future supported PLC exports.
- HMI source facts from FactoryTalk and other HMI sources.
- Import-run provenance, parser diagnostics, source hashes, and raw source metadata.

It should not own generated artifacts (`Flux.build`), runtime/emulation state (`Deep.plc`), current-state tags (`Flux.spot`/`Flux.plane`), or Ignition acquisition/runtime observations (`Flux.bridge`/`Flux.serve`/`Flux.opt`).

### Current tables to move

Current Mine tables are Django default public tables. Move them as a cluster; do not split HMI and PLC into separate schemas.

| Current public table | Target table | Notes |
| --- | --- | --- |
| `public.mine_minerun` | `mine.run` | Import/provenance root. |
| `public.mine_plccontrollerfact` | `mine.plc_controller` | Current PLC controller fact. |
| `public.mine_plcdatatypefact` | `mine.plc_data_type` | User-defined/AOI type facts. |
| `public.mine_plcmemberfact` | `mine.plc_member` | Data type member facts. |
| `public.mine_plctagfact` | `mine.plc_tag` | Current scoped PLC tag facts. |
| `public.mine_hmiscreenfact` | `mine.hmi_screen` | HMI display/screen facts. |
| `public.mine_hmicomponentfact` | `mine.hmi_component` | HMI component tree facts. |
| `public.mine_hmitagreferencefact` | `mine.hmi_tag_reference` | HMI symbolic tag references. |
| `public.mine_hmiparameterfilefact` | `mine.hmi_parameter_file` | FactoryTalk parameter files. |
| `public.mine_hmiparameterfact` | `mine.hmi_parameter` | Parameter key/value rows. |
| `public.mine_hmicomponentactionfact` | `mine.hmi_component_action` | Component action facts. |
| `public.mine_hmicomponentparameterfact` | `mine.hmi_component_parameter` | Component parameter facts. |
| `public.mine_hmicomponentstatefact` | `mine.hmi_component_state` | Multi-state/visual state facts. |
| `public.mine_hmiglobalobjectlinkfact` | `mine.hmi_global_object_link` | Global object links. |
| `public.mine_hmivbalinkfact` | `mine.hmi_vba_link` | VBA linkage facts. |

Python model names can remain for now. The table move should be a physical schema/table-name migration, not a broad class rename.

### Migration pattern

Use the same general pattern as the existing schema migrations in Cell/Sim, but tighten the postconditions:

1. Add explicit `Meta.db_table` values to every active Mine model, for example:
   - `MineRun.Meta.db_table = '"mine"."run"'`
   - `PlcTagFact.Meta.db_table = '"mine"."plc_tag"'`
   - `HmiComponentFact.Meta.db_table = '"mine"."hmi_component"'`
2. Add a manual Mine migration, likely `mine.0003_mine_schema_tables`, using `migrations.SeparateDatabaseAndState`.
3. Database operations:
   - `CREATE SCHEMA IF NOT EXISTS "mine";`
   - `ALTER TABLE "public"."mine_minerun" SET SCHEMA "mine";`
   - `ALTER TABLE "mine"."mine_minerun" RENAME TO "run";`
   - repeat for every current Mine table.
4. State operations:
   - `migrations.AlterModelTable(name="minerun", table='"mine"."run"')`
   - repeat for every current Mine model.
5. Add a small postcondition check, preferably `RunPython`, that verifies every target `to_regclass('mine.<table>')` exists and no expected old `public.mine_*` table remains.

Do not let a naive autogenerated `AlterModelTable` migration be the only migration. We want a deliberate `SET SCHEMA` + `RENAME`, not a copy/drop or ambiguous rename.

### Reverse migration

Reverse SQL should rename each table back to the old Django default name and set schema back to public. Example shape:

```sql
ALTER TABLE "mine"."run" RENAME TO "mine_minerun";
ALTER TABLE "mine"."mine_minerun" SET SCHEMA "public";
```

Reverse in the opposite order of the forward table list. Cross-schema FKs should remain valid because PostgreSQL constraints reference relation OIDs, but the reverse path still needs verification.

### Cross-app dependencies

Known non-Mine app relationships:

- `Flux.build`:
  - `BuildRun.mine_run` protects `MineRun`.
  - `HmiMapSelection` references `MineRun`, `HmiScreenFact`, and `HmiComponentFact`.
- `Flux.cell`:
  - `Source`/`Visual` reference `MineRun`, `HmiScreenFact`, and `HmiComponentFact`.
- Dashboard/build views read Mine counts and Mine rows through ORM.

The migration should not require Build/Cell table moves. Their FK constraints should continue to point to the moved Mine table OIDs. The Django state for the target models must be correct before adding new cross-domain tables.

### Safety checks

Before migration, Build should record read-only counts for all current Mine tables.

After migration, verify:

- all target tables exist under `mine`
- no expected `public.mine_*` tables remain
- row counts match before/after
- cross-app FK constraints still resolve to `mine.*` tables
- `uv run python manage.py check`
- `uv run python manage.py makemigrations --check --dry-run`
- focused tests: `flux.mine`, `flux.build`, `flux.cell`, and dashboard page/load tests

Suggested read-only evidence queries:

```sql
SELECT schemaname, tablename
FROM pg_catalog.pg_tables
WHERE schemaname = 'mine' OR tablename LIKE 'mine\_%' ESCAPE '\\'
ORDER BY schemaname, tablename;

SELECT conrelid::regclass AS source_table,
       confrelid::regclass AS target_table,
       conname
FROM pg_catalog.pg_constraint
WHERE contype = 'f'
  AND (conrelid::regclass::text LIKE 'mine.%'
       OR confrelid::regclass::text LIKE 'mine.%')
ORDER BY source_table::text, target_table::text, conname;
```

### What not to do

- Do not add the new PLC program/routine/rung tables before the schema move unless the move gets blocked.
- Do not rename Python model classes in the same migration. Table movement and class/API naming are separate risk surfaces.
- Do not move Build artifacts, HMI map selections, Cell sources, or Deep runtime rows into the Mine schema just because they reference Mine.
- Do not store runtime PLC/emulation state in Mine. Mine facts are source evidence, not runtime truth.
- Do not rely on `IF EXISTS` alone to hide missing tables; if `IF EXISTS` is used for compatibility with existing patterns, add explicit postcondition checks so migration typos fail loudly.

### Next schema after the move

Once current Mine tables live under `mine`, add richer PLC tables directly in that schema:

- `mine.plc_program`
- `mine.plc_task`
- `mine.plc_scheduled_program`
- `mine.plc_routine`
- `mine.plc_rung`
- `mine.plc_instruction`
- `mine.plc_tag_reference`
- optional `mine.source_artifact` and `mine.diagnostic` if source bytes/diagnostics need first-class storage beyond `MineRun.summary`/`error`.

This keeps the future Logix model clean from the first migration.

## Mine Schema Migration Implementation Outcome

Date: 2026-05-25

Implemented the storage boundary migration for current Mine tables.

Changed files:

- `web/Flux/src/flux/mine/models.py`
- `web/Flux/src/flux/mine/migrations/0003_mine_schema_tables.py`
- `architecture/mine/flux_mine_exploration.md`
- `architecture/core_area_files.md`
- `architecture/daily/architecture_2026-05-25/architecture_2026-05-25.md`

Implementation details:

- Added explicit `Meta.db_table` values for current Mine models.
- Added `mine.0003_mine_schema_tables` using `SeparateDatabaseAndState`.
- The migration creates schema `mine`, moves existing `public.mine_*` tables with `ALTER TABLE ... SET SCHEMA`, renames them to concise schema-owned table names, and updates Django migration state with `AlterModelTable`.
- Added a forward postcondition check that verifies all target `mine.*` tables exist and expected old `public.mine_*` tables are gone.
- Did not add PLC program/routine/rung tables.
- Did not rename Python model classes.
- Did not change parsers, serializers, or Deep.plc behavior.

Local migration evidence:

- Before migration: `public.mine_minerun=1`, `public.mine_hmiscreenfact=8`, `public.mine_hmicomponentfact=1612`, `public.mine_hmitagreferencefact=858`, `public.mine_hmicomponentactionfact=355`, `public.mine_hmicomponentparameterfact=40`, `public.mine_hmicomponentstatefact=676`, `public.mine_hmiglobalobjectlinkfact=22`; PLC, parameter, and VBA tables were 0 rows.
- After migration: `mine.run=1`, `mine.hmi_screen=8`, `mine.hmi_component=1612`, `mine.hmi_tag_reference=858`, `mine.hmi_component_action=355`, `mine.hmi_component_parameter=40`, `mine.hmi_component_state=676`, `mine.hmi_global_object_link=22`; corresponding PLC, parameter, and VBA target tables remained 0 rows.
- Catalog checks showed only target `mine.*` tables from the expected set and no expected old public Mine tables.
- Foreign key catalog evidence showed Build and Cell references now target `mine.*` relation names while preserving existing constraint names.

Verification:

- `uv run python web/Flux/manage.py makemigrations mine --check --dry-run`: passed.
- `uv run python web/Flux/manage.py makemigrations --check --dry-run`: passed.
- `uv run ruff check web/Flux/src/flux/mine/models.py web/Flux/src/flux/mine/migrations/0003_mine_schema_tables.py`: passed.
- `uv run python web/Flux/manage.py migrate mine --noinput`: applied `mine.0003_mine_schema_tables` locally.
- `uv run python web/Flux/manage.py migrate --check`: passed after local migration.
- `uv run python web/Flux/manage.py check`: passed.
- `uv run python web/Flux/manage.py test flux.mine flux.build flux.cell dashboard --noinput`: passed before local migration in a freshly rebuilt test DB, 94 tests, 4 skipped.
- A second no-keepdb rerun hit a PostgreSQL test database create/drop lifecycle issue after stale `test_flux` cleanup; retrying with `--keepdb` passed: `uv run python web/Flux/manage.py test flux.mine flux.build flux.cell dashboard --noinput --keepdb`, 94 tests, 4 skipped.

Next safe Build slice:

- Add PLC source graph tables directly under `mine.*`, beginning with program/task/routine/rung models and parser persistence for the `logix_samples/hello_world.L5X` fixture.

## PLC Source Graph Implementation Outcome

Date: 2026-05-25

Implemented the first bounded PLC source graph slice for Mine.

Changed files:

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

Implementation details:

- Added canonical PLC dataclasses for `PlcTask`, `PlcProgram.main_routine_name`, `PlcRoutine`, and `PlcRung`.
- Extended the L5X parser to recover program main routines, routines, RLL rungs, tasks, scheduled programs, and tag data payloads in `PlcTag.raw["data"]`.
- Extended the L5K parser to recover the hello_world program/routine/rung/task subset and task scheduled programs.
- Added persisted Mine graph tables under `mine.*`: `mine.plc_program`, `mine.plc_task`, `mine.plc_scheduled_program`, `mine.plc_routine`, and `mine.plc_rung`.
- Wired `persist_plc_project()` to store programs, routines, rungs, tasks, and task-program scheduling links before persisting tags.
- Added fixture-backed tests for `logix_samples/hello_world.L5X` and `logix_samples/hello_world.L5K`.
- Added Django persistence coverage for the L5X hello_world graph.

Boundaries preserved:

- No Flux.build L5X/L5K serializer was added.
- No Deep.plc runtime/emulation work was added.
- No instruction/tag-reference parser was added yet.
- Existing `PlcTagFact` still uses text `scope`; program FK for tags remains a later migration.

Verification:

- `uv run pytest mine/tests/test_l5x.py mine/tests/test_l5k.py`: passed, 5 tests.
- `uv run ruff check mine/src/flux_mine/plc/models.py mine/src/flux_mine/plc/l5x.py mine/src/flux_mine/plc/l5k.py`: passed.
- `uv run python web/Flux/manage.py makemigrations mine --check --dry-run`: passed.
- `uv run ruff check web/Flux/src/flux/mine/models.py web/Flux/src/flux/mine/services.py web/Flux/src/flux/mine/tests.py web/Flux/src/flux/mine/migrations/0004_plc_source_graph.py`: passed.
- `uv run python web/Flux/manage.py check`: passed.
- `uv run python web/Flux/manage.py migrate mine --noinput`: applied `mine.0004_plc_source_graph` locally.
- Local catalog checks showed the new graph tables exist under `mine` and contain 0 rows before importing new PLC samples into the local dev DB.
- `uv run python web/Flux/manage.py migrate --check`: passed after local migration.
- `uv run python web/Flux/manage.py makemigrations --check --dry-run`: passed.
- `uv run python web/Flux/manage.py test flux.mine flux.build flux.cell dashboard --noinput --keepdb`: passed, 95 tests, 4 skipped.

Next safe Build slice:

- Add bounded RLL instruction/tag-reference extraction for the hello_world subset: `XIO`, `XIC`, `TON`, `OTL`, `OTU`, and `COP`.
- Persist instruction/reference rows under `mine.plc_instruction` and `mine.plc_tag_reference`.
- Then start the first Flux.build L5X serializer parity loop from the persisted Mine model.

## RLL Instruction Reference Implementation Outcome

Date: 2026-05-25

Implemented bounded RLL instruction and tag-reference extraction for the hello_world subset.

Changed files:

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

Implementation details:

- Added a small RLL parser for instruction calls matching the hello_world subset: `XIO`, `XIC`, `TON`, `OTL`, `OTU`, and `COP`.
- Added canonical dataclasses for `PlcInstruction` and `PlcInstructionTagReference`.
- Rung parsing now attaches instruction objects to `PlcRung.instructions` for both L5X and L5K paths.
- Added persisted Mine tables:
  - `mine.plc_instruction`
  - `mine.plc_tag_reference`
- `persist_plc_project()` now stores instructions and tag references after tag rows exist, resolving references first against the containing program scope and then `Global`.
- Reference roles are intentionally narrow: `read`, `write`, `timer`, `source`, and `destination`.

Boundaries preserved:

- This is not a full Logix grammar.
- No Flux.build serializer was added.
- No Deep.plc execution/emulation was added.
- No tag-to-program FK migration was added yet.

Verification:

- `uv run pytest mine/tests/test_l5x.py mine/tests/test_l5k.py`: passed, 5 tests.
- `uv run ruff check mine/src/flux_mine/plc/models.py mine/src/flux_mine/plc/l5x.py mine/src/flux_mine/plc/l5k.py`: passed.
- `uv run python web/Flux/manage.py makemigrations mine --check --dry-run`: passed.
- `uv run ruff check web/Flux/src/flux/mine/models.py web/Flux/src/flux/mine/services.py web/Flux/src/flux/mine/tests.py web/Flux/src/flux/mine/migrations/0005_plc_instruction_references.py`: passed.
- `uv run python web/Flux/manage.py check`: passed.
- `uv run python web/Flux/manage.py migrate mine --noinput`: applied `mine.0005_plc_instruction_references` locally.
- Local table checks showed `mine.plc_instruction` and `mine.plc_tag_reference` exist and contain 0 rows before importing new PLC samples into the local dev DB.
- `uv run python web/Flux/manage.py migrate --check`: passed.
- `uv run python web/Flux/manage.py makemigrations --check --dry-run`: passed.
- `uv run python web/Flux/manage.py test flux.mine flux.build flux.cell dashboard --noinput`: passed on a fresh test DB, 97 tests, 4 skipped.
- A prior `--keepdb` focused run failed on unrelated stale dashboard fixture counts from a preserved test database; the fresh test DB run passed.

Next safe Build slice:

- Start the first Flux.build L5X serializer parity loop from the persisted Mine model.
- Initial parity target should serialize controller/program/task/routine/rung/tag structure for hello_world, then parse the generated L5X back through Flux.mine and compare canonical counts/references.

## Flux.build L5X Parity Implementation Outcome

Date: 2026-05-25

Implemented the first Flux.build generated L5X parity loop from persisted Mine rows.

Changed files:

- `build/src/flux_build/targets/logix_l5x.py`
- `web/Flux/src/flux/build/models.py`
- `web/Flux/src/flux/build/services.py`
- `web/Flux/src/flux/build/tests.py`
- `web/Flux/src/flux/build/management/commands/flux_build_logix_l5x.py`
- `web/Flux/src/flux/build/migrations/0003_buildrun_logix_l5x_target.py`
- `architecture/mine/flux_mine_exploration.md`
- `architecture/core_area_files.md`
- `architecture/daily/architecture_2026-05-25/architecture_2026-05-25.md`

Implementation details:

- Added `flux_build.targets.logix_l5x.build_logix_l5x()`.
- Added Build target `logix_l5x` and a management command: `flux_build_logix_l5x <mine_run_id> --output <path>`.
- Extended `plc_project_from_mine_run()` to reconstruct tasks, scheduled programs, routines, rungs, instructions, and tag references from persisted Mine rows.
- Added `build_logix_l5x_from_mine_run()` service that:
  - loads a persisted Mine PLC project,
  - serializes generated L5X,
  - parses the generated L5X back through Flux.mine's L5X parser,
  - compares canonical counts, and
  - writes a `logix_l5x` Build artifact only if parse-back counts match.
- Added a hello_world parity test that mines `logix_samples/hello_world.L5X`, builds a generated L5X, parses it back, and asserts graph/reference parity.

Current parity contract:

- Semantic/count parity, not byte-perfect source identity.
- Preserves controller, tags, program, main routine, task, scheduled program, routine, rung, instruction, and tag-reference counts for hello_world.
- Preserves L5X tag data payload text when present in Mine tag raw metadata.

Boundaries preserved:

- No L5K serializer was added.
- No Deep.plc runtime/emulation was added.
- No general Logix grammar claim was added.
- No raw-source exact replay/object storage was added.

Verification:

- `uv run ruff check build/src/flux_build/targets/logix_l5x.py web/Flux/src/flux/build/models.py web/Flux/src/flux/build/services.py web/Flux/src/flux/build/tests.py web/Flux/src/flux/build/management/commands/flux_build_logix_l5x.py web/Flux/src/flux/build/migrations/0003_buildrun_logix_l5x_target.py`: passed.
- `uv run python web/Flux/manage.py makemigrations build --check --dry-run`: passed.
- `uv run python web/Flux/manage.py test flux.build --noinput`: passed, 8 tests, 1 skipped.
- `uv run python web/Flux/manage.py migrate build --noinput`: applied `build.0003_buildrun_logix_l5x_target` locally.
- `uv run python web/Flux/manage.py showmigrations build`: all Build migrations applied through `0003`.
- `uv run python web/Flux/manage.py migrate --check`: passed.
- `uv run python web/Flux/manage.py makemigrations --check --dry-run`: passed.
- `uv run python web/Flux/manage.py check`: passed.
- `uv run python web/Flux/manage.py test flux.mine flux.build flux.cell dashboard --noinput`: passed, 98 tests, 4 skipped.
- `uv run pytest build/tests`: passed, 4 tests.

Next safe Build slice:

- Add L5K serializer parity for hello_world or move to Deep.plc functional testing now that Mine -> Build -> Mine L5X parity is proven.
- If choosing Deep.plc next, keep the runtime subset bound to the persisted instruction/reference model and finite scan/time assertions.

## Flux.build L5K Parity Implementation Outcome

Date: 2026-05-25

Implemented generated L5K parity from the same persisted Mine model used by the L5X serializer.

Changed files:

- `build/src/flux_build/targets/logix_l5k.py`
- `web/Flux/src/flux/build/models.py`
- `web/Flux/src/flux/build/services.py`
- `web/Flux/src/flux/build/tests.py`
- `web/Flux/src/flux/build/management/commands/flux_build_logix_l5k.py`
- `web/Flux/src/flux/build/migrations/0004_buildrun_logix_l5k_target.py`
- `architecture/mine/flux_mine_exploration.md`
- `architecture/core_area_files.md`
- `architecture/daily/architecture_2026-05-25/architecture_2026-05-25.md`

Implementation details:

- Added `flux_build.targets.logix_l5k.build_logix_l5k()`.
- Added Build target `logix_l5k` and management command: `flux_build_logix_l5k <mine_run_id> --output <path>`.
- Added `build_logix_l5k_from_mine_run()` service that serializes persisted Mine PLC facts to generated L5K, parses that L5K back through Flux.mine, compares canonical counts, and records a `logix_l5k` Build artifact only if parity holds.
- Added hello_world L5K parity coverage from an L5X-mined source, proving that Mine's canonical model can emit both generated L5X and generated L5K forms.

Current parity contract:

- Semantic/count parity, not byte-perfect Rockwell export parity.
- Verifies controller, tags, program, task, scheduled program, routine, rung, instruction, and tag-reference counts for hello_world.
- Includes L5K tag initializers when L5K payload text is available in Mine tag raw data.

Boundaries preserved:

- No Deep.plc runtime/emulation was added.
- No full Logix grammar or complex L5K formatting support was claimed.
- No raw-source exact replay/object storage was added.

Verification:

- `uv run ruff check build/src/flux_build/targets/logix_l5k.py web/Flux/src/flux/build/models.py web/Flux/src/flux/build/services.py web/Flux/src/flux/build/tests.py web/Flux/src/flux/build/management/commands/flux_build_logix_l5k.py web/Flux/src/flux/build/migrations/0004_buildrun_logix_l5k_target.py`: passed.
- `uv run python web/Flux/manage.py makemigrations build --check --dry-run`: passed.
- `uv run python web/Flux/manage.py test flux.build --noinput`: passed, 9 tests, 1 skipped.
- `uv run python web/Flux/manage.py migrate build --noinput`: applied `build.0004_buildrun_logix_l5k_target` locally.
- `uv run python web/Flux/manage.py showmigrations build`: all Build migrations applied through `0004`.
- `uv run python web/Flux/manage.py migrate --check`: passed.
- `uv run python web/Flux/manage.py makemigrations --check --dry-run`: passed.
- `uv run python web/Flux/manage.py check`: passed.
- `uv run python web/Flux/manage.py test flux.mine flux.build flux.cell dashboard --noinput`: passed, 99 tests, 4 skipped.
- `uv run pytest build/tests`: passed, 4 tests.

Next safe Build slice:

- Move to Deep.plc functional testing using Mine's persisted instruction/reference model.
- Keep the first runtime proof bounded to hello_world with finite scan/time assertions for `XIO`, `XIC`, `TON`, `OTL`, `OTU`, and `COP`.

## Deep.plc Bounded Runtime Implementation Outcome

Date: 2026-05-25

Implemented the first bounded Deep.plc functional runtime proof using the hello_world instruction subset.

Changed files:

- `deep/src/flux_deep/rll.py`
- `deep/tests/test_hello_world.py`
- `deep/README.md`
- `docs/deep-openplc.md`
- `web/Flux/src/flux/mine/test_deep_runtime.py`
- `pyproject.toml`
- `uv.lock`
- `architecture/mine/flux_mine_exploration.md`
- `architecture/core_area_files.md`
- `architecture/daily/architecture_2026-05-25/architecture_2026-05-25.md`

Implementation details:

- Added `flux_deep.rll`, a small deterministic scan executor for the hello_world RLL subset.
- Supported instructions are intentionally limited to `XIO`, `XIC`, `TON`, `OTL`, `OTU`, and `COP`.
- Added `TimerValue`, `RllState`, `RllInstruction`, `RllRung`, and `RllProgram` primitives.
- Added tag initial-state extraction for persisted Mine tag raw payloads for `BOOL`, `STRING`, integer types, and `TIMER`.
- Added branch splitting that respects commas inside instruction operands, so the hello_world branch rung executes as two networks.
- Added a Django integration test that mines `logix_samples/hello_world.L5X`, builds a Deep runtime program from persisted `PlcRungFact`/`PlcInstructionFact` rows, initializes state from persisted `PlcTagFact` rows, and runs finite 100 ms scans.

Functional proof:

- After the first bounded scan, `hello_world` contains `hello`.
- After the hello timer completes, `world_latch` is true and `hello_world` contains `world`.
- After the world timer completes, `world_latch` is false and `hello_world` returns to `hello`.

Boundaries preserved:

- This is not OpenPLC integration.
- This is not a full Logix runtime.
- No Django runtime service owns PLC execution; the Django side is a focused integration test adapter only.
- The root project now depends on editable `flux-deep` so tests can prove Mine-persisted rows execute through the isolated Deep package.

Verification:

- `uv lock`: updated root lockfile and added `flux-deep v0.1.0`.
- `uv run ruff check deep/src/flux_deep/rll.py deep/tests/test_hello_world.py web/Flux/src/flux/mine/test_deep_runtime.py pyproject.toml`: passed.
- `uv run --project deep pytest deep/tests`: passed, 8 tests.
- `uv run python web/Flux/manage.py test flux.mine.test_deep_runtime --noinput`: passed, 1 test.
- `uv run python web/Flux/manage.py check`: passed.
- `uv run python web/Flux/manage.py test flux.mine flux.build flux.cell dashboard --noinput`: passed, 100 tests, 4 skipped.
- `uv run pytest build/tests`: passed, 4 tests.
- `uv run python web/Flux/manage.py makemigrations --check --dry-run`: passed.
- `uv run python web/Flux/manage.py migrate --check`: passed.

Next safe Build slice:

- Decide whether to grow Deep toward an OpenPLC ST translator for the same persisted RLL subset or strengthen Mine/Build canonical comparisons beyond counts.

## Direct OpenPLC Compiler Integration Outcome

Date: 2026-05-25

Implemented and validated a direct, non-Docker OpenPLC compiler integration path.

Changed files:

- `deep/src/flux_deep/openplc.py`
- `deep/tests/test_openplc_integration.py`
- `deep/README.md`
- `docs/deep-openplc.md`
- `architecture/mine/flux_mine_exploration.md`
- `architecture/core_area_files.md`
- `architecture/daily/architecture_2026-05-25/architecture_2026-05-25.md`

Direct setup performed locally:

- Cloned OpenPLC v3 to `/tmp/opencode/OpenPLC_v3`.
- Built the MatIEC compiler directly under `/tmp/opencode/OpenPLC_v3/utils/matiec_src` with `autoreconf -i`, `./configure`, and `make -j$(nproc)`.
- Did not use Docker.
- Did not install or start an OpenPLC system service.
- Did not use `sudo`.

Implementation details:

- Added `flux_deep.openplc.OpenPlcV3Toolchain`.
- The adapter is gated by `FLUX_DEEP_OPENPLC_ROOT`.
- It validates OpenPLC v3 MatIEC availability by checking for `iec2c` and `webserver/lib/ieclib.txt`.
- It compiles Structured Text in an isolated temporary/output directory by linking OpenPLC's IEC library folder and invoking `iec2c -f -l -p -r -R -a`.
- It returns generated OpenPLC C artifacts such as `POUS.c`, `POUS.h`, `Config0.c`, `Config0.h`, and `Res0.c`.

Validation result:

- `deep/examples/hello_world/openplc/hello_world.st` compiles successfully through OpenPLC v3 MatIEC.
- Generated `POUS.c` contains OpenPLC/MatIEC generated symbol `HELLO_WORLD_body__`.
- Ungated test behavior skips cleanly when `FLUX_DEEP_OPENPLC_ROOT` is not set.

Verification:

- `uv run ruff check deep/src/flux_deep/openplc.py deep/tests/test_openplc_integration.py deep/README.md docs/deep-openplc.md`: passed.
- `uv run --project deep pytest deep/tests/test_openplc_integration.py`: skipped without `FLUX_DEEP_OPENPLC_ROOT`, as intended.
- `FLUX_DEEP_OPENPLC_ROOT=/tmp/opencode/OpenPLC_v3 uv run --project deep pytest deep/tests/test_openplc_integration.py`: passed, 1 test.
- `uv run --project deep pytest deep/tests`: passed without env, 8 passed, 1 skipped.
- `FLUX_DEEP_OPENPLC_ROOT=/tmp/opencode/OpenPLC_v3 uv run --project deep pytest deep/tests`: passed, 9 tests.
- `uv run python web/Flux/manage.py check`: passed.

Remaining gap:

- This validates against the OpenPLC compiler/toolchain, not a running OpenPLC PLC runtime loop.
- Full runtime validation will require either OpenPLC v3 service setup with native dependencies or an OpenPLC v4 runtime/editor-compatible upload package. That should be a separate adapter because service supervision, auth, ports, and real-time privileges are different responsibilities than ST compilation.

Next safe Build slice:

- Generate OpenPLC Structured Text from the persisted Mine instruction model, then validate that generated ST through this direct OpenPLC compiler adapter.

## OpenPLC Harness Variable Inspection Outcome

Date: 2026-05-25

Extended the direct OpenPLC validation from compile-only to direct generated-variable inspection.

Changed files:

- `deep/src/flux_deep/hello_world.py`
- `deep/src/flux_deep/openplc.py`
- `deep/tests/test_hello_world.py`
- `deep/tests/test_openplc_integration.py`
- `deep/examples/hello_world/openplc/hello_world.st`
- `deep/examples/hello_world/manifest.json`
- `deep/examples/hello_world/README.md`
- `deep/README.md`
- `docs/deep-openplc.md`
- `architecture/mine/flux_mine_exploration.md`
- `architecture/core_area_files.md`
- `architecture/daily/architecture_2026-05-25/architecture_2026-05-25.md`

Implementation details:

- Updated the Deep OpenPLC ST target to model the mined sample more directly:
  - program `MainProgram`
  - string variables `hello`, `world`, and inspectable `hello_world`
  - BOOL `world_latch`
  - timers `hello_TON` and `world_TON`
- Added `OpenPlcV3Toolchain.compile_and_run_harness()`.
- The harness compiles OpenPLC MatIEC generated `Config0.c` and `Res0.c` with a small C++ test program.
- The harness defines `__CURRENT_TIME`, advances scans in 100 ms steps, and directly reads `RES0__MAININSTANCE.HELLO_WORLD` and `RES0__MAININSTANCE.WORLD_LATCH` from the generated C program state.
- Added harmless TCP helper stubs because OpenPLC's standard library references optional communication blocks even when the tested ST program does not use them.

Validation result:

- tick 0: `world_latch = false`, `hello_world = hello`
- tick 10: `world_latch = true`, `hello_world = world`
- tick 20: `world_latch = false`, `hello_world = hello`

This is now the requested validation test: OpenPLC accepts the ST, generates C, the generated C executes, and the program variable cycles between `hello` and `world`.

Boundaries preserved:

- This still does not start the OpenPLC system service.
- It validates OpenPLC-generated execution artifacts directly in-process.
- It keeps runtime-service supervision, REST upload/auth, and real-time scheduling for a separate adapter.

Verification:

- `uv run ruff check deep/src/flux_deep/openplc.py deep/src/flux_deep/hello_world.py deep/tests/test_openplc_integration.py deep/tests/test_hello_world.py deep/examples/hello_world/manifest.json deep/README.md docs/deep-openplc.md`: passed.
- `FLUX_DEEP_OPENPLC_ROOT=/tmp/opencode/OpenPLC_v3 uv run --project deep pytest deep/tests/test_openplc_integration.py`: passed, 2 tests.
- `uv run --project deep pytest deep/tests`: passed without env, 8 passed, 2 skipped.
- `FLUX_DEEP_OPENPLC_ROOT=/tmp/opencode/OpenPLC_v3 uv run --project deep pytest deep/tests`: passed, 10 tests.
- `uv run python web/Flux/manage.py check`: passed.
- `uv run python web/Flux/manage.py test flux.mine.test_deep_runtime --noinput`: passed, 1 test.
- `uv run python web/Flux/manage.py makemigrations --check --dry-run`: passed.

Next safe Build slice:

- Generate this OpenPLC ST target from persisted Mine instruction rows instead of maintaining it as a checked-in hand-written ST artifact.
