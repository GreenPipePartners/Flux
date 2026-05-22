# Serve

Flux.serve owns worker/service orchestration and supervised FieldAgent process control.

Flux.serve is the local service platform: it keeps a catalog of expected Flux services, discovers dynamic runtime services, probes them on a cadence, and stores the latest observed service health for UI surfaces.

## Boundaries

- Request handlers enqueue approved commands.
- Supervisors and workers claim and execute commands.
- Heartbeats describe supervisor/worker health, not necessarily individual endpoint state.
- `flux_serve_monitor` writes `ServeServiceSnapshot` rows as the UI source of truth for observed service health.

The target FieldAgent path is supervised mode: one FieldAgent adapter process per enabled `FieldEndpoint` / OPC UA server.

## Service Visibility

`Flux.serve` groups service health by domain-qualified service keys:

- `Flux.web.server`
- `Flux.web.docs`
- `Flux.plane.qdb`
- `Flux.serve.monitor`
- `Flux.serve.field-supervisor`
- `Flux.serve.field-agent:<endpoint>`
- `Flux.live.fluxolot-sampler`
- `Flux.opt.sampler`
- `Flux.trace.worker`

Snapshots are durable observations. Page rendering should read stored snapshots instead of probing sockets or processes during the request.

## Heartbeats Vs Observed Health

- Heartbeats are raw self-reports from running processes.
- Observed service health is the consolidated platform view produced by `flux_serve_monitor`.
- A service can have no heartbeat and still be monitored through HTTP, TCP, stored bridge tests, or dynamic model discovery.
- Snapshots older than the stale threshold are treated as stale by UI selectors even if the stored row was last healthy.
