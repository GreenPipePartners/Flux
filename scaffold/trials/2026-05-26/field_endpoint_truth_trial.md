# Labyrinth Curator Trial: field_endpoint_truth__sim__serve__dashboard

## Runner Capability

- Requested reasoning mode: `Low`.
- Actual model-level reasoning control: not exposed by the current task tool.
- Enforcement used: low-curator prompt, read-only scope, fixed output schema.

## Node Chain Checked

1. Flux.sim endpoint config - `web/Flux/src/flux/sim/models.py`
2. Flux.serve FieldAgent heartbeat - `web/Flux/src/flux/serve/models.py`
3. Flux.serve monitor snapshot - `web/Flux/src/flux/serve/monitor.py`
4. Flux.sim runtime display - `web/Flux/src/templates/sim/partials/field_runtime_status.html`
5. Dashboard serve display - `web/Flux/src/templates/dashboard/home.html`

## Success Signal Testability

- Testable: yes
- Reason: Endpoint config, heartbeat evidence, monitor snapshots, and rendered dashboard/sim status are all represented in Django models/views/templates.

## Handoffs

- From Flux.sim endpoint config to Flux.serve FieldAgent heartbeat: `SimAgentHeartbeat.endpoint` is a FK to `sim.Endpoint` with `related_name="heartbeats"`.
- From Flux.serve FieldAgent heartbeat to Flux.serve monitor snapshot: `field_agent_result()` reads latest endpoint heartbeat and records PID/TCP evidence in snapshot metadata.
- From Flux.serve monitor snapshot to Flux.sim runtime display: `sim_field_runtime_status()` counts only healthy OK `Flux.serve.field-agent:` snapshots as verified endpoints.

## Failure Matrix Updates

| Failure | Likely Owner | Evidence |
|---|---|---|
| Stored endpoint status can disagree with runtime truth | Flux.serve monitor | `web/Flux/src/flux/serve/monitor.py` |
| Dashboard serve card shows service snapshots, but endpoint-specific truth is indirect through service keys | Dashboard | `web/Flux/src/templates/dashboard/home.html` |

## Existing Tests Found

- `web/Flux/src/flux/serve/tests.py` - monitor records healthy, dead-process, closed-port, and skipped-TCP FieldAgent snapshots.
- `web/Flux/src/flux/sim/tests.py` - sim index renders FieldAgent Runtime and states that the card does not run probes.
- `web/Flux/src/dashboard/tests.py` - dashboard serve status prefers observed snapshots when present.

## Proposed Bounded Test

- Add one Django view test that creates a FieldEndpoint, fresh FieldAgent heartbeat, healthy `Flux.serve.field-agent:<name>` snapshot, then asserts `/sim/` shows `1 verified` and the endpoint row shows healthy snapshot text.

## Meta-Architect Disposition

- Format generalizes cleanly.
- Do not create the full labyrinth yet; keep this as a candidate until the pilot produces one implemented test handoff.
