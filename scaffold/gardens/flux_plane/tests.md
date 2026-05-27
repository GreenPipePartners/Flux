# Tests: flux_plane

## Existing Tests Found

- `web/Flux/src/flux/live/tests.py` - covers Spot selector use of Plane latest and QuestDB Plane sample ranges.
- `web/Flux/src/flux/trace/tests.py` - covers Plane series identity, sample sync/upsert, runtime-history seeding, local Plane sample chart payloads, and routes.
- `web/Flux/src/flux/trace/test_e2e_playwright.py` - covers Playwright chart flows backed by seeded Plane samples.
- `web/Flux/src/flux/sim/tests_fluxolot_fishtank.py` - covers Fluxolot install seeding Plane samples.
- `web/Flux/src/flux/cell/tests.py` - covers Cell page preference for Plane samples.
- `web/Flux/src/flux/serve/tests.py` - mentions `Flux.plane.qdb` service snapshot status.

## Proposed Bounded Scaffold Tests

- Verify resolving a known `base.tag` creates/reuses one Plane series with stable storage key.
- Verify mirrored latest samples update Plane latest without requiring a web request.
- Verify Plane sample read helpers return bounded ordered samples for a known series.
- Verify missing Plane linkage is visible to consumers rather than silently producing misleading freshness claims.
- Verify QuestDB-backed `today` window semantics match Plane service `WindowStat.Window.TODAY` semantics for a fixed `now`.

## Test Boundaries

- Default tests must use fixture-backed database state.
- No live Ignition access.
- No worker loops.
- No sleep-based polling.
- Target runtime under 10 seconds per focused Plane scaffold test file.
