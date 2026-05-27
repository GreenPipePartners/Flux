# Labyrinth: current_state_display__plane__spot__web

## Purpose

Observe the bounded path from cached Plane current-state data into Spot/Web display without browser-owned runtime truth.

## Node Chain

1. Flux.plane
2. Flux.spot/live compatibility layer
3. Flux.web/Django templates/HTMX display

## Success Signal

A linked Spot point can render a Plane latest value, quality, and freshness state through a server-rendered Django/HTMX surface without direct Ignition IO from the request/browser path.

## Explicit Bounds

- no live Ignition access
- no worker startup
- no browser-required truth acquisition
- fixture-backed database state preferred
- runtime target under 30 seconds

## Source Files

- `web/Flux/src/flux/plane/models.py` - Plane latest/sample/window storage.
- `web/Flux/src/flux/plane/services.py` - Plane write/mirror contracts.
- `web/Flux/src/flux/live/selectors.py` - current-state selector boundary.
- `web/Flux/src/flux/live/views.py` - current-state view boundary.
- `web/Flux/src/templates/dashboard/home.html` - dashboard Comp Surface display boundary when Spot/health data is surfaced there.

## Failure Matrix

| Failure | Likely Owner | Evidence Needed |
|---|---|---|
| Plane latest row missing for linked point | Flux.plane / producer path | Series/latest fixture or worker output evidence |
| Spot ignores linked Plane series | Flux.spot/live | Selector result evidence |
| Web request performs external IO for display truth | Flux.web/architecture | View/template/service call evidence |
| Browser refresh is treated as sampler | Flux.web/Flux.serve boundary | HTMX route and worker/sampler evidence |
| Other grid/display state hidden by detail/config mode | Flux.web Comp Surface | Browser/template test evidence |

## Existing Tests

- Pending curator inventory.

## Proposed Scaffold Tests

- Create fixture rows for `base.tag`, `plane.series`, `plane.latest`, and a linked Spot point; assert the server-rendered response uses Plane latest data without requiring sampler execution.
- Add a negative fixture where Plane latest is missing and assert display/status makes the missing state visible rather than claiming fresh runtime truth.

## Meta-Architect Synthesis

- Last reviewed: 2026-05-26
- Decision: pilot labyrinth accepted as scaffold-only context.
