# Docs Steward Agent Notices

Append-only inbox for Coordinator notices to Docs Steward. Coordinator appends notices below; Docs Steward appends outcomes when notices are handled.

## Notice: 2026-05-24-coordinator-001

- Status: open
- Priority: high
- Horizon: next-run
- Source: Coordinator
- Target agent: Docs Steward
- Feature/context: Flux.live service contract
- Request: Document the surfaced Flux.live/Flux.serve.live architecture mismatch: current cached live snapshots, current sampler/demand implementation, target hot/warm/cold service contract, and Fluxolot sampler liveness expectation.
- Acceptance signal: MkDocs contains a durable explanation of current reality vs target contract; related app docs/runbook pages point to it; relevant `Flux.links` docs pointers point at the best docs page; MkDocs validation is run or blockers are recorded.
- Files/context: `docs/apps/live.md`, `docs/apps/serve.md`, `docs/apps/opt.md`, `docs/runbooks/fluxolot-fishtank.md`, `mkdocs.yml`, `web/Flux/src/flux/live/views.py`, `web/Flux/src/flux/serve/management/commands/flux_sampling_worker.py`, `web/Flux/src/flux/opt/services.py`, `web/Flux/src/flux/serve/monitor.py`, `scripts/flux-start.sh`.
- Notes: User expects Flux.serve.live to negotiate hot/warm/cold reads as a service contract. Current code has `RefreshLane`, `RuntimeDemand`, `OptimizationLease`, `RuntimeSchedulerConfig`, and `flux_sampling_worker`, but Fluxolot uses a profile sampler that reads all matching tags by prefix; `RefreshLane` is not yet the active scheduler. Also fix or report missing MkDocs nav targets `trace-architecture.md` and `apps/trace.md`.

### Docs Steward outcome - 2026-05-24

- Docs Steward status after outcome: completed.
- Docs changed: `docs/apps/live.md`, `docs/apps/serve.md`, `docs/apps/opt.md`, `docs/apps/dashboard.md`, `docs/operator-guide.md`, `docs/runbooks/fluxolot-fishtank.md`, `docs/flux-architecture.md`, and `documentation/core_area_files.md`.
- Outcome: Documented current cached Live/runtime health behavior, the target Flux.serve/Flux.opt sampler contract, hot/warm/cold target planning, and the Fluxolot sampler liveness expectation. Dashboard/Live/Serve/Opt docs now separate browser cached display from backend block-read ownership.
- Validation: pending in this run; result is recorded in the daily documentation log after build.
- Remaining follow-up: Product work still needs to make the general interface-health sampler required/visible and wire `RefreshLane` into the active sampler contract.
- Validation update: `uv run --project web/Flux mkdocs build --strict` passed on 2026-05-24.

## Notice: 2026-05-24-coordinator-003

- Status: open
- Priority: medium
- Horizon: next-run
- Source: Coordinator
- Target agent: Docs Steward
- Feature/context: Ignition Bridges token and version explanations
- Request: Document the Ignition Bridges token model and visible connection metadata in user-facing docs: explain what a stored token is, why the UI may show or hide token state, what “Clear stored token” does and when to use it, and what Ignition version/build text like `Ignition 8.3.6 (b2026042713)` means.
- Acceptance signal: MkDocs contains a clear user-facing explanation and any relevant Flux.links docs pointer target is identified or updated by Docs Steward; unresolved product/UI wording questions are recorded for cleanup.
- Files/context: Ignition Bridges UI/detail/configure views; user pasted bridge detail `default / Simulator`, endpoint `http://localhost:8088/system/webdev/flux`, `Connected`, `Token set`, `Connected to Ignition 8.3.6 (b2026042713).`.
- Notes: User explicitly asked “what is this” for Token, requested a documents link, called “Clear stored token” unclear, questioned whether `TOKEN SET` should exist, and requested hover/docs explanation for the Ignition build string. Coordinate with Site Auditor notice `2026-05-24-coordinator-002` for UI affordance findings.

### Docs Steward outcome - 2026-05-24

- Docs Steward status after outcome: completed.
- Docs changed: `docs/apps/dashboard.md` and `docs/operator-guide.md`.
- Outcome: Documented Fluxy base URL, token presence, write-only token entry, blank-token-save behavior, `Clear stored token`, and Ignition version/build text. Existing bridge Flux.links target `http://localhost:8001/apps/dashboard/#ignition-bridges` now lands on the detailed explanation.
- Validation: pending in this run; result is recorded in the daily documentation log after build.
- Remaining follow-up: UI cleanup should still add hover/popdown help for token state and Ignition build text; Docs Steward did not implement UI behavior.
- Validation update: `uv run --project web/Flux mkdocs build --strict` passed on 2026-05-24.

## Notice: 2026-05-24-coordinator-010

- Status: open
- Priority: medium
- Horizon: next-run
- Source: Coordinator
- Target agent: Docs Steward
- Feature/context: Import chart CSV help content
- Request: Provide user-facing documentation/help content for the dashboard `Import chart CSV` workflow, including a concise `What is this?` explanation and an example Markdown/fenced CSV layout suitable for a pop-down in the UI.
- Acceptance signal: MkDocs or notice outcome contains the chart CSV import purpose, expected columns/layout, a small example, and the recommended docs anchor/Flux.links target for the UI pop-down; blockers or unknown CSV schema details are recorded.
- Files/context: `web/Flux/src/templates/dashboard/home.html` trace configure focus; `web/Flux/src/flux/charts/importer.py` or related importer/schema; dashboard `Flux.charts` card with `1004 charts, 8067 signals`.
- Notes: Coordinate with Site Auditor notice `2026-05-24-coordinator-009`; Docs Steward should supply durable wording/content, not implement the UI.

### Docs Steward outcome - 2026-05-24

- Docs Steward status after outcome: completed.
- Docs changed: `docs/apps/charts.md` and `docs/charts-architecture.md`.
- Outcome: Added `Import Chart CSV` documentation with purpose, expected columns, fenced CSV example, import results, and current schema gap. Recommended UI docs target: `http://localhost:8001/apps/charts/#import-chart-csv`. Also documented navigation-well stress preservation and bounded dashboard navigation expectations.
- Validation: pending in this run; result is recorded in the daily documentation log after build.
- Remaining follow-up: Product/UI work can use the added CSV section for a popdown; Docs Steward did not implement UI behavior.
- Validation update: `uv run --project web/Flux mkdocs build --strict` passed on 2026-05-24.
