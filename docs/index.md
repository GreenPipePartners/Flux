# Flux Docs

Flux is performance-first Ignition companion tooling for fast local operations views, simulation, tracing, and live-to-sim workflows.

The docs are organized around how Flux is used:

- **Operator Guide**: local service, CLI, dashboard, and health workflows.
- **Architecture**: system boundaries and ownership.
- **Apps**: dashboard, Live, Trace, Serve, Sim, and Opt behavior.
- **Runbooks**: repeatable workflows for local operation and recovery.
- **Reference**: durable formats such as Live card context payloads.

## Local URLs

```text
Flux web UI:      http://localhost:8000/
Docs server:      http://localhost:8001/
Live view:        http://localhost:8000/live/
Trace:            http://localhost:8000/trace/
Ignition Gateway: http://localhost:8088/web/home
Fluxy bridge:     http://localhost:8088/system/webdev/flux
```

## Local Docs Commands

```bash
flux docs serve
flux docs open
flux docs build
```

## Documentation Contract

Docs should preserve Flux architecture. If a page mixes operator workflow, implementation detail, and product intent, split it before it becomes a junk drawer.
