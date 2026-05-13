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
- `flux.trace`: historical HTMX display.

See `docs/architecture-roadmap.md` for the current roadmap.
