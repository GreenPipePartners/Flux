# Fluxolot Fishtank

Fluxolot Fishtank is the local field simulation handle for validating Flux.spot, Flux.serve, FieldAgent, Flux.trace, and Ignition configuration loops.

## Operator Notes

- Sir Fluxolot and Missus Fluxolot each get a dedicated FieldAgent endpoint.
- Start and stop Fluxolot endpoints from the dashboard SimServer card.
- The dashboard queues commands; `flux_field_supervisor` claims and applies them.
- A running Flux.serve heartbeat means the supervisor is alive, not that every endpoint is enabled.

## Current Troubleshooting Checks

```bash
flux status
flux doctor
```

For detailed Django state, inspect `sim.Endpoint`, `serve.SimAgentHeartbeat`, `ServeCommand`, and `ServeHeartbeat` from `web/Flux`.

## Proof Surfaces

- Current state: `/spot/fluxolot/`
- Historical chart cycle: `/chart/fluxolot/`
- Sir profile: `/chart/fluxolot-sir/`
- Missus profile: `/chart/fluxolot-missus/`
- Fixture install: `uv run python web/Flux/manage.py install_fluxolot_fishtank`
- Spot sampler: `uv run python web/Flux/manage.py flux_sampling_worker --profile fluxolot-fishtank`

## Spot Sampler Liveness

Fluxolot Spot is expected to have a continuously running sampler after `flux start`.

Current reality:

- `scripts/flux-start.sh` starts `flux_sampling_worker --profile fluxolot-fishtank`.
- That worker heartbeats as `fluxolot-live-sampler` for compatibility.
- Spot cards read cached `LatestTagValue` rows, so a stale sampler can leave `Good` values marked `Stale`.

Check the stack before refreshing pages repeatedly:

```bash
flux status
flux doctor
flux logs
```

If Fluxolot values stay stale, restart the stack or run one sampler cycle directly:

```bash
uv run python web/Flux/manage.py flux_sampling_worker --once --profile fluxolot-fishtank
```

Target contract: Flux.serve should treat the Fluxolot sampler as required whenever the Fluxolot Spot scope is enabled and surface stale heartbeat age in operator UI.

## Plane Proof Dataset

Default install seeds a lightweight local proof dataset. For a years-long Flux.plane/Flux.chart proof, run:

```bash
uv run python web/Flux/manage.py install_fluxolot_fishtank --long-history --plane-samples-all --export-questdb
```

This creates three years of 15-minute Fluxolot history, splits Trace profiles into Sir and Missus tanks, fills local `plane.sample` rows, and exports the Plane samples to QuestDB when available.
