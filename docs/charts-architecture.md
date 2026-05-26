# Flux Chart Architecture

Flux.chart is performance-first. If chart behavior adds browser or server IO pressure, it does not fit Flux.

Flux.chart is a first-class operating space, not an appended chart UI. Its job is to turn configured tags plus chart significance into fast local rolling-history views. Process domains such as wells, pads, lines, machines, or facilities may provide tag selections, but Chart must remain process agnostic.

## Boundaries

- Django views provide initial payloads and lightweight polling endpoints only.
- Tag configuration remains the source of tag identity. Charts adds significance metadata for rendering and caching.
- `TraceProfile` groups signals into an operator-facing chart view.
- `TraceSignal` points at a configured `RuntimeTag` and defines significance: display label, unit, axis group, display range, sort order, visibility, and cache eligibility.
- `plane.sample` is the local rolling-history cache for fast chart reads.
- `TraceCacheCursor` tracks historian sync progress.
- `flux.chart.cache` owns cache read/sync behavior.
- `flux.chart.providers.*` owns demo/provider process logic such as navigation-well seeding and Ignition provisioning.
- `flux.serve` owns worker orchestration for keeping cache current.
- uPlot owns canvas rendering.
- uPlot assets are vendored under `static/flux/vendor/uplot/` so Charts works offline.
- Static ES modules own chart behavior. There is no frontend build chain yet.

Views must not create historian data, query Ignition in hot loops, or perform cache maintenance. They resolve request state and return read-model payloads.

## Rolling Cache Path

The intended fast path is:

```text
tag configuration -> TraceSignal significance -> Fluxy historian bulk query -> plane.sample -> uPlot payload
```

The page read path is local:

```text
browser -> Django view -> plane.sample -> compact shared-x JSON -> uPlot
```

The worker path is external IO:

```text
flux.serve worker -> Fluxy/Ignition historian -> idempotent plane.sample upsert
```

This separation is intentional. Local chart reads should be fast even when Ignition is slow, expired, or temporarily unavailable.

## Navigation Wells Demo

The current navigation-well chart page is a demo provider over the generic Charts architecture, not core Charts domain logic.

Open:

```text
http://localhost:8000/chart/wells/
```

Behavior:

- One template page.
- Previous/Next Well buttons cycle data sources.
- Left/right arrow keys also cycle data sources.
- Each selected well resolves to one `TraceProfile`.
- Each well profile has exactly eight `TraceSignal` rows.
- The chart reads local `plane.sample` rows only.

Seed the first ten navigation wells through the real Ignition-backed path:

```bash
uv run python web/Flux/manage.py seed_nav_well_charts --limit 10 --configure-ignition --inject-history --update-live --sync-cache
```

Run one live/update/cache cycle:

```bash
uv run python web/Flux/manage.py flux_worker --once --nav-well-live --nav-well-limit 10
```

Run continuously every minute:

```bash
uv run python web/Flux/manage.py flux_worker --nav-well-live --nav-well-limit 10 --interval 60
```

The real path for this demo is:

```text
/nav/ well options -> 8 chart tags per well -> Ignition memory tags -> Ignition historian -> Fluxy historian query -> plane.sample -> /chart/wells/
```

## Large Chart Sets

Large chart sets must use a bounded navigation surface.

The dashboard may show counts and aggregate entry points, but it should not render one link per enabled `TraceProfile` when hundreds or thousands of profiles are enabled. Use:

- one single-page cycling surface for homogeneous stress families, such as `/chart/wells/`
- a paginated or searchable profile index for operator-created profiles
- explicit route summaries in dashboard readiness cards

Preserve stress rows and source data. Clean the UI by filtering, grouping, pagination, or category-aware route summaries, not by truncating `TraceProfile`, `TraceSignal`, `RuntimeTag`, or `plane.sample` records.

## Chart Data Planes

Flux.chart has two read models in current use:

- `plane.sample` in Flux Postgres is the durable local rolling-history cache and control-plane staging area.
- QuestDB `plane_samples` is the high-volume serving/export plane for stress surfaces such as navigation wells.

Current gap: generic chart profiles can read from local `plane.sample`, while navigation wells prefer QuestDB payloads. If QuestDB is empty, seeded profiles can still exist but the large stress payload may be empty until Plane sample rows are exported.

Operational restore path for nav-well stress data:

```bash
uv run python web/Flux/manage.py seed_nav_well_charts --limit 10 --local-bootstrap-cache
uv run python web/Flux/manage.py sync_charts_questdb --limit 10 --replace
```

Use `--limit` for a fast smoke test, then remove it only when the single-page navigation and data-plane performance are acceptable.

## JavaScript Modules

```text
web/Flux/src/static/flux/chart/
  data.js             payload alignment, nearest-sample lookup, live series merge
  chart.js            uPlot construction and resize boundary
  interactions.js     wheel zoom, side-scroll pan, drag pan, click index lookup
  markers.js          pinned markers, marker table, markdown export, annotation overlay
  historical-page.js  historical chart page bootstrap
  live-page.js        live polling and right-edge-follow bootstrap
```

## Performance Rules

- Keep templates thin; no large inline chart behavior.
- Transform data once per payload, then pass arrays directly to uPlot.
- Avoid DOM churn inside pan, zoom, hover, and live-poll paths.
- Keep marker table rendering event-driven, not tied to every chart redraw.
- Do not introduce a framework or build step until native modules become the bottleneck.
- Live polling should merge samples by tag id and timestamp instead of rebuilding chart identity from scratch.

## Feature Direction

- Persisted chart sessions and annotations should be server-side models, not browser-only state.
- The browser should render only the active viewport and selected marker context.
- Any higher-volume historian path needs server-side decimation/windowing before it reaches uPlot.
- Chart series render line-only by default. Point markers are visual noise for trend work and become expensive at one-minute historian density.
- JSON payloads are acceptable for trial-scale data, but long-term Chart should avoid repeated per-series ISO timestamps. Prefer an async, shared-x payload shape first; consider binary/columnar transport only after measuring JSON parsing as the bottleneck.
- Do not perform per-tag historian reads. Bulk query paths by profile/source group.
- Do not use `TagSample` as the first-class chart cache. It is runtime sample history, not the chart rolling-history read model.

## Browser Tests

Flux.chart has a gated Playwright suite for real uPlot interaction behavior.

Install Chromium once for the local Playwright cache:

```bash
uv run python -m playwright install chromium
```

Run the browser tests:

```bash
FLUX_PLAYWRIGHT=1 DATABASE_URL= uv run pytest web/Flux/src/flux/trace/test_e2e_playwright.py -q
```

Current coverage:

- historical chart click pins a marker and renders the marker table
- horizontal wheel/trackpad side-scroll pans the uPlot x-axis

The tests are skipped by default because they require a browser runtime.

## Removed Spikes

The earlier oilfield-specific trial was removed. Its useful lessons are now carried by the process-agnostic Chart architecture and the navigation-well provider:

- eight dense one-minute signals are a good trial payload shape
- Fluxy/Ignition should be isolated from page read paths by local rolling cache
- shared-x payloads are mandatory for dense data
- line-only rendering is the default

Do not reintroduce process-specific naming into `flux.chart.cache`, `TraceProfile`, `TraceSignal`, or worker orchestration.
