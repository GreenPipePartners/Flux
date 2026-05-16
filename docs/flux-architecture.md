# Flux Architecture

Flux is the application boundary around Ignition-facing tooling, runtime data capture, and development environment simulation.

## System Shape

```text
Ignition Production -> WebDev -> fluxy -> Flux.serve -> Flux.opt -> Flux.live / Flux.trace / Flux.web
Ignition Development -> WebDev -> fluxy -> Flux.sim <-> Flux.field
Flux.web -> Configurator -> Flux.field / Flux.sim / Flux.serve
```

## Boundaries

- `fluxy/`: Python-for-Ignition client, WebDev deployment tooling, and Ignition expression/tag export utilities.
- `field/`: FieldAgent OPC UA simulator runtime. This is the real `Flux.field` execution core.
- `sim/`: standalone `Flux.sim` core for importing Ignition tag exports, reconstructing provider models, flattening OPC requests, and generating simulation/FieldAgent configuration.
- `web/Flux/`: Django/HTMX UX, admin, status, configuration, and worker-control surface. It should adapt core packages, not own their core logic.
- `scripts/flux`: operator CLI for local service control, health checks, and managed Ignition dev-cell commands.

## Django Role

Django is the UX and configurator layer:

- `flux.live`: lightweight DB-backed visualization.
- `flux.trace`: power-user charting, historical exploration, and live trace trials over recorded runtime samples.
- `flux.opt`: tag browse optimizer and runtime read planning.
- `flux.serve`: worker/service orchestration UX and adapters.
- `flux.base`: persistent datastore, including runtime and FieldAgent configuration objects.
- `flux.sim`: simulation UX and adapters over root `sim/`.

Core import, flattening, expression, server generation, and OPC UA simulation logic should stay outside Django.

## Simulation Path

The development replication path is:

1. Import an Ignition tag provider export into a standalone `sim` database.
2. Reconstruct the provider tree and UDT structures.
3. Use `fluxy.ignition_expression` to resolve UDT parameter bindings and flatten OPC requests.
4. Generate a `Flux.field` FieldAgent configuration.
5. Start FieldAgent as the OPC UA simulation server.
6. Use `fluxy` through WebDev to configure the Ignition development gateway and inject matching tags.
7. Use `Flux.serve` to supervise long-running workers and status.

## Production Path

The production path is:

1. `Flux.serve` runs worker servicing against production Ignition through `fluxy` and WebDev.
2. `Flux.opt` controls browse/read planning and reduces inefficient tag IO.
3. Runtime values are persisted into Flux runtime storage.
4. `Flux.live`, `Flux.trace`, and `Flux.web` render from Flux storage instead of causing browser-driven Ignition tag IO.

`Flux.trace` reads `runtime.TagSample` and renders uPlot charts from stored samples. The historical trace supports pinned chart markers, a copied Markdown marker-value table, and prompt-based annotations. The live trace polls new samples and only follows the newest right edge when the user is already viewing that edge; panning back preserves the inspected viewport while new samples continue to merge. Trace JavaScript architecture is documented in `docs/trace-architecture.md`.

Live-to-sim extraction is documented in `docs/live-extraction.md`. The current trial stays at the Fluxy public API boundary for tag/config/history reads and writes. Raw historian deletion is intentionally deferred to database-specific cleanup adapters because Ignition does not expose a public delete-data-points API.

## Local Service Boundary

Local development runtime is owned by a user systemd service:

```text
flux-stack.service -> scripts/flux-start.sh -> Django + FieldAgent + demo reader
```

The CLI and desktop launchers start/stop the service. Django should not directly own long-lived OS processes from request handlers.

See `docs/operator-guide.md`.

## Health Utility Boundary

Health checks are split by responsibility:

- `scripts/flux`: operator-facing CLI, shell/service/process checks, output formatting, and fix suggestions.
- `dashboard.management.commands.flux_doctor_state`: JSON app-health bridge for the CLI.
- `dashboard.services`: runtime readiness, Live Ignition Bridge config, stale-tag classification, and block-read recovery.
- `fluxy`: Ignition Gateway, WebDev, and datasource probing.

This keeps `flux doctor` useful without turning the CLI into an untestable copy of Django business logic.

## Configurator Contract

The configurator coordinates three execution domains:

- `Flux.sim`: owns desired simulated environment and generated tag/server artifacts.
- `Flux.field`: owns OPC UA server runtime config and process lifecycle.
- `Flux.serve`: owns worker process plans and health/supervision.

The configurator should persist intent and show status. It should call package APIs or CLIs, not duplicate their internals.
