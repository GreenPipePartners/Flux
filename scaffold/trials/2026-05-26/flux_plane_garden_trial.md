# Garden Curator Trial: flux_plane

## Runner Capability

- Requested reasoning mode: `Low`.
- Actual model-level reasoning control: not exposed by the current task tool.
- Enforcement used: low-curator prompt, read-only scope, fixed output schema.

## Files Reviewed

- `scaffold/agents/garden_curator_low.md` - low-mode packet and output rules.
- `scaffold/gardens/flux_plane/garden.md` - Flux.plane ownership, boundaries, source inventory.
- `scaffold/gardens/flux_plane/contracts.md` - Series/Latest/WindowStat contracts.
- `web/Flux/src/flux/plane/models.py` - Plane `Series`, `Latest`, `Sample`, `WindowStat` schema models.
- `web/Flux/src/flux/plane/services.py` - series resolution, latest/sample mirroring, window stats, status emission.
- `web/Flux/src/flux/plane/samples.py` - Plane sample read boundary.
- `web/Flux/src/flux/plane/questdb_samples.py` - QuestDB Plane sample export/read helpers.
- `web/Flux/src/flux/plane/runtime.py` - bad-quality runtime mirroring into Plane.
- `web/Flux/src/flux/plane/sample_seed.py` - legacy runtime history seed into Plane samples.
- `web/Flux/src/flux/chart/data_plane.py` - Chart PostgreSQL consumer over Plane samples.
- `web/Flux/src/flux/spot/selectors.py` - Spot/current-state consumer of Plane latest/window stats.

## Confirmed Ownership

- Flux.plane owns data-plane storage/read contracts for sampled series, latest values, historical samples, and fixed window stats.
- Source confirms schema-qualified `plane.series`, `plane.latest`, `plane.sample`, and `plane.window_stat` models.

## Non-Ownership Boundaries

- Flux.plane does not own Ignition/WebDev reads, worker supervision, bridge probing, Spot layout, Chart membership/navigation, or browser/HTMX cadence.
- Spot consumes Plane rows and falls back to runtime rows when Plane linkage/latest is missing.

## Existing Tests Found

- `web/Flux/src/flux/live/tests.py` - covers Spot markers using Plane latest plus QuestDB Plane sample ranges.
- `web/Flux/src/flux/trace/tests.py` - covers Plane series identity, sample sync/upsert, runtime-history seeding, local Plane sample chart payloads, and routes.
- `web/Flux/src/flux/trace/test_e2e_playwright.py` - covers Playwright chart flows backed by seeded Plane samples.
- `web/Flux/src/flux/sim/tests_fluxolot_fishtank.py` - covers Fluxolot install seeding Plane samples.
- `web/Flux/src/flux/cell/tests.py` - covers Cell page preference for Plane samples.
- `web/Flux/src/flux/serve/tests.py` - mentions `Flux.plane.qdb` service snapshot status.

## Risks

- Severity: Medium
- Owner: Flux.plane
- Evidence: `web/Flux/src/flux/plane/questdb_samples.py:103-107`
- Risk: QuestDB `today` uses `now - 1 day`, while Plane service window logic uses local midnight, so fixed-window semantics can diverge.

- Severity: Low
- Owner: Flux.spot/live
- Evidence: `web/Flux/src/flux/spot/selectors.py:139-183`
- Risk: Runtime fallback can hide missing Plane linkage or missing Plane latest rows from current-state consumers.

## Proposed Bounded Test

- Add one bounded test asserting QuestDB Plane `today` window semantics match the Plane service `WindowStat.Window.TODAY` local-midnight boundary for a fixed `now`.

## Meta-Architect Disposition

- Accepted both risks as scaffold findings.
- No application source change authorized from this trial alone.
