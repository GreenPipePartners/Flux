# Opt

Flux Opt owns browse/read planning, demand leases, and cold-spot strategy.

The purpose is performance: reduce Ignition IO by making demand explicit and avoiding dynamic/circular browser-driven read loops.

## Runtime Sampling Boundary

Flux.opt is the planning layer for runtime reads:

- Select due runtime tags.
- Prioritize active demand.
- Perform consolidated Fluxy block reads.
- Persist `LatestTagValue` and append `TagSample` rows.

Current reality:

- `sample_due_runtime_tags()` selects enabled tags due by schedule or active demand.
- `sample_runtime_tags()` performs one `read_blocking([...])` call for the selected batch.
- `RuntimeDemand` and `OptimizationLease` can mark tags hot.
- `RefreshLane` stores hot/warm/cold interval settings, but the active sampler does not yet fully negotiate by lanes.

Target contract:

- Hot tags are active cards/charts or explicit demand and should be read fastest.
- Warm tags are recently relevant interface tags.
- Cold tags are background health or inventory tags.
- The browser never creates Ignition IO loops; it can only declare demand and render cached state.
