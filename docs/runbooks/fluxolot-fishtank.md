# Fluxolot Fishtank

Fluxolot Fishtank is the local field simulation handle for validating Flux Live, Serve, FieldAgent, Trace, and Ignition configuration loops.

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

For detailed Django state, inspect `FieldEndpoint`, `FieldAgentHeartbeat`, `ServeCommand`, and `ServeHeartbeat` from `web/Flux`.

## Proof Surfaces

- Current state: `/live/fluxolot/`
- Historical trace cycle: `/trace/fluxolot/`
- Sir profile: `/trace/fluxolot-sir/`
- Missus profile: `/trace/fluxolot-missus/`
- Fixture install: `uv run python manage.py install_fluxolot_fishtank`
- Live sampler: `uv run python manage.py flux_sampling_worker --profile fluxolot-fishtank`

## Plane Proof Dataset

Default install seeds a lightweight local proof dataset. For a years-long Flux.plane/Flux.trace proof, run:

```bash
uv run python manage.py install_fluxolot_fishtank --long-history --trace-cache-all --export-questdb
```

This creates three years of 15-minute Fluxolot history, splits Trace profiles into Sir and Missus tanks, fills local `TraceCachePoint` rows, and exports the cache to QuestDB when available.
