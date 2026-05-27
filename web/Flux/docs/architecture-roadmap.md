# Flux Architecture Roadmap

This document summarizes the current implementation state after the first live demo buildout.

## Current Goal

Flux is being shaped into an on-prem Django/HTMX companion UI for Ignition runtime data. The current path is:

- `Flux.FieldAgent` simulates field devices through OPC UA.
- Ignition reads those OPC UA tags through Fluxy-configured tags.
- `run_sim_demo` reads Ignition values through Fluxy and writes snapshots to Flux base runtime tables.
- `flux.live` renders DB-backed live values with HTMX, avoiding direct browser/Perspective tag bindings.
- Chart, Spot, and Dashboard render server-side Django/HTMX views from local Flux storage; retired advanced navigation tables remain only in migration history.

## Running Local Stack

Expected local services:

```bash
dotnet run --project field/Flux.FieldAgent/Flux.FieldAgent.csproj --FluxField:ConfigPath=/home/bobby/Projects/11006-PRW-flux/web/Flux/field/field-config.json
uv run python manage.py runserver 0.0.0.0:8000
uv run python manage.py run_sim_demo
```

Current Postgres connection:

```text
postgres://flux:flux@localhost:5432/flux
```

Useful local pages:

- `http://localhost:8000/spot/`
- `http://localhost:8000/spot/pad-overview/`
- `http://localhost:8000/chart/`
- `http://localhost:8000/chart/stream/`

## Field Demo

The Field demo is now expanded to six demo assets and twenty runtime tags:

- `DemoWell_01`
- `DemoWell_02`
- `DemoMeter_01`
- `DemoMeter_02`
- `DemoTank_01`
- `DemoTank_02`

The source of the demo asset/tag definitions is:

```text
src/flux/field/demo.py
```

The runtime/Ignition mapping is:

```text
src/flux/opt/demo.py
```

To apply demo changes locally:

```bash
uv run python manage.py shell -c "from flux.sim.demo import ensure_demo_runtime_config; print(len(ensure_demo_runtime_config()))"
uv run python manage.py export_field_config --output field/field-config.json
uv run python manage.py run_sim_demo --configure-ignition --once
```

Then restart FieldAgent and the continuous demo reader.

## Spot UI

`flux.spot` currently has a Pad Overview demo backed by the historical `flux.live` Django app label with:

- Equipment tabs: `Well`, `Meter`, `Tank`.
- Cards grouped by runtime tag `asset_name`.
- Values formatted for display only; float display is truncated down to three decimal places.
- Units always shown below values.
- Historical min/max range rails under values.
- A shared `Next read` timer just below the equipment tabs.

The shared timer is intentionally not rendered per field anymore. It lives in the HTMX-refreshed content panel so it updates every second with the cards.

Important templates:

- `src/templates/live/pad_overview.html`
- `src/templates/live/partials/pad_overview_tab_panel.html`
- `src/templates/live/partials/pad_overview_content.html`
- `src/templates/live/partials/pad_overview_cards.html`

Spot selector logic is in:

```text
src/flux/spot/selectors.py
```

## Chart Trial UI

`flux.chart` has two uPlot-backed pages over `runtime.TagSample`:

- `http://localhost:8000/chart/`: historical sample chart.
- `http://localhost:8000/chart/stream/`: polling streaming chart trial.

`/trace/` and `/charts/` remain compatibility redirects to `/chart/`.

The old trial URLs remain as redirects only:

- `http://localhost:8000/trace-clone/`: historical trace compatibility route.
- `http://localhost:8000/trace-clone/live/`: compatibility redirect to the polling streaming chart route.

Historical chart trial features:

- Numeric `TagSample` streams are rendered as uPlot series.
- Wheel zoom and drag pan are handled by local uPlot plugins.
- Clicking inside the chart pins the nearest numbered marker, such as `(1)`, on the chart.
- Pinned marker values are listed below the chart in a cross-tab table.
- The table uses marker rows and trace-name columns.
- Long trace headers are middle-ellipsized to 15 characters with the full trace name in the native browser tooltip.
- Missing values remain blank; marker values come from the nearest aligned sample timestamp and are not interpolated.
- The marker table can be copied as a Markdown table.
- Each pinned marker row can add a prompt-based chart annotation at the selected point.
- Clear removes pinned markers, annotations, and the marker-value table state.

Streaming chart trial features:

- `/chart/stream/` starts with the latest numeric samples and polls `/chart/stream/samples/` every five seconds.
- Samples are merged by runtime tag id to avoid rebuilding trace identity on each poll.
- The visible x-range follows the newest right edge only while the user is already viewing the newest edge.
- If the user pans or zooms back, new samples are merged without dragging the viewport forward.
- A pause/resume button controls polling.

uPlot chart features:

- Numeric `TagSample` streams are aligned client-side into uPlot's shared x-axis data shape.
- Wheel zoom, side-scroll pan, and drag pan are implemented as small uPlot plugins.
- Historical trace clicks pin numbered vertical markers and render the same marker-value table shape.
- Marker tables can be copied as Markdown, and prompt annotations are drawn as chart overlays.
- Live trace preserves right-edge follow behavior while allowing the user to pan or zoom away from the latest edge.

Important chart files:

```text
src/flux/chart/selectors.py
src/flux/chart/views.py
src/flux/chart/control.py
src/flux/chart/routes.py
src/static/flux/chart/
src/templates/trace/index.html
src/templates/trace/live.html
```

Current chart trial caveats:

- Pinned markers are browser-session state.
- Chart annotations are locally persisted, with Ignition historian sync isolated behind `flux.chart.annotation_bridge`.
- The streaming chart page is a trial polling surface, not the final service-supervised historian UX.

## Runtime Storage

Runtime models are the shared DB spine:

- `RuntimeTag`
- `TagSchedule`
- `LatestTagValue`
- `TagSample`
- `DailyTagExtreme`
- `RuntimeSchedulerConfig`

Daily min/max behavior:

- Current day-to-date extremes are calculated live from `TagSample`.
- Completed days are stored in `DailyTagExtreme`.
- `24h`, `7d`, and `30d` display windows are rolling-midnight windows, not true trailing-hour windows.

Roll up completed days with:

```bash
uv run python manage.py rollup_daily_extremes
```

Or for a specific local date:

```bash
uv run python manage.py rollup_daily_extremes --date YYYY-MM-DD
```

## Scheduler Direction

Runtime scheduler config has been added but is not yet the full demand-aware scheduler.

Current configurable fields:

- `hot_interval_seconds`, default `1`
- `warm_interval_seconds`, default `10`
- `warm_cycles_after_hot`, default `1`
- `cold_bucket_count`, default `60`
- `current_balancer_code`, default `1`
- `balancer_increment`, default `1`
- `demand_lease_seconds`, default `5`

Current behavior:

- `run_sim_demo` reloads scheduler config each loop.
- Demo tags get assigned `balancer_code` values.
- `run_sim_demo --cold-balanced` reads only the current balancer bucket and advances by configured increment.

Target behavior:

- A hot lane reads demanded tags every 1s.
- A warm lane reads recently demanded tags every 10s.
- A cold staggered lane is implemented by the warm loop using `balancer_code` buckets.
- Client demand should be lease-based, because browser/client disconnects are not perfectly reliable.

## Retired Navigation

The advanced `flux.nav` navigation/filter surface and `navigation.db` reference file were retired. `flux.nav` may remain in `INSTALLED_APPS` temporarily as a migration-history shell so Django can apply the table-drop migration.

Current UI navigation should be explicit Django/HTMX page state owned by the consuming app, such as Spot tabs, Chart pagination, and Dashboard Comp Surface mode controls.

## Verification Commands

Focused tests:

```bash
env DATABASE_URL= uv run pytest src/flux/live/tests.py src/runtime/tests.py
```

Django check:

```bash
uv run python manage.py check
```

Useful DB checks:

```bash
psql postgres://flux:flux@localhost:5432/flux -c "select count(*) from runtime_runtimetag where path like 'FluxLiveDemo/%';"
psql postgres://flux:flux@localhost:5432/flux -c "select count(*), max(read_at) from runtime_latesttagvalue where tag_id in (select id from runtime_runtimetag where path like 'FluxLiveDemo/%');"
```

Expected current counts:

- Runtime demo tags: `20`
- Latest demo values: `20`

## Current Known Issues / Next Work

- Demand-aware hot/warm/cold scheduling is not fully implemented yet.
- `run_sim_demo` is still a manual process; proper service supervision is still needed.
- Postgres test DB creation fails for user `flux`, so tests are currently run with `DATABASE_URL=` to use SQLite unless Postgres privileges are adjusted.

## Files Most Likely To Continue From

- `src/flux/spot/views.py`
- `src/flux/spot/selectors.py`
- `src/templates/live/partials/pad_overview_tab_panel.html`
- `src/templates/live/partials/pad_overview_content.html`
- `src/templates/live/partials/pad_overview_cards.html`
- `src/flux/field/demo.py`
- `src/flux/opt/demo.py`
