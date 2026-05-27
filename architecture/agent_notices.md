# Architect Agent Notices

Append-only inbox for Coordinator notices to Architect. Coordinator appends notices below; Architect appends outcomes when notices are handled.

## Notice: 2026-05-24-coordinator-004

- Status: open
- Priority: high
- Horizon: next-run
- Source: Coordinator
- Target agent: Architect
- Feature/context: Interface health refresh persistence service
- Request: Write an architecture recommendation for making interface runtime tag health refresh persistently serviced rather than stale-page dependent. The user observed Overall health reading `0/50 interface runtime tags online`, then after trial reset and page reload it became `26/50`, implying the underlying state recovered but the page did not refresh/update until reload.
- Acceptance signal: Architecture report or notice outcome describes the current likely refresh boundary, proposes a persistent service/update contract for interface health, names ownership between Flux.serve/live/web/opt if applicable, and calls out HTMX/browser refresh expectations versus backend sampler responsibilities.
- Files/context: Ignition Bridges/health dashboard area showing `Overall`, `Attention needed`, `0/50 interface runtime tags online · last read May 24, 2026, 7:31 p.m.`, and `8032 trial/stress tags hidden from interface health`; user reset the Ignition trial and saw the displayed count recover only after reload.
- Notes: User requested this be sent to Architect for a write-up on how to make it a persistent service. This is architecture-only; do not implement runtime changes through the notice.

### Architect outcome - 2026-05-24

- Architect status after outcome: completed.
- Review action: Wrote architecture recommendation in `arch_review.md` and updated architecture logs.
- Highest-severity finding: High — interface health currently reads cached `LatestTagValue` state on dashboard requests and exposes manual stale refresh, while the persistent backend sampler contract is implicit. Flux.serve should supervise a required interface-health sampler, Flux.opt should own block reads and persistence, Flux.live should own freshness semantics, and Flux.web should only render/poll cached state.
- Blockers: No runtime process inspection was performed in architecture mode.
- Remaining follow-up: Build should add sampler service visibility and bounded HTMX health-fragment refresh that does not perform Ignition reads from the browser/request path.

## Notice: 2026-05-24-coordinator-005

- Status: open
- Priority: high
- Horizon: next-run
- Source: Coordinator
- Target agent: Architect
- Feature/context: OPC server runtime truth contract
- Request: Investigate whether the dashboard `OPC server runtime` rows can truthfully claim endpoints are `running`, and define the runtime status/PID/port contract if they cannot. The user asked whether rows like `Flux sim ACM_02 Server`, `Flux sim ACM Server`, `Flux sim FluxolotOPC Server`, `Flux sim OPC-UA Server`, `local-field`, `local-sim`, `missus-fluxolot-fishtank`, and `sir-fluxolot-fishtank` are actually running; if true the UI should expose PID and port, and if not this needs architecture investigation.
- Acceptance signal: Architecture report or notice outcome states whether `running` should be derived from `FieldEndpoint.status`, fresh `FieldAgentHeartbeat`, `ServeServiceSnapshot`, OS process/port probes, or a composed contract; identifies stale/false-positive risk; and recommends where PID/port metadata should be generated, persisted, and displayed.
- Files/context: `web/Flux/src/templates/dashboard/home.html` sim-config focus; `web/Flux/src/dashboard/services.py` `field_device_status()` currently treats `online` as `endpoint.enabled and endpoint.status == RUNNING`; `web/Flux/src/flux/serve/management/commands/flux_field_supervisor.py` records `FieldAgentHeartbeat.process_id` and sets endpoint status; `web/Flux/src/flux/serve/field_supervisor.py` computes FieldAgent endpoint ports with `base_port + endpoint.id`; `web/Flux/src/flux/serve/monitor.py` checks heartbeat freshness for field agents in snapshots.
- Notes: Coordinator code review suggests the dashboard configure view can display `running` from stored DB status without directly checking heartbeat freshness in `field_device_status()`. Actual OS process/port verification was not available in this run because bash execution is denied in the current tool policy.

### Architect outcome - 2026-05-24

- Architect status after outcome: completed.
- Review action: Wrote runtime truth contract recommendation in `arch_review.md` and updated architecture logs.
- Highest-severity finding: High — dashboard runtime rows should not claim `running` from `FieldEndpoint.status` alone. The status should be composed from desired endpoint state, fresh `FieldAgentHeartbeat`, `process_id`, derived endpoint URL/port, optional OS/TCP probe, and/or fresh `ServeServiceSnapshot` evidence.
- Blockers: Current OS process and port truth were not verified from the host in architecture mode.
- Remaining follow-up: Build should introduce a Flux.serve-owned `EndpointRuntimeStatus` selector and render PID/port/heartbeat age/observed state in the dashboard before using `running` as user-facing truth.

## Notice: 2026-05-24-coordinator-008

- Status: open
- Priority: high
- Horizon: next-run
- Source: Coordinator
- Target agent: Architect
- Feature/context: Flux.charts stress-load restoration and pagination
- Request: Determine what happened to the prior trial/stress Flux.charts live-load process that used one page with next/forward navigation instead of thousands of individual well links. Verify whether the source data still exists or was truncated, identify what it would take to make the stress/load test fairly quick to restore, and define the pagination/single-page architecture for large chart sets.
- Acceptance signal: Architecture report or notice outcome explains current data/process state, names the source tables/files/commands that preserve the stress data, recommends how to restore the single-page navigation test without deleting source data, and defines pagination expectations for dashboard/chart surfaces with large chart counts.
- Files/context: Dashboard `Flux.charts` card showed `1004 charts, 8067 signals`; `web/Flux/src/templates/dashboard/home.html` trace focus currently renders a `Navigation wells` row plus one `Open` link per enabled `TraceProfile`; `web/Flux/src/dashboard/services.py` counts enabled `TraceProfile` and `TraceSignal`; work note `work_assignment/2026_May_19/to_do_first.md` says the trial stress test logic should be kept but not be an interface display.
- Notes: User specifically said to preserve the trial stress test and source data, remove the thousand single-page links from the UI, and keep the restored test on a single page.

### Architect outcome - 2026-05-24

- Architect status after outcome: completed.
- Review action: Wrote Flux.charts stress-load/pagination recommendation in `arch_review.md` and updated architecture logs.
- Highest-severity finding: Medium — the nav-well stress source path is preserved through `navigation.db`, `seed_nav_well_trace_config()`, `TraceProfile`/`TraceSignal`, `RuntimeTag(category=TRACE_STRESS)`, local `plane.sample`, QuestDB export, and `/charts/wells/`; however, the dashboard still risks rendering one `Open` link per enabled profile.
- Blockers: Did not execute restoration commands; review is code-structure based.
- Remaining follow-up: Build should preserve stress rows, keep `/charts/wells/` as the single-page cycling surface, and replace dashboard profile-link explosion with aggregate links plus pagination/search.
- Superseded 2026-05-26: user selected retirement instead of restoration for advanced navigation and nav-well surfaces. Preserve generic chart/Plane data where useful, but remove `/chart/wells*`, nav-well commands/providers, `navigation.db`, and `nav_*` tables.

## Cleanup implementation note: 2026-05-24-runtime-and-chart-follow-up

- Source: Cleanup
- Related notices: `2026-05-24-coordinator-005`, `2026-05-24-coordinator-008`
- Implemented cleanup: dashboard runtime rows now label endpoint state as stored state plus heartbeat evidence, and render PID/port evidence where the existing heartbeat/endpoint metadata provides it. Dashboard Flux.chart detail now keeps aggregate links and no longer restores `/chart/wells*`.
- Still architecture-owned: define the durable truth contract for whether an endpoint is actually running (OS/TCP/Serve-owned selector versus stored state), and keep pagination/search contracts for large chart sets. No source data deletion/truncation was performed by Cleanup.
