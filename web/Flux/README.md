# Flux

Flux is a read-optimized Django/HTMX companion UI for Ignition runtime data.

Ignition owns tag reads and writes sampled `QualifiedValue` results into Postgres. Flux reads those database rows to render fast operations screens without live Perspective bindings or websocket-heavy dashboards.

## Local Development

For the current local operator workflow, prefer the top-level `flux` CLI from the repository root:

```bash
flux install-service
flux start
flux doctor
```

See `../../docs/operator-guide.md`.

Manual Django-only startup remains useful for isolated checks:

```bash
uv sync
uv run python manage.py migrate
uv run python manage.py runserver --noreload -6 [::]:8000
```

Local settings default to SQLite when `DATABASE_URL` is empty. Production should use Postgres.

SQLite is acceptable for simple page checks, but it will lock under the live demo pattern where Django serves HTMX requests while a worker writes runtime values. Use Postgres for any concurrent web + worker run.

## Local Postgres

Create a local Flux database and role:

```bash
sudo -u postgres createuser --pwprompt flux
sudo -u postgres createdb --owner flux flux
```

Create `.env` from the example:

```bash
cp .env.example .env
```

Ensure it contains:

```text
DATABASE_URL=postgres://flux:flux@localhost:5432/flux
```

Then migrate and run:

```bash
uv run python manage.py migrate
uv run python manage.py runserver
```

Run the live Field demo worker in another terminal:

```bash
uv run python manage.py run_sim_demo --interval 10
```

## Flux Sim Provider Selection

The `/sim/` page includes two simulation areas:

- Django `SimTag` scheduled memory-tag simulation.
- Imported Flux Sim provider-tree selection backed by `sim/flux-sim.db`.

Import an Ignition provider export into the standalone Flux Sim database:

```bash
uv run python manage.py import_tag_provider_export ../../tags02.json --provider ACM02
```

Then open:

```text
http://localhost:8000/sim/?provider=ACM02
```

The imported provider tree supports:

- Collapsible `>` / `v` branches.
- Folder icon `📁`, UDT instance icon `◆`, and standalone atomic tag icon `●`.
- Checkbox selection with recursive parent selection.
- Indeterminate parent state when only child branches are selected.
- UDT-instance-level selection instead of showing every inherited child atomic tag.
- Standalone atomic tag selection when the tag is not under a UDT instance.

Save selected branches with `Save Selection`, then export selected OPC source paths:

```bash
curl 'http://localhost:8000/sim/imported/selected-paths.json?provider=ACM02' \
  > ../../sim/selected-paths.json
```

Use that file with `flux-sim-configure-ignition`:

```bash
cd ../../sim
uv run --with ../fluxy flux-sim-configure-ignition \
  field-config.sim.json \
  --base-url http://localhost:8088/system/webdev/flux \
  --token "$FLUXY_TOKEN" \
  --tag-provider default \
  --tag-folder ACM02 \
  --opc-server "Flux Sim ACM02" \
  --provider ACM02 \
  --sim-database flux-sim.db \
  --selected-paths-file selected-paths.json
```

Apply migrations after pulling these changes:

```bash
uv run python manage.py migrate sim
```

## Flux Trace

`flux.trace` uses uPlot for visualizing sample tag history. uPlot assets are vendored locally under `src/static/flux/vendor/uplot/`, and Trace behavior is split into static ES modules under `src/static/flux/trace/`.

The current trace uses local sample tag data and returns a renderer-neutral shape:

```json
{
  "series": [
    {"name": "tag", "fullPath": "[default]Path/Tag", "x": [], "y": []}
  ]
}
```

Trace is now a first-class operating space. Its fast path is configured tags plus `TraceSignal` significance, synced from Ignition historian into local `TraceCachePoint` rows, then rendered from the local rolling cache.

See `../../docs/trace-architecture.md`.

Seed the first ten navigation wells through the Ignition-backed Trace path:

```bash
uv run python manage.py seed_nav_well_trace --limit 10 --configure-ignition --inject-history --update-live --sync-cache
```

Then open:

```text
http://localhost:8000/trace/wells/
```

## Live Extraction Trial

The live-to-sim extraction trial builds memory tags and raw history in a live namespace, extracts tag config/history through Fluxy, recreates the tags in a sim namespace, and replays the extracted history.

Run the command against the local dev gateway:

```bash
uv run python manage.py trial_live_extraction --cleanup
```

Run the gated integration test:

```bash
FLUX_LIVE_EXTRACTION_INTEGRATION=1 uv run pytest src/flux/sim/test_integration_live_extract.py -q
```

This is closed-loop for tag state. Raw historian data-point deletion is not available through public Ignition/Fluxy APIs, so database-specific cleanup adapters are documented as the next step.

See `../../docs/live-extraction.md`.

## First-Run Setup

After deployment and migrations, Flux redirects to `/setup/` when no users exist. That page creates the initial Django superuser and then disables itself automatically because at least one user exists.

This is intentionally a bootstrap-only web configuration path for production environments where shell access should not be required for the first administrator.

## Boundary

- Flux reads runtime values from the database.
- Ignition reads tags and writes runtime value snapshots.
- Control/write workflows remain in Perspective for the initial version.

## Architecture Namespaces

- `flux.serve`: service lifecycle, wrappers, heartbeats, and approved commands.
- `flux.opt`: browse/read optimization, refresh lanes, leases, and cold-spot strategy.
- `flux.sim`: simulated tag configuration, scheduled writes, and historical backfill.
- `flux.base`: persistent datastore, including FieldAgent endpoint/device/tag configuration.
- `flux.live`: live/current-state HTMX display.
- `flux.trace`: historical and live uPlot traces over recorded runtime samples.

See `docs/architecture-roadmap.md` for the current roadmap.

Repository-level docs start at `../../docs/README.md`.
