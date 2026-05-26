# Site Audit

## Scope
Target URL: `http://localhost:49963` using `django StaticLiveServerTestCase fixture dashboard`. Routes/surfaces checked: dashboard summary plus bridges/sim-config/live/trace/serve detail/configure modes, `/charts/`, `/charts/?card=trace-paths&mode=detail`, `/charts/wells/`, and `/charts/?card=trace-samples&mode=detail`. Viewports: desktop 1280x900 and mobile 390x844. Baseline used: `site_audit/baseline.json` for route-level comparison; baseline was not changed.

## Executive Summary
Cleanup audit completed with browser availability `True`. High/blocker findings: 0; medium findings: 3. Confirmed cleanup wins include bridge WebDev URL/help wording, live stale source context, chart dashboard link bounding, and charts path pagination. Remaining drift/open cleanup is primarily unbounded Flux.serve observed-health rows plus copy-affordance gaps: inserted real-table copy controls were not visible/click-ready in the fixture, and dashboard table-like div lists still lack top-right list-level copy controls.

## Commands Run
- `uv run python manage.py check` in `/home/bobby/Projects/11006-PRW-flux/web/Flux`: passed.
- `uv run pytest -q ../../site_audit/test_playwright_cleanup_audit.py` in `/home/bobby/Projects/11006-PRW-flux/web/Flux`: passed.

## Baseline Status
Baseline path: `site_audit/baseline.json`. Latest snapshot path: `site_audit/latest.json`. Baseline changed: false. Comparison result: 12 route/environment drift item(s), mostly because the cleanup audit fixture renders Command Center while the current baseline records `/` redirecting to `/setup/`.

## Findings
- **MEDIUM — Flux.serve observed health list is unbounded**: 56 observed health rows; pagination_controls=0 Minimal direction: Paginate or otherwise bound long service/detail lists.
- **LOW — Flux.live replace checkbox alignment needs review**: {"default_scope_value": "Fluxolot", "default_scope_placeholder": "Fluxolot", "replace_checkbox_row_present": true, "replace_checkbox_aligned_smoke": false, "replace_checkbox_label_text": "Replace existing cards for imported scopes Updates the imported scope definitions without deleting runtime values."} Minimal direction: Keep the checkbox and explanatory text visually aligned as a single checkbox row.
- **MEDIUM — Real table copy affordance is hidden or not click-ready**: {"route": "/charts/?card=trace-samples&mode=detail", "table_count": 1, "table_copy_button_count": 1, "table_copy_button_visible": false, "table_copy_click_attempted": false, "copy_popover": ""} Minimal direction: Make inserted table copy buttons visible, focusable, and click-ready at the table top-right.
- **MEDIUM — Dashboard table-like lists lack table-level copy affordance**: [{"label": "Ignition Bridges list", "selector": "#bridges-comp-focus .bridge-mini-list", "row_count": 1, "focus_copy_button_count": 1, "table_copy_button_count": 0}, {"label": "OPC server runtime list", "selector": "#sim-config-comp-focus .stale-list", "row_count": 6, "focus_copy_button_count": 1, "table_copy_button_count": 0}, {"label": "Flux.live stale recovery list", "selector": "#live-comp-focus .stale-list", "row_count": 3, "focus_copy_button_count": 1, "table_copy_button_count": 0}, {"label": "Flux.charts dashboard links list", "selector": "#trace-comp-focus .stale-list", "row_count": 2, "focus_copy_button_count": 1, "table_copy_button_count": 0}, {"label": "Flux.serve observed health list", "selector": "#serve-comp-focus .stale-list", "row_count": 56, "focus_copy_button_count": 1, "table_copy_button_count": 0}] Minimal direction: Either convert representative table-like lists to real copyable tables or add list-level top-right copy controls distinct from the focus/card copy widget.

## Confirmed Cleanup Checks
- Ignition Bridges: detail copy reproduced as working (`copy_button_count=1`, first popover contains table-copy message=True, second popover contains LLM message=True); configure base URL value `http://localhost:8088/system/webdev/flux` does not contain admin=True; token/remove help present=True; build-string title=`Ignition version/build reported by Fluxy getVersion. The b-number is Ignition's build identifier.`.
- Runtime service observability: OPC PID/port visible=True; stale heartbeat labeling visible=True; Flux.serve PID/port visible=True; stale/unknown observed-health evidence visible=True; observed-health rows=56 with pagination_controls=0.
- Flux.live cleanup: stale row source context visible=True; legacy missing `Flux Field` rows isolated=True; default scope value/placeholder=`Fluxolot`/`Fluxolot`; replace checkbox row present/aligned=False.
- Flux.charts cleanup: dashboard detail Open links=2 and `chart-055` absent from dashboard detail=True; chart CSV `What is this?` and example visible=True; `/charts/` path pagination next/previous worked=True with `chart-055` on page 2 only=True.
- Table copy cleanup: real table route `/charts/?card=trace-samples&mode=detail` has tables=1 and inserted copy buttons=1, but visible/click-ready=False; representative dashboard table-like list copy gaps are detailed in Findings.

## Comp Surface Coverage
- Real glyph-control clicks attempted: 14; clicked: 14; failed/missing: 0.
- `bridges` `detail`: clicked surface=detail focus=bridges-comp-focus anchor=True active_pressed=1 other_summary=4 hx-target=#dashboard-comp-surface hx-select=#dashboard-comp-surface.
- `bridges` `configure`: clicked surface=configure focus=bridges-comp-focus anchor=True active_pressed=1 other_summary=4 hx-target=#dashboard-comp-surface hx-select=#dashboard-comp-surface.
- `bridges` `summary`: clicked surface=summary focus= anchor=False active_pressed=1 other_summary=4 hx-target=#dashboard-comp-surface hx-select=#dashboard-comp-surface.
- `sim-config` `detail`: clicked surface=detail focus=sim-config-comp-focus anchor=True active_pressed=1 other_summary=4 hx-target=#dashboard-comp-surface hx-select=#dashboard-comp-surface.
- `sim-config` `configure`: clicked surface=configure focus=sim-config-comp-focus anchor=True active_pressed=1 other_summary=4 hx-target=#dashboard-comp-surface hx-select=#dashboard-comp-surface.
- `sim-config` `summary`: clicked surface=summary focus= anchor=False active_pressed=1 other_summary=4 hx-target=#dashboard-comp-surface hx-select=#dashboard-comp-surface.
- `live` `detail`: clicked surface=detail focus=live-comp-focus anchor=True active_pressed=1 other_summary=4 hx-target=#dashboard-comp-surface hx-select=#dashboard-comp-surface.
- `live` `configure`: clicked surface=configure focus=live-comp-focus anchor=True active_pressed=1 other_summary=4 hx-target=#dashboard-comp-surface hx-select=#dashboard-comp-surface.
- `live` `summary`: clicked surface=summary focus= anchor=False active_pressed=1 other_summary=4 hx-target=#dashboard-comp-surface hx-select=#dashboard-comp-surface.
- `trace` `detail`: clicked surface=detail focus=trace-comp-focus anchor=True active_pressed=1 other_summary=4 hx-target=#dashboard-comp-surface hx-select=#dashboard-comp-surface.
- `trace` `configure`: clicked surface=configure focus=trace-comp-focus anchor=True active_pressed=1 other_summary=4 hx-target=#dashboard-comp-surface hx-select=#dashboard-comp-surface.
- `trace` `summary`: clicked surface=summary focus= anchor=False active_pressed=1 other_summary=4 hx-target=#dashboard-comp-surface hx-select=#dashboard-comp-surface.
- `serve` `detail`: clicked surface=detail focus=serve-comp-focus anchor=True active_pressed=1 other_summary=4 hx-target=#dashboard-comp-surface hx-select=#dashboard-comp-surface.
- `serve` `summary`: clicked surface=summary focus= anchor=False active_pressed=1 other_summary=4 hx-target=#dashboard-comp-surface hx-select=#dashboard-comp-surface.

## Accessibility And HTMX Notes
- Mode controls were located by role/name (`Show summary view`, `Show detail view`, `Show configure view`) and clicked rather than by coordinates. Console warnings/errors: 0; failed requests: 0.
- Real table copy affordance insertion was observed on `/charts/?card=trace-samples&mode=detail`, but the inserted control was not visible/click-ready in the fixture. Dashboard table-like lists still rely on focus/card copy widgets rather than table/list-level top-right copy controls.

## Blockers
- No browser/tooling blocker. The comparison baseline is environment-limited because it records initial setup, not the seeded Command Center fixture used for cleanup verification.

## Recommended Next Moves
- Add pagination/bounding for long Flux.serve observed-health rows or explicitly cap dashboard detail rows with a link to the serve page.
- Decide whether dashboard div-based table-like lists should become real tables or receive a generic list-level copy affordance; current `site.js` only covers real `<table>` elements.
- Once the running dev database is stable and setup-complete, create a user-approved Command Center baseline; do not overwrite `baseline.json` silently.
