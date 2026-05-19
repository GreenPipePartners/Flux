# Flux Operator Guide

This guide covers the local operator workflow built around the top-level `flux` command.

## CLI

Install or refresh the user service and CLI symlink:

```bash
./scripts/flux-service-install.sh
```

This installs:

- `~/.config/systemd/user/flux-stack.service`
- `~/.local/bin/flux` symlinked to `scripts/flux`

Show the getting-started intro:

```bash
flux
flux intro
```

Common commands:

```bash
flux start
flux stop
flux status
flux logs
flux open
flux doctor
```

Ignition dev-cell commands:

```bash
flux ignition info
flux ignition doctor
flux ignition deploy-fluxy
flux ignition request-scan
flux ignition open
```

Field simulation commands:

```bash
flux field import-tag-data Tag_02 \
  --devices "tag_data/tag_data/tag_02 devices.txt" \
  --tags tag_data/tag_data/tags02.json
flux field materialize --provider Tag_02
FLUX_FIELD_AGENT_MODE=supervised flux start
flux field configure-ignition --tag-provider default --tag-folder FieldAgent
flux doctor
```

This is the local operator path from a checked-in `tag_data` export to Ignition-readable simulated OPC tags. Do not use `--skip-raw-config` for provider reconstruction unless you intentionally do not need UDT OPC bindings.

## Background Service

`flux-stack.service` runs the local development stack in the background:

- Django web app on `http://localhost:8000/`
- QuestDB Trace data plane on `postgresql://admin:quest@localhost:8812/qdb`
- FieldAgent OPC UA adapter process or processes, depending on `FLUX_FIELD_AGENT_MODE`
- demo reader that reads Ignition through Fluxy and writes latest values into Flux

The service runs `scripts/flux-start.sh`.

The launcher intentionally:

- runs migrations
- repairs Postgres sequences for copied legacy IDs
- exports FieldAgent config for the legacy single-process FieldAgent path
- starts QuestDB from `.runtime/questdb-dist` with data in `.runtime/questdb-data`
- starts Django through Gunicorn on Linux with `FLUX_WEB_WORKERS=8` and `FLUX_WEB_THREADS=2` by default
- starts Django through Waitress on Windows for native compatibility
- starts FieldAgent in `FLUX_FIELD_AGENT_MODE=legacy` by default, with `FLUX_FIELD_AGENT_MODE=supervised` available for the `Flux.serve` per-device supervisor
- waits until Django responds before declaring the stack ready
- keeps all child services under one cleanup boundary

FieldAgent modes:

- `FLUX_FIELD_AGENT_MODE=legacy` starts one FieldAgent from `web/Flux/field/field-config.json` on `opc.tcp://localhost:4840/flux/field`.
- `FLUX_FIELD_AGENT_MODE=supervised` starts `manage.py flux_field_supervisor`, which writes per-device runtime configs under `.runtime/field-agent` and starts one FieldAgent process per enabled field device.
- Run the supervisor directly with `cd web/Flux && uv run python manage.py flux_field_supervisor --runtime-dir ../../.runtime/field-agent`.

Architecture boundary:

- `Flux.sim` owns the simulated device/tag domain configuration imported from `tag_data` or built through the UI.
- `Flux.base` persists both the simulation catalog and the materialized runtime endpoint/device/tag configuration.
- `Flux.serve` supervises FieldAgent as the OPC UA runtime adapter, with one FieldAgent process per enabled materialized runtime device in supervised mode.
- `Flux.web` configures and displays the state; it does not directly own long-lived FieldAgent processes from request handlers.
- `fluxy` configures Ignition through WebDev by creating OPC UA connections and tags that point at the FieldAgent endpoints.

## Field Simulation Operator Workflow

Use this workflow when the source is an Ignition provider export plus device inventory under `tag_data/`.

1. Import the provider export and device inventory into the Django simulation catalog:

```bash
flux field import-tag-data Tag_02 \
  --devices "tag_data/tag_data/tag_02 devices.txt" \
  --tags tag_data/tag_data/tags02.json
```

This runs `manage.py import_tag_data_catalog`. It imports the provider tree, correlates device inventory, and creates enabled `SimDevice` and `SimDeviceTag` rows. Keep raw config for normal provider reconstruction because UDT OPC bindings live there.

2. Materialize enabled simulation catalog rows into FieldAgent runtime tables:

```bash
flux field materialize --provider Tag_02
```

This runs `manage.py materialize_sim_field_config`. It creates enabled `FieldEndpoint`, `FieldDevice`, and `FieldTag` rows from the imported simulation catalog.

3. Start supervised FieldAgent processes:

```bash
FLUX_FIELD_AGENT_MODE=supervised flux start
```

Supervised mode starts one FieldAgent OPC UA adapter process per enabled materialized runtime device. Runtime configs are written under `.runtime/field-agent`. To inspect the supervisor plan without starting processes, run:

```bash
flux field supervisor --dry-run
```

4. Configure Ignition through Fluxy:

```bash
flux field configure-ignition \
  --tag-provider default \
  --tag-folder FieldAgent
```

This runs `manage.py configure_field_ignition`. It uses Fluxy WebDev to create OPC UA connections for the enabled FieldAgent endpoints and OPC tags under `[default]FieldAgent`. By default it removes the target generated folder and generated OPC UA connections before writing fresh config.

Current limitations:

- Legacy mode remains available and still represents a single-process FieldAgent path; supervised mode is the target architecture.
- Supervised mode is local-service oriented and writes generated process configs under `.runtime/field-agent`.
- Device delay metadata can be materialized, but FieldAgent does not yet enforce request-level delay at runtime.
- Large provider exports can produce large FieldAgent and Ignition configurations; start with a small closed-loop trial before full ACM02 scale.
- Ignition configuration cleanup targets generated folders and generated OPC UA connections, not arbitrary gateway history or unrelated operator-created tags.

Next tests:

- Closed-loop lifecycle: build a test-specific simulated device, materialize it, start supervised FieldAgent, configure Ignition through `fluxy`, read a tag, confirm value change, delete the tag/folder, verify missing, and remove the device.
- Multi-device supervision: verify two enabled materialized devices produce two distinct FieldAgent processes and endpoints.
- Restart recovery: restart `flux-stack.service` with `FLUX_FIELD_AGENT_MODE=supervised` and verify enabled materialized devices return online.
- Runtime behavior: add a FieldAgent-backed test for `slow_network` after the adapter consumes device delay metadata.

5. Verify the whole stack:

```bash
flux doctor
```

`flux doctor` should show the Flux service, Flux web, FieldAgent OPC UA, runtime reads, Live Ignition Bridge, historian, QuestDB, and Ignition dev cell checks. If Ignition is not ready, run `flux ignition doctor --open` and resolve Gateway or Fluxy WebDev readiness first.

For direct Django access, the equivalent commands are:

```bash
cd web/Flux
uv run python manage.py import_tag_data_catalog Tag_02 \
  --devices ../../tag_data/tag_data/tag_02\ devices.txt \
  --tags ../../tag_data/tag_data/tags02.json
uv run python manage.py materialize_sim_field_config --provider Tag_02
uv run python manage.py configure_field_ignition --tag-provider default --tag-folder FieldAgent
uv run python manage.py flux_field_supervisor --runtime-dir ../../.runtime/field-agent
```

Start/stop/status wrappers:

```bash
./scripts/flux-service-start.sh
./scripts/flux-service-stop.sh
./scripts/flux-service-status.sh
./scripts/flux-service-logs.sh
```

The desktop app launcher entries are:

- `Flux Stack Start`
- `Flux Stack Stop`

## Dashboard

The main page is an operator console, not a branding page.

It shows:

- runtime tag readiness
- latest read freshness
- FieldAgent port/config state
- Live Ignition Bridge state
- stale tag recovery actions

The stale recovery action performs one Fluxy `read_blocking([...])` block read for the stale set, then updates `LatestTagValue` and `TagSample`. Avoid per-tag read loops.

The Live Ignition Bridge configuration is stored in Django as `dashboard.IgnitionBridgeConfig`.

Token behavior:

- token is never rendered back into HTML
- blank token input keeps the existing token
- `Clear stored token` explicitly clears it
- `Test connection` calls Fluxy `util_get_version`

## Health

Run:

```bash
flux doctor
```

The health check currently covers:

- user systemd service state
- Flux web response
- FieldAgent OPC UA port
- runtime tag count, stale count, bad quality count, and latest read age
- Live Ignition Bridge token/config and live Ignition version probe
- historian datasource type/status
- QuestDB Trace data-plane reachability, `trace_points` count, and latest timestamp
- Ignition Gateway and Fluxy WebDev readiness

Architecture boundary:

- `scripts/flux` is the operator CLI and process-orchestration boundary.
- `dashboard.management.commands.flux_doctor_state` emits Django/app health as JSON.
- `dashboard.services` owns runtime/bridge state calculations used by both the dashboard and doctor-state command.
- Fluxy owns Gateway and datasource probes.
- `Flux.serve` owns FieldAgent adapter supervision; FieldAgent is the OPC UA process that services materialized `Flux.sim` devices.
- Django request handlers should not directly own long-lived process supervision.

## Trace Worker

Flux Trace has a dedicated `flux.serve` worker command for keeping local rolling-history cache current from Ignition/Fluxy.

Run one generic cache sync:

```bash
cd web/Flux
uv run python manage.py flux_trace_worker --once
```

Run one navigation-well live cycle for the first ten seeded wells:

```bash
cd web/Flux
uv run python manage.py flux_trace_worker --once --nav-well-live --nav-well-limit 10
```

Run continuously every minute:

```bash
cd web/Flux
uv run python manage.py flux_trace_worker --nav-well-live --nav-well-limit 10 --interval 60
```

The dedicated Trace worker performs service/process work. Trace views should only read local cache payloads.

## QuestDB Trace Data Plane

Navigation-well Trace uses QuestDB as its only HTTP payload data plane. The Postgres/local ORM cache remains the control plane and source/export staging area; browser payloads are served from QuestDB.

Start QuestDB directly:

```bash
scripts/questdb-start.sh
```

On Windows:

```powershell
scripts\questdb-start.ps1
```

The scripts download QuestDB `9.3.5` into `.runtime/questdb-dist` when missing and store data under `.runtime/questdb-data`. Override with `QUESTDB_VERSION`, `FLUX_QUESTDB_DIST`, or `FLUX_QUESTDB_DATA` if needed.

Export current nav-well Trace cache rows into QuestDB:

```bash
cd web/Flux
uv run python manage.py sync_trace_questdb --limit 10 --replace
```

The active nav-well payload endpoint is:

```text
http://localhost:8000/trace/wells/payload/?set=1&window_minutes=10080&step_minutes=7
```

Known good output ends with:

```text
Flux is healthy.
```

## Windows

Windows foreground startup exists:

```cmd
scripts\flux-start.cmd
```

Windows background service management is not wired yet. The repo contains placeholder `.cmd` service scripts that fail clearly instead of pretending Windows background service support exists.

## Optional Browser Tests

Trace interaction tests use Playwright and are gated behind `FLUX_PLAYWRIGHT=1`.

```bash
cd web/Flux
uv run python -m playwright install chromium
FLUX_PLAYWRIGHT=1 DATABASE_URL= uv run pytest src/flux/trace/test_e2e_playwright.py -q
```
