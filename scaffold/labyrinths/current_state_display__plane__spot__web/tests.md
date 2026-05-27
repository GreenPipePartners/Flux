# Tests: current_state_display__plane__spot__web

## Existing Tests Found

- `web/Flux/src/flux/live/tests.py::test_scope_cards_use_questdb_plane_sample_ranges_for_spot_markers` - covers selector use of `plane.Latest` and `Series` for `scope_cards()`.
- `web/Flux/src/flux/live/tests.py::test_live_scope_routes_filter_by_group` - covers `/spot/<scope>/` route rendering scope cards.
- `web/Flux/src/flux/live/tests.py::test_live_scope_cards_partial_loads` - covers `/spot/<scope>/cards/` partial rendering card markup.

## Proposed Bounded Scaffold Tests

- Fixture-backed selector test for Spot point linked to Plane latest.
- Fixture-backed view/template test for rendered value/quality/freshness.
- Negative test for missing Plane latest state.
- Focused Django test that creates `Series` with `Latest(value=80.0, quality_code="Good")`, links a `LiveCardPointDefinition.series`, requests a Spot scope route, and asserts the rendered card value/quality/label.

## Test Boundaries

- No live Ignition.
- No worker startup.
- No sleeps.
- No browser unless testing HTMX swap behavior specifically.
- Target runtime under 30 seconds.
