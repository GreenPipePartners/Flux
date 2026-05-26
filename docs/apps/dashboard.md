# Dashboard

The dashboard at `http://localhost:8000/` is the local operator console.

It shows readiness, runtime read health, stale recovery actions, SimServer endpoint state, and Flux.serve heartbeat state.

## Ignition Bridges

The Ignition bridges readiness card summarizes configured Fluxy bridge endpoints.

Use `http://localhost:8000/bridges/` to add or update production and simulator bridge endpoints. This is the front-facing bridge configuration page; Django admin is not required for normal bridge setup.

Tokens are never copied. Only token presence is exported.

Bridge field meanings:

- **Fluxy base URL** is the Ignition WebDev endpoint Flux uses, usually ending in `/system/webdev/flux`.
- **Token set** means Flux has a stored bridge token. It does not show the token value and does not prove the token is still valid.
- **Token** input is write-only. Leaving it blank while saving keeps the existing stored token.
- **Clear stored token** removes the saved token for that bridge. Use it when rotating credentials, disabling token auth, or correcting a bridge that should not authenticate with the old token.
- **Connected to Ignition 8.3.6 (b2026042713)** means the last bridge test reached Ignition and returned product version `8.3.6`; the `b...` suffix is Ignition's build identifier, not a Flux version.

Current gap: the UI should explain token presence and build text inline or by hover/popdown. Until then, this section is the documentation target for the Ignition Bridges Flux.links copy context.

## Sim Config

The Sim config readiness card summarizes whether local simulation has runtime tags, enabled endpoints, and enabled field tags.

## Latest Reads

The Latest reads readiness card summarizes current runtime tag freshness and quality from Flux storage.

This is cached health. The card reads `LatestTagValue` rows; it should not be interpreted as the browser directly reading Ignition.

Current reality:

- `Good` quality describes the last sampled value quality.
- `Stale` means the last sample is older than the configured stale threshold.
- The dashboard can submit a stale-recovery action that performs one consolidated Fluxy block read for the displayed stale set.
- Trial/stress tags with `TRACE_STRESS` category are hidden from interface health counts.

Target contract:

- A required Flux.serve sampler keeps interface runtime tags fresh in the background.
- Flux.opt performs block reads and writes `LatestTagValue` / `TagSample`.
- The dashboard may HTMX-refresh cached health status, but browser polling must not perform Ignition IO.

## Flux.web Display Pulse

Operational pages opt into the shared Flux.web display pulse through `#flux-page-content`.

- Default cadence is 5 seconds.
- The pulse swaps the cached server-rendered page fragment with HTMX.
- The request path must remain display-only and must not perform Ignition or Fluxy reads.
- The hero banner shows only the next display-refresh timer; backend freshness belongs in the page's operational cards.
- Configure views, focused forms, and dirty forms pause the pulse so operator input is not overwritten.

## Fluxserve Readiness

The Flux.serve readiness card summarizes supervisor and worker heartbeat health for the local Flux stack.

`Flux.serve` observed health should come from `ServeServiceSnapshot` when available. Raw heartbeats are evidence, not the whole truth.

## Service Visibility

When service snapshots exist, dashboard copy context uses observed service health:

- healthy / warning / error counts from `ServeServiceSnapshot`
- stale snapshot count when the monitor has not refreshed inside the stale threshold
- raw heartbeats retained as evidence for debugging

Use the Flux.serve app for service detail. The dashboard should summarize health; it should not run socket/process probes during page rendering.

## SimServer

The SimServer card describes materialized Flux simulated OPC-UA endpoints and their supervised runtime state.

## OPC Server Runtime Truth

The dashboard should only claim an OPC endpoint is `running` when there is fresh Flux.serve evidence.

Current gap: some runtime rows can derive `running` from stored `sim.Endpoint.status`. That can be stale after a process dies, a port changes, or a supervisor stops before updating the row.

Target contract for each endpoint row:

- desired enabled/disabled state from `sim.Endpoint`
- latest `serve.SimAgentHeartbeat` age
- `serve.SimAgentHeartbeat.process_id`
- endpoint URL and port
- latest `ServeServiceSnapshot` observed state
- optional OS/TCP probe when available

If the heartbeat or snapshot is stale, show `stale` or `last reported running`, and expose the stale reason. PID and port should be visible before the UI asks an operator to trust a `running` label.

## Flux.chart Readiness

The Flux.chart readiness card summarizes configured `TraceProfile` and `TraceSignal` counts.

Large chart sets must not turn into thousands of dashboard links. The dashboard detail should prefer aggregate routes:

- `/chart/wells/` for navigation-well stress charts
- `/chart/fluxolot/` for Fluxolot proof charts
- `/chart/` for chart paths, samples, and profile discovery

Current gap: enabled `TraceProfile` rows may still render as one link per profile in dashboard detail. The stress data should be preserved, but dashboard navigation should aggregate, paginate, or search it.

## Service Heartbeats

Service heartbeat cards describe Flux.serve supervisor and worker processes. They do not prove every individual SimServer endpoint is enabled.

## Stale Tag Recovery

Stale recovery uses a consolidated Fluxy block read to refresh selected stale runtime tags without browser-driven read loops.

Use stale recovery as an operator action, not as the steady-state service model. If stale counts return quickly, check the sampler/worker contract in `apps/live.md` and `apps/serve.md`.

## Boundaries

- Shows app health from `dashboard.services`.
- Performs stale recovery as one block read, not per-tag loops.
- Displays service summaries; it does not own long-lived processes.

## Related Docs

- `operator-guide.md`
- `flux-architecture.md`
