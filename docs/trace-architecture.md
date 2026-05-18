# Flux Trace Architecture

Flux Trace is performance-first. If chart behavior adds browser or server IO pressure, it does not fit Flux.

Flux Trace is a first-class operating space, not an appended chart UI. Its job is to turn configured tags plus trace significance into fast local rolling-history views. Process domains such as wells, pads, lines, machines, or facilities may provide tag selections, but Trace must remain process agnostic.

## Boundaries

- Django views provide initial payloads and lightweight polling endpoints only.
- Tag configuration remains the source of tag identity. Trace adds significance metadata for rendering and caching.
- `TraceProfile` groups signals into an operator-facing trace view.
- `TraceSignal` points at a configured `RuntimeTag` and defines significance: display label, unit, axis group, display range, sort order, visibility, and cache eligibility.
- `TraceCachePoint` is the local rolling-history cache for fast chart reads.
- `TraceCacheCursor` tracks historian sync progress.
- root `trace.cache` owns cache read/sync behavior.
- root `trace.providers.*` owns demo/provider process logic such as navigation-well seeding and Ignition provisioning.
- `flux.serve` owns worker orchestration for keeping cache current.
- uPlot owns canvas rendering.
- uPlot assets are vendored under `static/flux/vendor/uplot/` so Trace works offline.
- Static ES modules own trace behavior. There is no frontend build chain yet.

Views must not create historian data, query Ignition in hot loops, or perform cache maintenance. They resolve request state and return read-model payloads.

## Rolling Cache Path

The intended fast path is:

```text
tag configuration -> TraceSignal significance -> Fluxy historian bulk query -> TraceCachePoint -> uPlot payload
```

The page read path is local:

```text
browser -> Django view -> TraceCachePoint -> compact shared-x JSON -> uPlot
```

The worker path is external IO:

```text
flux.serve worker -> Fluxy/Ignition historian -> idempotent TraceCachePoint upsert -> retention prune
```

This separation is intentional. Local chart reads should be fast even when Ignition is slow, expired, or temporarily unavailable.

## Navigation Wells Demo

The current navigation-well trace page is a demo provider over the generic Trace architecture, not core Trace domain logic.

Open:

```text
http://localhost:8000/trace/wells/
```

Behavior:

- One template page.
- Previous/Next Well buttons cycle data sources.
- Left/right arrow keys also cycle data sources.
- Each selected well resolves to one `TraceProfile`.
- Each well profile has exactly eight `TraceSignal` rows.
- The chart reads local `TraceCachePoint` rows only.

Seed the first ten navigation wells through the real Ignition-backed path:

```bash
cd web/Flux
uv run python manage.py seed_nav_well_trace --limit 10 --configure-ignition --inject-history --update-live --sync-cache
```

Run one live/update/cache cycle:

```bash
cd web/Flux
uv run python manage.py flux_worker --once --nav-well-live --nav-well-limit 10
```

Run continuously every minute:

```bash
cd web/Flux
uv run python manage.py flux_worker --nav-well-live --nav-well-limit 10 --interval 60
```

The real path for this demo is:

```text
/nav/ well options -> 8 trace tags per well -> Ignition memory tags -> Ignition historian -> Fluxy historian query -> TraceCachePoint -> /trace/wells/
```

## JavaScript Modules

```text
web/Flux/src/static/flux/trace/
  data.js             payload alignment, nearest-sample lookup, live series merge
  chart.js            uPlot construction and resize boundary
  interactions.js     wheel zoom, side-scroll pan, drag pan, click index lookup
  markers.js          pinned markers, marker table, markdown export, annotation overlay
  historical-page.js  historical trace page bootstrap
  live-page.js        live polling and right-edge-follow bootstrap
```

## Performance Rules

- Keep templates thin; no large inline chart behavior.
- Transform data once per payload, then pass arrays directly to uPlot.
- Avoid DOM churn inside pan, zoom, hover, and live-poll paths.
- Keep marker table rendering event-driven, not tied to every chart redraw.
- Do not introduce a framework or build step until native modules become the bottleneck.
- Live polling should merge samples by tag id and timestamp instead of rebuilding trace identity from scratch.

## Feature Direction

- Persisted trace sessions and annotations should be server-side models, not browser-only state.
- The browser should render only the active viewport and selected marker context.
- Any higher-volume historian path needs server-side decimation/windowing before it reaches uPlot.
- Trace series render line-only by default. Point markers are visual noise for trend work and become expensive at one-minute historian density.
- JSON payloads are acceptable for trial-scale data, but long-term Trace should avoid repeated per-series ISO timestamps. Prefer an async, shared-x payload shape first; consider binary/columnar transport only after measuring JSON parsing as the bottleneck.
- Do not perform per-tag historian reads. Bulk query paths by profile/source group.
- Do not use `TagSample` as the first-class trace cache. It is runtime sample history, not the trace rolling-history read model.

## Browser Tests

Trace has a gated Playwright suite for real uPlot interaction behavior.

Install Chromium once for the local Playwright cache:

```bash
cd web/Flux
uv run python -m playwright install chromium
```

Run the browser tests:

```bash
cd web/Flux
FLUX_PLAYWRIGHT=1 DATABASE_URL= uv run pytest src/flux/trace/test_e2e_playwright.py -q
```

Current coverage:

- historical trace click pins a marker and renders the marker table
- horizontal wheel/trackpad side-scroll pans the uPlot x-axis

The tests are skipped by default because they require a browser runtime.

## Removed Spikes

The earlier oilfield-specific trial was removed. Its useful lessons are now carried by the process-agnostic Trace architecture and the navigation-well provider:

- eight dense one-minute signals are a good trial payload shape
- Fluxy/Ignition should be isolated from page read paths by local rolling cache
- shared-x payloads are mandatory for dense data
- line-only rendering is the default

Do not reintroduce process-specific naming into root `trace.cache`, `TraceProfile`, `TraceSignal`, or worker orchestration.
