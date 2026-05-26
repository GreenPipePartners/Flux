# Trace

Flux Trace owns historical-time context: profiles, signals, runtime sample history, and demand signals for active trend surfaces.

Trace is not a direct Ignition read surface. It should use local runtime samples, chart cache rows, and explicit demand signals so external IO stays centralized in Flux.serve workers.

## Operator Surfaces

- `/chart/` surfaces trend views backed by Trace profiles and Flux.chart rendering.
- `/chart/demand/` records active profile demand so related runtime tags can be sampled hot by the worker path.
- Fluxolot proof charts live under `/chart/fluxolot/`, `/chart/fluxolot-sir/`, and `/chart/fluxolot-missus/`.

## Service Contract

Trace demand should flow through Flux.opt and Flux.serve:

```text
active trace profile -> RuntimeDemand -> due runtime tags -> Fluxy block read -> LatestTagValue + TagSample
```

If trace data is old but quality is good, inspect the relevant sampling worker, demand lease state, and cache worker before blaming the browser page.

## Related Docs

- `trace-architecture.md`
- `charts-architecture.md`
- `apps/chart.md`
- `apps/opt.md`
