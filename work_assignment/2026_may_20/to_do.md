# 2026-05-20 Work Assignment

## Architecture Thesis

Flux should organize around Schelling point primitives:

- Live card: current-state display
- Trace trend: historical/time display
- Simulated tag: testable signal
- Simulated device: testable source
- Cell: bounded process object, incoming `Flux.cell`
  - `cell.group`: broad process family, formerly equipment_type/process_type
  - `cell.kind`: narrower process classification, formerly subtype/type
- Cell interlock: action/permissive rule, incoming `Flux.lock`

Architectural rule:

```text
Tags are not process objects.
Cards are not process objects.
Trends are not process objects.
Cells bind them together.
```

## Confirmed Decisions

- `Flux.plane` is a future namespace for the data-plane layer.
- Bootstrap-Bob is a verification artifact for all installations, not only a local demo.
- All operator demand events reset sampling to hot:
  - page open
  - scope/card selection
  - trace source selection
  - zoom/pan/staged chart movement
  - manual refresh
  - stale recovery

## System Shape

The near-term mission is to build a repeatable SCADA migration and verification loop:

```text
Bootstrap-Bob
-> simulated Ignition source
-> Flux sampling
-> Flux.plane/runtime storage
-> Flux.live
-> Flux.trace
-> production-derived Flux.sim profile
-> cleanup verification
```

Boundary intent:

- `Flux.live` renders current-state cards from cached data.
- `Flux.trace` renders historical/staged trends from cached/history data.
- `Flux.opt` decides what should be sampled, how often, and why.
- `Flux.serve` runs and monitors the services that do the work.
- `Flux.plane` will own/query-serve sampled data as the data-plane namespace matures.
- `Flux.sim` creates testable devices/tags and production-derived simulation behavior.
- `Flux.test` orchestrates repeatable verification across all of the above.

## Shared Naming

Use this naming in new interfaces:

- Use `scope` for a configured live/trace page group.
- Use `group` for broad process family.
- Use `kind` for narrower process classification.
- Avoid new public `equipment_type`, `process_type`, `subtype`, or `cell_type` language.

Preferred route language:

```text
/live/{scope}/
/live/{scope}/cards/?group={cell_group}
/trace/{scope}/
/trace/{scope}/embed/
/trace/{scope}/payload/
```

## Bootstrap-Bob

Bootstrap-Bob is the canonical all-install verification artifact.

Responsibilities:

- Provide a known simulated device connected through the default `Ignition OPC-UA Server`.
- Provide known bootstrap tags modeled after the `/live/pad-overview/` tag shape.
- Generate 30 days of predictable history.
- Support online/offline transitions for stale/recovery tests.
- Remain installed as a verification fixture after test cleanup.
- Provide known value patterns for cross-checking live, trace, and sim-profile behavior.

Bootstrap-Bob should be persistent. Tests may create temporary live/trace/sim configurations around it, but cleanup should not delete Bootstrap-Bob itself unless explicitly requested.

## CSV Interfaces

Start with CSV. Do not add Excel dependencies until CSV proves insufficient.

Canonical tag references should use full Ignition tag paths:

```text
[default]Path/to/tag
```

### Live CSV

Initial shape:

| Live Scope | ID (optional) | Name | group | kind | Tag 1 | Tag {n} | display order (optional) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| wells | 1 | Tank_01 | Tank | Oil Tank | [default]Path/to/tag/atomic_tag_1 | [default]Path/to/tag/atomic_tag_n | 4 |

First implementation may use runtime tag display names for point labels. Add explicit per-tag label columns only when needed.

### Trace CSV

Initial shape:

| Chart Scope | ID (optional) | Name | Tag 1 | Tag {n} | display order (optional) |
| --- | --- | --- | --- | --- | --- |
| wells | 1 | AL1-16-29-107 | [default]Path/to/tag/atomic_tag_1 | [default]Path/to/tag/atomic_tag_n | 4 |

Ordering options:

```text
order_by = display_order | name | id
```

## Sampling Lifecycle

Live/operator demand should move affected tags/scopes to hot sampling.

Policy:

```text
hot: first 2 minutes after demand
warm: 2 to 5 minutes after demand
cold: after 5 minutes without demand
```

Demand reset events:

- page open
- scope/card selection
- trace source selection
- zoom in/out
- staged left/right chart movement
- manual refresh
- stale recovery

Historical sampling rules:

- When a tag is ingested through live, trace, or sim config, read tag configuration through `fx.tag.getConfiguration`.
- If Ignition history exists, prefer historian reads over live tag reads for history recovery.
- If history mode is on-change with no minimum, enforce Flux hot minimum sampling for local recovery.
- If Ignition minimum sample time exceeds Flux hot sampling rate, log/report that instead of fighting it.
- If no historical data is available, use hot interval tag reads to recover local history.

History fields likely needed from `getConfiguration`:

```text
historyEnabled
historyProvider
historySampleMode
historySampleRate
historySampleRateUnits
historyMinTimeBetweenSamples
historyMinTimeUnits
historicalDeadband
historicalDeadbandMode
historyMaxAge
historyMaxAgeUnits
```

## Trace Data View

`/trace/wells/` has the template form we want.

Trace should move toward staged views rather than live-scrolling views.

Navigation requirements:

- dropdown source selector
- previous/next source buttons
- zoom in/zoom out buttons
- left/right staged chart movement
- stable source IDs, not only index-based `set=1`

Embedding requirements:

- Provide an embeddable mirror at `/trace/{scope}/embed/` or equivalent.
- Embedded views should preserve Flux-driven chart behavior.
- Outer pages should be able to trigger:
  - next
  - previous
  - select source
  - set window
  - zoom
  - staged movement

Window movement rules:

```text
1 hour trend  -> move 5 minutes
1 day trend   -> move 1 hour
1 week trend  -> move 1 day
1 month trend -> move 2 days
1 year trend  -> move 1 month
```

Zoom rule:

- Zoom in should reduce the visible window by one increment total.
- Prefer half from right and half from left.
- If the right edge is pinned at present, decrement fully from the left.

Compression requirements:

- Target about 1440 display points per pen based on trend scale.
- Display compression information below the chart.
- If displayed points are sub-1440 on raw points, show `No compression`.
- Do not claim raw point count unless the query actually measured raw point count.
- Prefer disclosure wording like `Showing one point every N minutes`.

## Workstreams

### Agent 1: Bootstrap-Bob And Flux.test Contract

Mission: define the acceptance spine before feature work spreads.

Deliverables:

- Bootstrap-Bob fixture contract.
- Test CSV fixtures for live and trace.
- Suite manifest format.
- Cleanup boundaries.
- Expected assertions for live, trace, sampling, sim, stale, recovery, and cleanup.

First suites:

```text
bootstrap-bob
live-csv
trace-csv
sampling
sim-profile
closed-loop
```

Each suite should declare:

```text
name
command
cwd
required env
timeout
external services touched
cleanup expectations
destructive scope
```

The first `Flux.test` implementation should be report-only. The test agent should run or describe suites and return structured results; it should not auto-fix product code.

### Agent 2: Flux.live Configurable Card Scopes

Mission: make `/live/pad-overview/` the pattern for many CSV-defined live pages.

Current seam:

- Existing page has the right look and feel.
- Existing selector returns reusable `LiveCard` / `LivePoint` shapes.
- Current hard-coded assumptions are `FluxLiveDemo`, `Well/Meter/Tank`, and `asset_name` parsing.

Deliverables:

- Conceptual model/interface for `LiveScope`, `LiveCardDefinition`, and `LiveCardPointDefinition`.
- CSV import contract.
- Future route shape `/live/{scope}/`.
- Card filtering by `group` and eventually `kind`.
- Keep `/live/pad-overview/` working.
- Ensure live updating continues through cached runtime/latest values.
- Connect live card demand to hot/warm/cold sampling policy.

### Agent 3: Flux.trace Configurable Scope And UX

Mission: make `/trace/wells/` into a reusable trace-scope pattern.

Current seam:

- `TraceProfile` and `TraceSignal` already exist and are strong.
- `/trace/wells/` has the desired template feel.
- Nav-well logic is currently index-based and provider-specific.

Deliverables:

- Generic trace scope resolver.
- CSV import contract for trace scopes.
- Route shape `/trace/{scope}/`.
- Dropdown source selector.
- Previous/next source controls.
- Zoom in/out controls.
- Left/right staged chart movement.
- Stable source IDs.
- Compression disclosure.

### Agent 4: Flux.trace Embed And External Control

Mission: make trace views embeddable while Flux still owns chart state changes.

Deliverables:

- `/trace/{scope}/embed/` or equivalent `?embed=1` behavior.
- Minimal embedded chrome.
- External control API or event contract for:
  - next
  - previous
  - select source
  - set window
  - zoom
  - staged movement
- Tests showing embedded views still load chart payloads and respond to source/window changes.

### Agent 5: Flux.opt Sampling Architecture

Mission: define hot/warm/cold collection rules and history-aware behavior.

Current seam:

- `flux.opt.RefreshLane` exists but currently uses `hot/warm/cool/lazy`.
- `RuntimeTag`, `TagSchedule`, and `RuntimeSchedulerConfig` already exist.
- `dashboard.services.refresh_runtime_tags()` already does batch `read_blocking`.
- `fluxy` has `get_configuration`, but output likely needs more history config fields.

Deliverables:

- Normalize lanes to `hot`, `warm`, and `cold`.
- Define lane timing and demand reset behavior.
- Define history-aware behavior.
- Expand `getConfiguration` output to include history config fields.
- Decide how `Flux.opt` writes work into `Flux.plane`/runtime storage without owning presentation concerns.

### Agent 6: Flux.serve Sampling Worker

Mission: create the service that samples Ignition into Flux runtime/data-plane storage.

Current seam:

- `serve.worker.run_worker_heartbeat()` is the clean wrapper.
- `flux_worker` already accepts jobs.
- No dedicated sampling service exists yet.

Deliverables:

- Dedicated worker command concept: `flux_sampling_worker`.
- First hot-lane pass:
  - claim due tags
  - batch by provider/lane
  - `read_blocking` in bulk
  - update `LatestTagValue`
  - append `TagSample`
  - advance next due time
  - record heartbeat/errors
- Later pass:
  - historian-aware read branch
  - cold bucket balancing
  - QuestDB hot path if Django DB gets too heavy
- Move reusable sampling logic out of `dashboard.services`; dashboard should not own core sampling.
- Build in potential for multi-process sampling when multiple historian items or high tag counts require it.

### Agent 7: Flux.sim Bootstrap And Production Profiles

Mission: make `Flux.sim` able to bootstrap verification devices and simulate from production data.

Current seam:

- `flux_sim.runtime` has deterministic simulated values.
- `SimDeviceTag.mode_config` and `FieldTag.config` can carry JSON strategy config.
- `flux.sim.live_extract` already extracts config/history and can become a source for fitting.

Deliverables:

- Proper create/delete functions for sim devices and tags.
- Bootstrap-Bob installation/update path.
- Online/offline transition support.
- Value-profile abstraction:
  - sine fallback
  - polynomial profile
  - historical replay/profile later
- Default production-derived behavior:
  - sample last N days if history exists
  - fit 2nd-order polynomial by default
  - if no history, sine wave at +/- 15%
- Keep fitting pure and unit-testable.
- Avoid live polling loops.

Suggested internal shape:

```text
production_profile.py
  collect points
  fit profile
  serialize config
  evaluate profile at time/sample index
```

### Agent 8: Flux.cell And Flux.lock Watcher

Mission: track when `Flux.cell` and `Flux.lock` become justified, but do not implement full models yet.

Deliverables:

- Watch for repeated `group`/`kind` shape across live, trace, and sim.
- Watch for interlock/permissive concepts emerging from stale/recovery/offline testing.
- Report when a real `Flux.cell` model becomes the simplest architecture.

## End-To-End Acceptance Scenario

### Inputs

- Live CSV mirroring the current `/live/pad-overview/` model.
- Trace CSV derived from the live CSV and expanded with nine additional test items appended with test numbers.
- Bootstrap-Bob device connected to the default `Ignition OPC-UA Server`.
- Bootstrap tags modeled after `/live/pad-overview/` tags.
- 30 days of generated Bootstrap-Bob history.

### Process

1. Use live CSV to build `/live/test-pad-overview/`.
2. Use trace CSV to build `/trace/test/`.
3. Verify data is updating in:
   - Bootstrap-Bob tags
   - `Flux.live`
   - `Flux.live` statuses
   - `Flux.trace` historical payloads
   - `Flux.trace` live increment updates
4. Perform trace interaction checks:
   - zoom
   - staged chart back/forward
   - next/previous source cycling
   - dropdown source selection
5. Build sim OPC server/config from Bootstrap-Bob and tags.
6. Fit production-derived polynomial/sine profiles.
7. Use validated sim tags to feed `/live/test-pad-overview/`.
8. Cross-check expected values.
9. Take device offline.
10. Verify stale/bad status in:
    - Ignition
    - `Flux.live`
11. Put device back online.
12. Verify recovery in:
    - Ignition
    - `Flux.live`
13. Delete temporary sim tags/device created by the test.
14. Delete temporary `Flux.live` configuration.
15. Delete temporary `Flux.trace` configuration.
16. Leave Bootstrap-Bob installed.
17. Verify temporary artifacts are gone.

## Execution Order

1. Bootstrap-Bob and `Flux.test` acceptance contract.
2. `Flux.sim` Bootstrap-Bob create/delete/history generation.
3. `Flux.live` CSV-defined `test-pad-overview`.
4. `Flux.trace` CSV-defined `trace/test`.
5. `Flux.opt` lane/history discovery design.
6. `Flux.serve` sampling worker first hot-lane pass.
7. `Flux.sim` production profile unit layer.
8. Full close-loop test.
9. `Flux.cell` and `Flux.lock` after live/trace/sim prove the need.

## Agent Prompts

Use these as starting prompts for subagents.

### Bootstrap-Bob / Flux.test

```text
Design the Bootstrap-Bob all-install verification artifact and Flux.test acceptance contract.
Inventory current test conventions, env gates, cleanup risks, and propose a manifest-driven runner.
Return fixture contract, suite manifest shape, staged test suites, cleanup boundaries, and first implementation steps.
Do not edit files unless explicitly instructed.
```

### Flux.live

```text
Explore and design Flux.live configurable card scopes. Start from /live/pad-overview/.
Use group/kind naming, not equipment_type/cell_type.
Include CSV contract, scope/card/point model proposal, migration risk, live update behavior, hot/warm/cold demand reset behavior, and first implementation steps.
Do not edit files unless explicitly instructed.
```

### Flux.trace

```text
Explore and design generic Flux.trace scopes from /trace/wells/.
Include CSV contract, dropdown source selection, stable source IDs, next/previous, zoom controls, staged windows, compression disclosure, and first implementation steps.
Do not edit files unless explicitly instructed.
```

### Flux.trace Embed

```text
Design trace embed mode for /trace/{scope}/embed/.
Include minimal chrome behavior, external control/event interface, payload reuse, source/window controls, testing strategy, and implementation risks.
Do not edit files unless explicitly instructed.
```

### Flux.opt / Flux.serve

```text
Explore Flux.opt and Flux.serve sampling architecture.
Design hot/warm/cold lanes, demand reset semantics, history config discovery through fluxy getConfiguration, Flux.plane handoff, and a dedicated sampling worker.
Return risks, sequence, and first implementation steps.
Do not edit files unless explicitly instructed.
```

### Flux.sim

```text
Explore Flux.sim Bootstrap-Bob and production-data simulation.
Design create/delete device/tag functions, Bootstrap-Bob persistence, online/offline behavior, polynomial/sine profile abstraction, persistence location, pure unit tests, and no-Ignition first implementation path.
Do not edit files unless explicitly instructed.
```

### Flux.cell / Flux.lock Watcher

```text
Track Flux.cell and Flux.lock pressure without implementing full models.
Review live, trace, sim, stale/recovery, and interlock requirements.
Return where group/kind/interlock concepts repeat and when a real Cell model becomes the simplest architecture.
Do not edit files unless explicitly instructed.
```
