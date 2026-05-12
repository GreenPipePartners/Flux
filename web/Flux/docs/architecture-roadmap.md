# Flux Architecture Roadmap

Flux is a Django/HTMX modular monolith for on-prem Ignition companion services. Fluxy remains the Ignition API wrapper; Flux decides what to cache, optimize, display, and operate.

## Platform Boundaries

```text
fluxy
- Ignition WebDev/API wrapper
- transport contracts
- gateway deployment helpers

flux.serve
- service lifecycle and platform operations
- Windows .NET wrapper coordination
- Linux systemd coordination
- service heartbeats and approved commands

flux.opt
- tag browse/read optimization
- refresh lanes
- queue and lease policy
- cold-spot and lazy refresh strategy

flux.sim
- configured simulated tags
- scheduled live value writes
- historical backfill for test data

flux.field
- simulated field-device exposure
- OPC UA endpoint and node mapping
- .NET FieldAgent configuration/status
- C# OPC UA server source at repository-level `field/`

flux.live
- current-state HTMX display
- latest tag snapshots
- stale/quality visibility

flux.trace
- historical HTMX display
- samples, traces, trends, and replay
```

## Deployment Shape

Windows:

```text
Windows Service (.NET Flux Agent)
  -> Python Flux worker
      -> flux.opt
      -> fluxy
```

Linux:

```text
systemd
  -> flux-web.service
  -> flux-worker.service
```

The Linux path can run Python directly under systemd first. The Windows path uses a .NET Worker Service because that is the Microsoft-native service wrapper customers expect.

## Build Phases

1. Establish namespaces: `flux.serve`, `flux.opt`, `flux.live`, `flux.trace`.
2. Keep existing `runtime` models stable while `flux.live` and `flux.trace` wrap them.
3. Add service heartbeat and command tables for platform-neutral management.
4. Add optimization lane, browse node, optimized path, and lease tables.
5. Implement `flux_worker` as the first long-running worker entrypoint.
6. Seed default opt lanes: hot 10s, warm 30s, cool 60s, lazy opportunistic.
7. Connect `flux.opt` to Fluxy browse/read calls with measured durations and backoff.
8. Add HTMX panels for service status, queue pressure, lane health, and stale values.
9. Harden Windows installation through `serve/windows/Flux.Agent`.
10. Harden Linux installation through `serve/linux/systemd` and later RPM packaging.

## Current Scaffold

- Django apps are mounted at `/serve/`, `/opt/`, `/live/`, and `/trace/`.
- Flux Sim is mounted at `/sim/` for simulated tag configuration and backfill visibility.
- Flux Field is mounted at `/field/` for OPC UA endpoint and node mapping visibility.
- The OPC UA simulation server project lives at repository-level `field/Flux.FieldAgent/`.
- `flux.serve` owns `ServeHeartbeat` and `ServeCommand`.
- `flux.opt` owns `RefreshLane`, `OptimizedTagPath`, `BrowseNode`, and `OptimizationLease`.
- `flux.live` currently reads existing `runtime.RuntimeTag` and latest values.
- `flux.trace` currently reads existing `runtime.TagSample` rows.
- Wrapper assets live outside Django under repository-level `serve/`.
