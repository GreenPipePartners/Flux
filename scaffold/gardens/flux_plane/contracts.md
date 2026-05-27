# Contracts: flux_plane

## Contract: Series Identity

- Owner: Flux.plane
- Statement: Plane series identifies data-plane acquisition/storage streams and must not become a duplicate physical tag identity competing with `base.tag`.
- Evidence target: `web/Flux/src/flux/plane/models.py`, `web/Flux/src/flux/base/models.py`
- Failure handoff: Architect if ownership is unclear; Build if code violates an accepted contract.

## Contract: Latest Is Cached State

- Owner: Flux.plane with producer supervision by Flux.serve/Flux.opt
- Statement: Plane latest rows are persisted cached state produced by workers/services; web requests should consume them, not create runtime truth through direct external IO.
- Evidence target: `web/Flux/src/flux/plane/services.py`, `web/Flux/src/flux/live/selectors.py`
- Failure handoff: Flux.serve/Flux.opt for producer gaps; Flux.spot/web for request-path misuse.

## Contract: Bounded Windows

- Owner: Flux.plane
- Statement: Window stats need explicit names, bounds, and timezone semantics.
- Evidence target: `web/Flux/src/flux/plane/models.py`, `web/Flux/src/flux/plane/services.py`
- Failure handoff: Architect for semantic gap; Build for implementation drift.
