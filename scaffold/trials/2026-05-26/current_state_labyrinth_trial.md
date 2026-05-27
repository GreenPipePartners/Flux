# Labyrinth Curator Trial: current_state_display__plane__spot__web

## Runner Capability

- Requested reasoning mode: `Low`.
- Actual model-level reasoning control: not exposed by the current task tool.
- Enforcement used: low-curator prompt, read-only scope, fixed output schema.

## Node Chain Checked

1. Flux.plane cached latest - `web/Flux/src/flux/plane/models.py`
2. Flux.live/spot scope definition - `web/Flux/src/flux/live/models.py`
3. Flux.spot selector - `web/Flux/src/flux/spot/selectors.py`
4. Flux.spot view - `web/Flux/src/flux/spot/views.py`
5. Flux.web rendered display - `web/Flux/src/templates/live/partials/pad_overview_cards.html`

## Success Signal Testability

- Testable: yes
- Reason: A Django test can create a `plane.Series` plus `plane.Latest`, bind it to a `LiveCardPointDefinition`, request a Spot scope route, and assert the rendered card value.

## Handoffs

- From Flux.plane to Flux.live/spot: `LiveCardPointDefinition.series` is a nullable FK to `plane.Series`, while `plane.Latest` stores one cached latest row per series.
- From Flux.live/spot definition to Flux.spot selector: `scope_cards()` prefetches `cards__points__series`, loads series with latest, and calls `live_point_from_plane()` when available.
- From Flux.spot selector to Flux.spot view: `scope_detail()` renders `live/scope.html` using filtered scope cards.
- From Flux.spot view to Flux.web display: live templates render `point.display_value`, `point.quality`, and `point.full_path`.

## Failure Matrix Updates

| Failure | Likely Owner | Evidence |
|---|---|---|
| Plane latest exists but is not selected for a Spot point | Flux.spot selector | `web/Flux/src/flux/spot/selectors.py` |
| Spot scope route renders missing value despite Plane latest | Flux.spot view/template | `web/Flux/src/flux/spot/views.py`, `web/Flux/src/templates/live/partials/pad_overview_cards.html` |
| Point definition is not linked to cached Plane state | Flux.live model/config owner | `web/Flux/src/flux/live/models.py` |

## Existing Tests Found

- `web/Flux/src/flux/live/tests.py::test_scope_cards_use_questdb_plane_sample_ranges_for_spot_markers` - covers selector use of `plane.Latest` and `Series` for `scope_cards()`.
- `web/Flux/src/flux/live/tests.py::test_live_scope_routes_filter_by_group` - covers `/spot/<scope>/` route rendering scope cards.
- `web/Flux/src/flux/live/tests.py::test_live_scope_cards_partial_loads` - covers `/spot/<scope>/cards/` partial rendering card markup.

## Proposed Bounded Test

- Add one Django test that creates a `Series` via `ensure_series_for_full_path()`, creates `Latest(value=80.0, quality_code="Good")`, creates a `LiveScope` card point with `series=series`, requests a Spot route, and asserts value, quality, point label, and refresh panel markup render.

## Meta-Architect Disposition

- Accepted path as testable pilot labyrinth.
- No additional architecture finding accepted beyond the Plane garden findings.
