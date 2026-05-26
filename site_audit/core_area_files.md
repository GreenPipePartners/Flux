# Site Audit Core Area Files

Last updated: 2026-05-24

## Ownership

- Area name: `site_audit`.
- Human summary: `site_audit.md`.
- Baseline snapshot: `site_audit/baseline.json`.
- Latest collected snapshot: `site_audit/latest.json`.
- Drift report: `site_audit/diffs.md`.
- Notice inbox: `site_audit/agent_notices.md`.
- Daily ledger: `site_audit/daily/site_audit_{YYYY-MM-DD}/site_audit_{YYYY-MM-DD}.md`.

## Baseline Policy

- Treat `site_audit/baseline.json` as committed known-good project state.
- Do not update `baseline.json` during coordinator-note parameter updates or drift audits.
- Update the baseline only on explicit user request for a new known-good baseline or an initial baseline creation task.
- The 2026-05-24 cleanup audit did not modify `baseline.json`; it updated `latest.json`, `diffs.md`, and `site_audit.md` with a fixture-backed Command Center cleanup snapshot.

## Target Environments

- Primary running-site target: Flux local dev server at `http://127.0.0.1:8000/` started with `flux start --web-mode dev`.
- Fallback target when the Flux CLI/dev server is unavailable: Django `pytest` live server plus Django test client from `web/Flux`.
- Gunicorn mode: use `flux start --web-mode gunicorn` only when trace/e2e behavior requires gunicorn.
- Current known blocker from the existing baseline run: the live browser landed on `/setup/`; dashboard Comp Surface verification requires completed setup/fixture data so `/` renders Command Center instead of Initial Flux Setup.

## Standard Commands

- From `/home/bobby/Projects/11006-PRW-flux/web/Flux`: `uv run python manage.py check`.
- From `/home/bobby/Projects/11006-PRW-flux/web/Flux`: `uv run pytest -q ../../site_audit/test_playwright_initial_scrape.py`.
- From `/home/bobby/Projects/11006-PRW-flux/web/Flux`: `uv run pytest -q ../../site_audit/test_playwright_cleanup_audit.py`.
- Running-site startup, from repository root when available: `flux start --web-mode dev`.
- Trace/e2e startup, only when needed: `flux start --web-mode gunicorn`.

## Route And Surface Inventory

### Dashboard Command Center

- Route: `/`.
- Surface: `#dashboard-comp-surface[data-comp-surface]`.
- Focus region: `#dashboard-comp-focus`.
- Grid: `[data-comp-card-grid]` / `.readiness-grid`.
- HTMX mode-control target: `#dashboard-comp-surface`, `hx-select="#dashboard-comp-surface"`, `hx-swap="outerHTML show:none"`.
- Required viewport smoke: desktop `1280x900` and mobile `390x844`.
- Required semantic checks: use buttons by accessible names `Show summary view`, `Show detail view`, and `Show configure view`; verify `aria-pressed`, selected anchor card visibility, no hidden heavy Detail/Configure DOM in Summary mode, and no console/request failures during swaps.

### Coordinator-Driven Next-Run Parameters

These parameters are derived from open Site Auditor notices in `site_audit/agent_notices.md` and should be treated as audit scope, not approval to edit app code or bless drift.

#### Notice `2026-05-24-coordinator-002` — Ignition Bridges

- Route/modes: `/`, `/?card=bridges&mode=summary`, `/?card=bridges&mode=detail`, `/?card=bridges&mode=configure`.
- Elements: `#bridges-comp-card`, `#bridges-comp-focus`, `[data-bridge-copy]`, `label` text `Fluxy base URL`, token status pill text, clear-token checkbox, bridge rows in `.bridge-mini-list` / `.stale-list`.
- Audit assertions:
  - Detail top-left Flux.links/copy widget works and has a usable docs/help affordance.
  - Configure view must not present `admin` as the base entry/default for Fluxy base URL.
  - `Token set` is understandable or replaced with clearer token-state language.
  - `Clear stored token` has clear explanation/placement so users know leaving token blank preserves the stored token.
  - Ignition build strings such as `(b2026042713)`, if rendered, have hover/help context.

#### Notice `2026-05-24-coordinator-006` — Runtime Service Observability

- Route/modes: `/`, `/?card=sim-config&mode=detail`, `/?card=sim-config&mode=configure`, `/?card=serve&mode=detail`.
- Elements: `#sim-config-comp-card`, `#sim-config-comp-focus`, `#serve-comp-card`, `#serve-comp-focus`, OPC server runtime rows, Flux.serve Observed Health rows.
- Audit assertions:
  - OPC runtime rows expose PID and port where runtime evidence is available.
  - Stale, unknown, or missing runtime evidence is not presented as simply `running`.
  - Flux.serve Observed Health exposes operational detail without hiding stale snapshot evidence.
  - Long service/detail lists are paginated or otherwise bounded.
  - Record dependency on architecture notice `2026-05-24-coordinator-005` for any missing metadata contract.

#### Notice `2026-05-24-coordinator-007` — Flux.live Stale Recovery And CSV Import

- Route/modes: `/`, `/?card=live&mode=detail`, `/?card=live&mode=configure`, plus `/live/` and `/live/pad-overview/` as supporting routes.
- Elements: `#live-comp-card`, `#live-comp-focus`, stale tag rows, `input[name="live_scope_csv"]`, `input[name="live_scope"]`, `input[name="replace_live_scope"]`/`#replace_live_scope` if present.
- Audit assertions:
  - First stale rows such as Demo Area Pump/Tank reads include status/source context beyond `Last read older than 120s`.
  - Rows with `Bad quality: Error_Configuration("Server \"Flux Field\" does not exist.")` are clearly isolated as legacy/cleanup candidates and are not silently deleted by audit work.
  - `Replace existing cards for imported scopes` checkbox is visually aligned with its label/comment.
  - `Default scope slug` defaults to or suggests `Fluxolot`, not `pad-overview`.

#### Notice `2026-05-24-coordinator-009` — Flux.charts Large-List Cleanup

- Route/modes: `/`, `/?card=trace&mode=detail`, `/?card=trace&mode=configure`, plus `/charts/`, `/charts/wells/`, `/charts/fluxolot/`, and related payload/embed routes from the baseline inventory.
- Elements: `#trace-comp-card`, `#trace-comp-focus`, chart detail list `.stale-list`, `Import chart CSV` form, chart navigation links.
- Audit assertions:
  - Dashboard detail should not render a thousand per-chart/well `Open` links.
  - Existing single-page navigation/stress-test path with next/forward behavior remains available.
  - Large chart lists are paginated or otherwise bounded on dashboard and chart views.
  - `Import chart CSV` has a `What is this?` affordance with an example layout pop-down.
  - Record dependencies on Architect notice `2026-05-24-coordinator-008` and Docs Steward notice `2026-05-24-coordinator-010`.

#### Notice `2026-05-24-coordinator-011` — Table Copy Affordance Standard

- Representative surfaces: Ignition Bridges, OPC server runtime, Flux.live Stale Tag Recovery, Flux.charts readiness/detail lists, Flux.serve Observed Health.
- Audit assertions:
  - Every table-like/list-detail section has a top-right copy icon that copies the entire table/list contents.
  - Placement is top-right relative to the table/list, not only the card or focus panel.
- Existing Flux.links/copy widgets are recorded as reusable where they cover the whole table; otherwise flag the missing table-level copy affordance.

### Cleanup Audit Fixture And Coverage Added 2026-05-24

- Test/audit collector: `site_audit/test_playwright_cleanup_audit.py`.
- Server mode: Django `StaticLiveServerTestCase` with seeded setup-complete Command Center fixture data; persistent `flux start --web-mode dev` was not used for this run.
- Browser/viewports: Chromium desktop `1280x900`; mobile smoke `390x844`.
- Seeded evidence: Ignition bridge with version/build string, fresh and stale FieldAgent endpoint heartbeats with PID/port, stale/legacy Flux.live runtime tags, 64 chart profile paths plus consolidated chart routes, 56 Flux.serve observed-health snapshots, and one chart sample table.
- Verified routes/surfaces: `/`, dashboard `bridges`, `sim-config`, `live`, `trace`, and `serve` modes via real glyph controls; `/charts/?card=trace-paths&mode=detail` page 1/2; `/charts/wells/`; `/charts/?card=trace-samples&mode=detail`.
- Current open cleanup drift from this run: Flux.serve observed-health detail list is unbounded at 56 rows with no pagination controls; real `<table>` copy button is inserted but hidden/not click-ready in the chart samples fixture; dashboard table-like lists lack top-right list-level copy controls; Flux.live replace checkbox alignment smoke failed in the browser fixture.

## Current Snapshot Files

- `site_audit/baseline.json`: initial known-good snapshot collected 2026-05-24 with Django test client/live-server fallback; baseline currently records `/` redirecting to `/setup/` in that environment.
- `site_audit/latest.json`: cleanup audit fixture snapshot collected 2026-05-24; Command Center renders with seeded data and is therefore environment-different from the current setup-page baseline.
- `site_audit/diffs.md`: current route/environment drift plus cleanup findings; baseline was not changed.

## Next Audit Actions

- If the user wants Command Center as known-good, request explicit approval before re-baselining away from the current setup-page baseline.
- Re-run the cleanup audit after table/list copy and Flux.serve pagination follow-up.
- Run a persistent `flux start --web-mode dev` audit when the local dev database can render Command Center with representative runtime data.
