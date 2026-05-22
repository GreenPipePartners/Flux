# Dashboard

The dashboard at `http://localhost:8000/` is the local operator console.

It shows readiness, runtime read health, stale recovery actions, SimServer endpoint state, and Flux.serve heartbeat state.

## Ignition Bridges

The Ignition bridges readiness card summarizes configured Fluxy bridge endpoints.

Use `http://localhost:8000/bridges/` to add or update production and simulator bridge endpoints. This is the front-facing bridge configuration page; Django admin is not required for normal bridge setup.

Tokens are never copied. Only token presence is exported.

## Sim Config

The Sim config readiness card summarizes whether local simulation has runtime tags, enabled endpoints, and enabled field tags.

## Latest Reads

The Latest reads readiness card summarizes current runtime tag freshness and quality from Flux storage.

## Fluxserve Readiness

The Flux.serve readiness card summarizes supervisor and worker heartbeat health for the local Flux stack.

## SimServer

The SimServer card describes materialized Flux simulated OPC-UA endpoints and their supervised runtime state.

## Service Heartbeats

Service heartbeat cards describe Flux.serve supervisor and worker processes. They do not prove every individual SimServer endpoint is enabled.

## Stale Tag Recovery

Stale recovery uses a consolidated Fluxy block read to refresh selected stale runtime tags without browser-driven read loops.

## Boundaries

- Shows app health from `dashboard.services`.
- Performs stale recovery as one block read, not per-tag loops.
- Displays service summaries; it does not own long-lived processes.

## Related Docs

- `operator-guide.md`
- `flux-architecture.md`
