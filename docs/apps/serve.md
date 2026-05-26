# Serve

Flux.serve owns worker/service orchestration and supervised FieldAgent process control.

Flux.serve is the local service platform: it keeps a catalog of expected Flux services, discovers dynamic runtime services, probes them on a cadence, and stores the latest observed service health for UI surfaces.

## Boundaries

- Request handlers enqueue approved commands.
- Supervisors and workers claim and execute commands.
- Heartbeats describe supervisor/worker health, not necessarily individual endpoint state.
- `flux_serve_monitor` writes `ServeServiceSnapshot` rows as the UI source of truth for observed service health.

The target FieldAgent path is supervised mode: one FieldAgent adapter process per enabled `sim.Endpoint` / OPC UA server.

## Service Visibility

`Flux.serve` groups service health by domain-qualified service keys:

- `Flux.web.server`
- `Flux.web.docs`
- `Flux.plane.qdb`
- `Flux.serve.monitor`
- `Flux.serve.field-supervisor`
- `Flux.serve.field-agent:<endpoint>`
- `Flux.spot.fluxolot-sampler`
- `Flux.opt.sampler`
- `Flux.chart.worker`

Snapshots are durable observations. Page rendering should read stored snapshots instead of probing sockets or processes during the request.

## Heartbeats Vs Observed Health

- Heartbeats are raw self-reports from running processes.
- Observed service health is the consolidated platform view produced by `flux_serve_monitor`.
- A service can have no heartbeat and still be monitored through HTTP, TCP, stored bridge tests, or dynamic model discovery.
- Snapshots older than the stale threshold are treated as stale by UI selectors even if the stored row was last healthy.

## FieldAgent Runtime Truth

Do not treat `sim.Endpoint.status == running` as complete runtime truth by itself.

Current reality:

- `flux_field_supervisor` starts one FieldAgent process per enabled runtime endpoint in supervised mode.
- The supervisor writes `SimAgentHeartbeat.process_id` and updates `sim.Endpoint.status` when it starts a process.
- FieldAgent endpoint URLs are deterministic: the supervisor uses the base port plus `sim.Endpoint.id`.
- `flux_serve_monitor` can mark FieldAgent snapshots healthy, missing, stale, or error based on heartbeat freshness.
- Some dashboard rows may still display `running` from stored endpoint status without requiring fresh heartbeat evidence.

Target contract for a user-facing `running` label:

```text
  + sim.Endpoint.status
  + fresh serve.SimAgentHeartbeat
  + process_id
  + endpoint URL / port
  + fresh ServeServiceSnapshot
  + optional OS/TCP probe when available
  = runtime truth
```

If the heartbeat or snapshot is stale, display `stale` or `last reported running`, not plain `running`. The dashboard should expose PID, port, endpoint URL, heartbeat age, and observed state when claiming an OPC endpoint is online.

## Interface Sampler Responsibility

Interface runtime health is also a Flux.serve responsibility. A required sampler should be supervised when interface runtime tags exist. The sampler performs block reads through Flux.opt and writes `LatestTagValue`/`TagSample`; dashboard and Live pages only render cached results.
