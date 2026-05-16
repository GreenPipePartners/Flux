# Flux Trace Architecture

Flux Trace is performance-first. If chart behavior adds browser or server IO pressure, it does not fit Flux.

## Boundaries

- Django views provide initial payloads and lightweight polling endpoints.
- `runtime.TagSample` remains the persisted sample source.
- uPlot owns canvas rendering.
- uPlot assets are vendored under `static/flux/vendor/uplot/` so Trace works offline.
- Static ES modules own trace behavior. There is no frontend build chain yet.

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
