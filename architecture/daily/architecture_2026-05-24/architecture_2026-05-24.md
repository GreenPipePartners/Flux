# Architecture Daily Log - 2026-05-24

## Session: Flux.live architecture clarification

- Intent: Explain why Fluxolot Live can show `Good` quality while also marked `Stale`, and clarify whether Live is expected to be a constantly running process.
- Scope reviewed:
  - `web/Flux/src/flux/live/views.py`
  - `web/Flux/src/flux/live/selectors.py`
  - `web/Flux/src/flux/opt/services.py`
  - `web/Flux/src/flux/serve/management/commands/flux_sampling_worker.py`
  - `serve/worker.py`
  - `web/Flux/src/runtime/models.py`
  - `scripts/flux-start.sh`
  - `docs/runbooks/fluxolot-fishtank.md`
- Architectural finding: Flux.live is not direct live binding. It renders cached `LatestTagValue` snapshots and leases demand. Freshness depends on Flux.opt/Flux.serve sampling workers writing new samples. `Good/Stale` means the last cached sample quality was Good, but its read timestamp exceeded `STALE_AFTER_SECONDS`.
- Boundary notes: Browser/Django request path should remain read-only/cached and should not become a direct Ignition polling loop. Long-running sampling belongs under Flux.serve/Flux.opt workers.
- Report path: none requested.
- Blockers: none for explanation; implementation decision remains whether to make the sampler lifecycle stricter/visible/self-healing.
- Next architecture actions: Consider recommending a clearer operational contract for `fluxolot-live-sampler` and a service-health warning when Live scopes have active demand but no fresh sampler heartbeat.

## Session: Fluxolot sampler liveness expectation

- Intent: Clarify whether the Fluxolot background sampler should be alive all the time after `Good/Stale` appeared again.
- Scope reviewed: `scripts/flux-start.sh`, `web/Flux/src/flux/serve/monitor.py`, and `web/Flux/src/flux/serve/management/commands/flux_sampling_worker.py`.
- Architectural finding: `flux start` does start `flux_sampling_worker --profile fluxolot-fishtank`, which heartbeats as `fluxolot-live-sampler`. For operator Live, that process should be considered continuously alive. Current monitor semantics mark it `EXPECTED`, not `REQUIRED`, which weakens alerting/recovery despite the UI depending on it for freshness.
- Blockers: Current process liveness was not checked in architecture mode; operational confirmation should inspect `fluxolot-live-sampler` process and heartbeat age.
- Next architecture actions: Recommend promoting Fluxolot sampler health to required when Fluxolot live scope is enabled, and surfacing sampler heartbeat age directly on `/live/fluxolot/`.

## Session: Coordinator runtime/charts notices review

- Intent: Handle Coordinator notices `2026-05-24-coordinator-004`, `2026-05-24-coordinator-005`, and `2026-05-24-coordinator-008` for interface health persistence, OPC runtime truth, and Flux.charts stress-load restoration/pagination.
- Scope reviewed:
  - `architecture/agent_notices.md`
  - `coordination/daily/coordination_2026-05-24/coordination_2026-05-24.md`
  - `coordination/delegation_register.md`
  - `web/Flux/src/dashboard/services.py`
  - `web/Flux/src/dashboard/views.py`
  - `web/Flux/src/templates/dashboard/home.html`
  - `web/Flux/src/flux/serve/field_supervisor.py`
  - `web/Flux/src/flux/serve/management/commands/flux_field_supervisor.py`
  - `web/Flux/src/flux/serve/management/commands/flux_sampling_worker.py`
  - `web/Flux/src/flux/serve/monitor.py`
  - `web/Flux/src/flux/charts/views.py`
  - `web/Flux/src/flux/charts/control.py`
  - `web/Flux/src/flux/charts/providers/nav_wells.py`
  - `web/Flux/src/flux/charts/questdb_data_plane.py`
  - `web/Flux/src/flux/nav/registry.py`
  - `scripts/flux-start.sh`
- Architectural findings: Interface health needs a required persistent sampler contract; OPC runtime `running` is unsafe when derived from `FieldEndpoint.status` alone; Flux.charts stress/nav-well data and one-page route are preserved, but dashboard trace detail still risks rendering thousands of profile links.
- Report path: `arch_review.md`.
- Blockers: No OS process/port probe was performed in architecture mode; report recommendations rely on code-level evidence and persisted heartbeat/snapshot contracts.
- Next architecture actions: Re-review after Build adds sampler service visibility, composed endpoint runtime status, and bounded/paginated chart dashboard navigation.
