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

## Django Role

Django is the UX and configurator layer:

- `flux.live`: lightweight DB-backed visualization.
- `flux.trace`: power-user charting and historical exploration.
- `flux.opt`: tag browse optimizer and runtime read planning.
- `flux.serve`: worker/service orchestration UX and adapters.
- `flux.field`: FieldAgent configuration UX and status adapters.
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

## Configurator Contract

The configurator coordinates three execution domains:

- `Flux.sim`: owns desired simulated environment and generated tag/server artifacts.
- `Flux.field`: owns OPC UA server runtime config and process lifecycle.
- `Flux.serve`: owns worker process plans and health/supervision.

The configurator should persist intent and show status. It should call package APIs or CLIs, not duplicate their internals.
