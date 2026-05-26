# Flux Trace Architecture

Flux Trace is the historical-time persistence layer behind Flux.chart and the companion to Flux.spot current-state views.

Trace should make time-series context fast without creating browser-driven Ignition IO loops. Views and payload endpoints read local Flux cache or persisted runtime samples. Workers and explicit service jobs own external historian IO.

## Boundaries

- `TraceProfile` defines an operator-facing trend surface.
- `TraceSignal` connects a profile to `RuntimeTag` identity and rendering metadata.
- `TagSample` is legacy runtime sample history from live sampling paths.
- `plane.sample` is the chart-optimized rolling-history read model.
- `Flux.chart` renders trend payloads and browser interaction behavior.
- `Flux.serve` workers keep cache surfaces current.
- `Flux.opt` demand can mark profile signals hot while a trace surface is active.

Trace views should not perform per-tag Ignition reads. If a trace surface needs fresher live context, it should declare demand and let Flux.serve/Flux.opt sampling paths perform consolidated block reads.

## Demand Path

Trace profile demand is explicit:

```text
browser interaction -> /chart/demand/ -> RuntimeDemand -> sampler due selection -> block read -> LatestTagValue + TagSample
```

The page and payload GET routes intentionally do not write demand by themselves. Demand should be a deliberate active-view signal, not incidental read-path side effect.

## Related Docs

- `charts-architecture.md` describes chart cache, uPlot payload, and browser-performance boundaries.
- `apps/chart.md` describes operator chart surfaces.
- `apps/opt.md` describes demand leases and read planning.
- `apps/serve.md` describes worker/service orchestration.
