# Contracts: current_state_display__plane__spot__web

## Contract: Cached State Display

- Owner chain: Flux.plane -> Flux.spot/live -> Flux.web
- Statement: Current-state display consumes cached Plane/latest state. It must not perform Ignition reads or create sampler truth inside browser/request display refresh.
- Failure handoff: Flux.web if request path owns IO; Flux.serve/opt if producer freshness is missing; Flux.plane if cached latest semantics are unclear.

## Contract: Linkage Visibility

- Owner chain: Flux.spot/live -> Flux.plane
- Statement: A Spot point linked to Plane series should prefer Plane current-state evidence. Missing linkage or missing latest state should be visible as stale/missing evidence, not hidden by an ambiguous fallback.
- Failure handoff: Flux.spot/live selector owner first, then Architect if compatibility policy is unclear.
