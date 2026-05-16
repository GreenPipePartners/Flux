# Flux Field Service Control Pick-Up Plan

## Goal

Build a human-interfaceable way to manage Flux Field from the web app:

- Make and edit simulated field endpoints, devices, and tags.
- Start, stop, and restart Flux Field services.
- Show clear running/stale/error state from the web UI.

## Current State

- `flux.field` already models field configuration:
  - `FieldEndpoint`
  - `FieldDevice`
  - `FieldTag`
  - `FieldNode`
  - `FieldAgentHeartbeat`
- Django admin is currently the first-class config UI for endpoints/devices/tags.
- `/field/` is read-only status/config review.
- `/sim/field-config.json` exports enabled endpoint/device/tag config for `Flux.FieldAgent`.
- `export_field_config` writes the same payload to a JSON file.
- `.NET Flux.FieldAgent` can read config from `/sim/field-config.json` or a config file.
- `flux.serve` exists but is still skeletal:
  - `ServeHeartbeat`
  - `ServeCommand`
  - `/serve/` read-only page
  - `flux_worker` heartbeat loop only

## Current Gaps

- No web button/API starts `Flux.FieldAgent`.
- No web button/API stops `Flux.FieldAgent`.
- No real service supervision from Django yet.
- No command executor consumes `ServeCommand` rows.
- `FieldAgentHeartbeat` exists but the .NET agent does not post heartbeats yet.
- `FieldEndpoint.status` is not authoritative.
- `Flux.FieldAgent` appears to load config once at startup, so config changes likely require restart.

## Manual Commands Today

Run Django from `web/Flux`:

```bash
uv run python manage.py runserver 0.0.0.0:8000
```

Run FieldAgent from repo root:

```bash
dotnet run --project field/Flux.FieldAgent/Flux.FieldAgent.csproj --FluxField:ConfigUrl=http://localhost:8000/sim/field-config.json
```

Run the demo runtime reader from `web/Flux`:

```bash
uv run python manage.py run_sim_demo
```

## Architecture Decision

Do not let normal Django web requests directly own long-lived child processes.

Use this boundary instead:

- `flux.field`: endpoint/device/tag configuration and field-facing status.
- `flux.serve`: service lifecycle, approved commands, process wrappers, and heartbeats.
- `flux_worker`: trusted local process that consumes `ServeCommand` rows and executes approved service actions.

This keeps the web app as the human interface and command source, while a worker handles process supervision.

## Smallest Good Build

1. Keep Django admin for detailed endpoint/device/tag CRUD for now.
2. Improve `/field/` into the human Field control panel.
3. Add Field service buttons:
   - Start FieldAgent
   - Stop FieldAgent
   - Restart FieldAgent
   - Start Demo Reader
   - Stop Demo Reader
   - Restart Demo Reader
4. Button posts should create `ServeCommand` rows, not directly spawn processes.
5. Extend `flux_worker` to claim and execute requested commands from a hard-coded approved registry.
6. Registry commands should initially support:
   - FieldAgent via `dotnet run --project field/Flux.FieldAgent/Flux.FieldAgent.csproj --FluxField:ConfigUrl=http://localhost:8000/sim/field-config.json`
   - Demo reader via `uv run python manage.py run_sim_demo`
7. Persist enough process state to stop/restart services safely.
8. Show running/stale/error status on `/field/` from heartbeat/process state.
9. Add tests around command creation and command execution dispatch, avoiding real long-running processes in tests.

## Likely Files To Touch

- `web/Flux/src/flux/field/views.py`
- `web/Flux/src/flux/field/urls.py`
- `web/Flux/src/templates/field/index.html`
- `web/Flux/src/flux/serve/models.py`
- `web/Flux/src/flux/serve/management/commands/flux_worker.py`
- `web/Flux/src/flux/serve/views.py`
- `web/Flux/src/templates/serve/index.html`
- `web/Flux/src/flux/field/tests.py`
- `web/Flux/src/flux/serve/tests.py`

## Follow-On Improvement

After the local worker path works, decide whether deployed service control should map to:

- systemd units on Linux
- Windows Services on Windows
- local subprocess supervision for dev only

The current development path should favor subprocess supervision first because it is fastest to validate.
