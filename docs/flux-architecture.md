# Flux Architecture

Flux is the application boundary around Ignition-facing tooling, runtime data capture, and development environment simulation.

## System Shape

```text
Ignition Production -> WebDev -> fluxy -> Flux.serve -> Flux.opt -> Flux.spot / Flux.chart / Flux.web
Ignition Development -> WebDev -> fluxy -> Flux.sim -> Flux.base -> Flux.serve -> FieldAgent processes
Flux.web -> Configurator -> Flux.sim / Flux.base / Flux.serve
Flux.Deep -> OpenPLC runtime artifacts
```

## Boundaries

- Flux is Linux-exclusive runtime software. Supported operation assumes Linux,
  bash, systemd/user-systemd service ownership, Gunicorn for Django serving, and
  Linux-compatible OpenPLC/FieldAgent/QuestDB process control. Windows, PowerShell,
  `.cmd` launchers, Windows Services, and Waitress are intentionally unsupported.
- `fluxy/`: Python-for-Ignition client, WebDev deployment tooling, and Ignition expression/tag export utilities.
- `field/`: FieldAgent OPC UA adapter executable. It is not a Flux domain owner; `Flux.serve` starts one FieldAgent adapter process for each materialized runtime device.
- `sim/`: standalone `Flux.sim` core for importing Ignition tag exports, reconstructing provider models, flattening OPC requests, and generating simulation/FieldAgent configuration.
- `deep/`: isolated `Flux.Deep` core for OpenPLC-backed PLC emulation experiments. It starts with Logix L5X source intent and OpenPLC IEC 61131-3 runtime targets.
- `web/Flux/`: Django/HTMX UX, admin, status, configuration, and worker-control surface. It should adapt core packages, not own their core logic.
- `scripts/flux`: operator CLI for local service control, health checks, and managed Ignition dev-cell commands.

## Django Role

Django is the UX and configurator layer:

- `flux.spot`: lightweight DB-backed current-state visualization.
- `flux.chart`: power-user charting, historical exploration, and live trace trials over recorded runtime samples.
- `flux.trace`: chart/history persistence models backing Flux.chart until a planned schema migration.
- `flux.opt`: tag browse optimizer and runtime read planning.
- `flux.serve`: worker/service orchestration UX and adapters.
- `flux.base`: persistent datastore, including simulation catalog rows, materialized runtime device/tag config, and FieldAgent endpoint config.
- `flux.sim`: simulation UX and adapters over root `sim/`.

Core import, flattening, expression, server generation, and OPC UA simulation logic should stay outside Django.

## Flux.Deep Path

Flux.Deep is intentionally isolated from the Ignition-facing simulation path:

1. Keep Logix L5X or related PLC source artifacts as source intent.
2. Translate or target OpenPLC-compatible IEC 61131-3 artifacts for execution.
3. Use OpenPLC as the backend runtime for PLC emulation trials.
4. Add bridges back into Flux.web or Flux.serve only after the runtime adapter contract is proven.

The seed workspace is `deep/examples/hello_world/`. It includes a Logix ladder L5X
file and an OpenPLC Structured Text target that alternates `DisplayText` between
`hello` and `world` on one second cycles.

## Simulation Path

The development replication path is:

1. Import an Ignition tag provider export into a standalone `sim` database.
2. Reconstruct the provider tree and UDT structures.
3. Use `fluxy.ignition_expression` to resolve UDT parameter bindings and flatten OPC requests.
4. Store the desired simulated devices and tags as `Flux.sim` catalog configuration.
5. Materialize enabled simulated devices and tags into `Flux.base` runtime FieldAgent endpoint/device/tag rows.
6. Use `Flux.serve` to supervise one FieldAgent OPC UA adapter process per enabled materialized runtime device.
7. Use `fluxy` through WebDev to configure the Ignition development gateway with matching OPC UA connections and tags.

## Production Path

The production path is:

1. `Flux.serve` runs worker servicing against production Ignition through `fluxy` and WebDev.
2. `Flux.opt` controls browse/read planning and reduces inefficient tag IO.
3. Runtime values are persisted into Flux runtime storage.
4. `Flux.spot`, `Flux.chart`, and `Flux.web` render from Flux storage instead of causing browser-driven Ignition tag IO.

`Flux.chart` reads `runtime.TagSample` and renders uPlot charts from stored samples. The historical chart supports pinned chart markers, a copied Markdown marker-value table, and prompt-based annotations. The streaming chart polls new samples and only follows the newest right edge when the user is already viewing that edge; panning back preserves the inspected viewport while new samples continue to merge. Chart JavaScript architecture is documented in `docs/charts-architecture.md`.

Live-to-sim extraction is documented in `docs/live-extraction.md`. The current trial stays at the Fluxy public API boundary for tag/config/history reads and writes. Raw historian deletion is intentionally deferred to database-specific cleanup adapters because Ignition does not expose a public delete-data-points API.

## Runtime Health Contract

Flux runtime health is a cached-state contract, not a browser read loop.

```text
Flux.serve worker -> Flux.opt block read -> LatestTagValue / TagSample -> Flux.spot / Dashboard
```

Ownership:

- `Flux.serve` supervises long-running samplers and writes heartbeats/snapshots.
- `Flux.opt` chooses due tags, honors active demand, performs block reads, and writes runtime samples.
- `Flux.spot` defines freshness and current-state presentation.
- `Flux.web` renders cached state and may poll small cached fragments.

Current gap: the dashboard can refresh selected stale tags from a request path, and the Fluxolot sampler is explicitly started by `flux start`, but the general interface-health sampler should be promoted to a required service when interface runtime tags exist.

Target contract: page reloads or HTMX polls may update what the user sees, but they must not be the mechanism that makes runtime health fresh.

## OPC Runtime Truth Contract

FieldAgent endpoint rows need composed evidence before the UI claims they are running.

Minimum evidence:

- desired endpoint state from `FieldEndpoint`
- fresh `FieldAgentHeartbeat`
- `process_id`
- endpoint URL and derived/listening port
- fresh `ServeServiceSnapshot`
- optional OS/TCP probe from the service layer

`FieldEndpoint.status == running` alone means “last persisted endpoint state,” not proven current process truth. If heartbeat or snapshot evidence is stale, UI surfaces should say `stale` or `last reported running` and show the reason.

## Local Service Boundary

Local development runtime is owned by a Linux user systemd service:

```text
flux-stack.service -> scripts/flux-start.sh -> Django + FieldAgent + Fluxolot sampler
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

## FieldAgent Runtime Adapter Contract

FieldAgent is the concrete OPC UA runtime adapter below the Flux architecture, not a separate Flux module with domain ownership.

- `Flux.sim` owns device and tag domain configuration: provider import, reconstructed trees, UDT binding flattening, simulated device identity, and simulated tag behavior intent.
- `Flux.base` persists both the desired catalog state and the materialized runtime endpoint/device/tag state that can be supervised.
- `Flux.serve` owns process supervision and starts one FieldAgent process for each enabled materialized runtime device.
- FieldAgent loads the generated per-device runtime config and serves OPC UA for that one device process.
- `Flux.web` configures and displays the catalog/materialization/supervision state; it should not directly own long-lived FieldAgent processes from request handlers.
- `fluxy` configures Ignition through WebDev by creating OPC UA connections and matching Ignition tags that point at the supervised FieldAgent endpoints.

This resolves the earlier implicit `Flux.field` boundary: the thing running under `Flux.serve` is FieldAgent as an adapter process servicing `Flux.sim.device`, while `Flux.sim` remains the device/tag domain owner.

Current limitations:

- `FLUX_FIELD_AGENT_MODE=legacy` still exists and runs one FieldAgent from `web/Flux/field/field-config.json`; it is a compatibility/operator path, not the target architecture.
- Supervised mode writes runtime configs under `.runtime/field-agent`, but process lifecycle is still local-development oriented under `flux-stack.service`.
- Device-level delay metadata is materialized, but the current C# FieldAgent runtime does not yet apply request-level delay behavior.
- Full-provider simulations can generate large FieldAgent/Ignition configurations; use small closed-loop trials before scaling to the full ACM02 provider.
- Ignition cleanup is generated-folder and generated-connection oriented; broad historical or raw gateway cleanup remains adapter-specific and intentionally outside the simulation boundary.

Next tests:

- Closed-loop device lifecycle: create a test-specific `Flux.sim.device`, materialize it, start the supervised FieldAgent process, configure Ignition through `fluxy`, read a test tag, confirm changing values, delete the Ignition tag/folder, verify gone, then remove the runtime device.
- Multi-device supervision: materialize two enabled devices and verify `Flux.serve` starts two distinct FieldAgent processes with distinct endpoint configs.
- Restart recovery: restart `flux-stack.service` in supervised mode and verify materialized enabled devices are restored without manual config regeneration.
- Device behavior: prove `slow_network` once FieldAgent consumes device delay metadata.
- Scale smoke: run a limited preserved-tree ACM02 trial before attempting the full `tags02.json` configuration.

## Configurator Contract

The configurator coordinates three execution domains:

- `Flux.sim`: owns desired simulated environment, device/tag catalog configuration, and generated tag artifacts.
- `Flux.base`: owns persistence for desired catalog state and materialized runtime endpoint/device/tag configuration.
- `Flux.serve`: owns worker process plans, FieldAgent adapter supervision, and health/status.

The configurator should persist intent and show status. It should call package APIs or CLIs, not duplicate their internals.
