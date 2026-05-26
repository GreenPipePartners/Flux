# Live Compatibility

Flux.spot is the canonical current-state card surface. This page preserves the historical Flux Live wording for operators following older links.

Spot cards are intended to be small, copyable context objects:

- **Card definition**: scope, group, kind, title, and point address space.
- **Snapshot**: current values, units, quality, stale state, and read time.

## Copy Context

The top-left card marker copies card context:

- First click: compact Markdown table for quick handoff.
- Second click: LLM export with card identity, address space, snapshot, JSON, and docs link.

See `spot-card-context.md`. The older `live-card-context.md` page remains as a compatibility explanation.

## Runtime Freshness Contract

Flux.spot does **not** bind the browser directly to Ignition tags. A Spot page reads cached Flux rows:

```text
Flux.serve worker -> Flux.opt sampler -> LatestTagValue + TagSample -> Flux.spot cards
```

Current reality:

- Spot cards and the dashboard Overall banner read `LatestTagValue` rows.
- Stale means no fresh `LatestTagValue.read_at` exists inside the stale threshold, even if the last quality was `Good`.
- The dashboard stale recovery button performs one consolidated Fluxy block read for the selected stale tags.
- The Fluxolot proof path has a dedicated sampler service, `fluxolot-live-sampler`, started by `flux start`.
- The general interface-health sampler contract is still incomplete: the service exists as `flux_sampling_worker`, but dashboard health should not depend on manual page refreshes or per-request reads.

Target contract:

- `Flux.serve` supervises a required sampler when interface runtime tags exist.
- `Flux.opt` owns due-tag selection, hot/warm/cold planning, demand leases, and block reads.
- `Flux.spot` owns freshness semantics and presentation of cached values.
- `Flux.web` may HTMX-poll a small cached-health fragment, but browser polling must not perform Ignition reads.

## Hot, Warm, And Cold Reads

Flux has the model pieces for a tiered read contract:

- `RuntimeDemand` marks currently visible or requested tags as hot.
- `OptimizationLease` records short-lived explicit demand.
- `RefreshLane` stores hot/warm/cold intervals and limits.
- `RuntimeSchedulerConfig` stores scheduler defaults and balancer settings.

Current gap: `RefreshLane` is configurable from the dashboard, but it is not yet the full scheduler used by `flux_sampling_worker`. Treat hot/warm/cold lanes as target contract until the sampler uses them directly.

## Operator Checks

When Spot shows `Good` and `Stale`, check sampler liveness before blaming the card:

```bash
flux status
flux doctor
flux logs
```

For Fluxolot specifically, the sampler command is:

```bash
uv run python web/Flux/manage.py flux_sampling_worker --profile fluxolot-fishtank
```

If the sampler is stale or absent, page reloads may only reveal old cached state. The fix is to restore the worker path, not to add browser-driven Ignition IO.
