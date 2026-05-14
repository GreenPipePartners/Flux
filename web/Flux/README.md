# Flux

Flux is a read-optimized Django/HTMX companion UI for Ignition runtime data.

Ignition owns tag reads and writes sampled `QualifiedValue` results into Postgres. Flux reads those database rows to render fast operations screens without live Perspective bindings or websocket-heavy dashboards.

## Local Development

```bash
uv sync
uv run python manage.py migrate
uv run python manage.py runserver
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
uv run python manage.py run_field_demo --interval 10
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

## Flux Trace Trial

`flux.trace` now has an initial Plotly trial boundary for visualizing sample tag history. The current trial uses local sample tag data and returns a Plotly-friendly shape:

```json
{
  "series": [
    {"name": "tag", "fullPath": "[default]Path/Tag", "x": [], "y": []}
  ]
}
```

The intended next step is a Fluxy historian adapter that returns the same shape from Ignition history, so the chart does not care whether data came from local samples or a live historian query.

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
- `flux.field`: field-device exposure, starting with a .NET OPC UA server boundary.
- `flux.live`: live/current-state HTMX display.
- `flux.trace`: historical and live Plotly trace trials over recorded runtime samples.

See `docs/architecture-roadmap.md` for the current roadmap.
