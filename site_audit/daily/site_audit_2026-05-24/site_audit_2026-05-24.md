# Site Audit Daily Log — 2026-05-24

## Session — Coordinator-note parameter update

- Timestamp: 2026-05-24 local date; exact local time not collected.
- Target URL: no live site audit was run. Next running-site target remains `http://127.0.0.1:8000/` via `flux start --web-mode dev`; fallback remains Django `pytest` live server/test client.
- Server mode: none started for this parameter-only update.
- Routes/surfaces checked this session: read the Site Auditor notice inbox and mapped the dashboard route/template selectors for `/`, `/?card=bridges&mode=*`, `/?card=sim-config&mode=*`, `/?card=live&mode=*`, `/?card=trace&mode=*`, and `/?card=serve&mode=*`. No browser reproduction was attempted.
- Browser/viewports: none this session. Next audit should smoke desktop `1280x900` and mobile `390x844`.
- Commands/tools run: read `site_audit/agent_notices.md`, `site_audit/baseline.json`, `site_audit/latest.json`, `site_audit/diffs.md`, `site_audit.md`, and `site_audit/test_playwright_initial_scrape.py`; searched/read `web/Flux/src/templates/dashboard/home.html` to map card IDs, copy controls, HTMX targets, and visible labels. No `flux start`, `manage.py check`, or pytest audit command was run.
- Audit parameters updated: created `site_audit/core_area_files.md` with coordinator-driven next-run parameters for notices `2026-05-24-coordinator-002`, `2026-05-24-coordinator-006`, `2026-05-24-coordinator-007`, `2026-05-24-coordinator-009`, and `2026-05-24-coordinator-011`.
- Baseline/drift status: `site_audit/baseline.json`, `site_audit/latest.json`, and `site_audit/diffs.md` were not modified; no drift comparison was performed.
- Findings: no confirmed regressions because this was not a running-site audit. Coordinator-reported issues are now parameterized as next-run audit checks.
- Blockers: actual reproduction still depends on a running Flux dev site with setup completed and fixture/runtime data for dashboard Command Center surfaces.
- Next audit actions: start Flux in dev mode when available, open the dashboard Command Center, exercise real Comp Surface glyph controls for `bridges`, `sim-config`, `live`, `trace`, and `serve`, verify the notice-specific UI/accessibility/table-copy expectations, and write `site_audit/latest.json`, `site_audit/diffs.md`, and `site_audit.md` with evidence.

## Session — Cleanup follow-behind browser audit

- Timestamp: 2026-05-24 local date; exact local time not collected.
- Target URL: Django `StaticLiveServerTestCase` live server recorded in `site_audit/latest.json` (`http://localhost:<ephemeral-port>`). Persistent Flux dev URL `http://127.0.0.1:8000/` was not used.
- Server mode: fixture-backed Django live server with setup-complete Command Center data; site was not started by the agent with `flux start`.
- Routes/surfaces checked: `/`; dashboard Comp Surface cards `bridges`, `sim-config`, `live`, `trace`, and `serve` in summary/detail/configure modes where supported; `/charts/?card=trace-paths&mode=detail` page 1 and page 2; `/charts/wells/`; `/charts/?card=trace-samples&mode=detail`.
- Browser/viewports: Chromium desktop `1280x900` for interaction audit; mobile smoke `390x844` for dashboard card/focus presence.
- Commands/tools run: `uv run python manage.py check` from `web/Flux` (passed); `uv run pytest -q ../../site_audit/test_playwright_cleanup_audit.py` from `web/Flux` (passed, with staticfiles directory and Django 6 URLField scheme warnings only).
- Drift findings: baseline comparison is environment-different because the current baseline records `/` redirecting to `/setup/`, while this run seeded a setup-complete Command Center. Confirmed cleanup wins: bridge detail copy popover/docs and two-stage copy work; bridge configure uses WebDev Fluxy URL and explains token/build string; OPC runtime PID/port and stale heartbeat evidence are visible; Flux.serve PID/port plus stale/unknown observed-health evidence are visible; Flux.live stale rows include source context and isolate missing `Flux Field` legacy rows; default live scope is `Fluxolot`; dashboard Flux.charts detail renders only two aggregate `Open` links; chart CSV import help has example layout; charts path pagination works with `chart-055` on page 2 only.
- Confirmed remaining issues: Flux.serve observed-health detail rendered 56 rows with no pagination/bounding controls; chart sample real-table copy button was inserted but hidden/not click-ready; representative dashboard table-like div lists have focus/card copy widgets but no table/list-level top-right copy button; Flux.live replace-checkbox alignment smoke failed in the browser fixture.
- Files updated: `site_audit/latest.json`, `site_audit/diffs.md`, `site_audit.md`, `site_audit/core_area_files.md`, this daily log, and notice outcomes in `site_audit/agent_notices.md`.
- Blockers: no browser/tooling blocker. Persistent dev-server audit remains unrun; current committed baseline is still setup-page based.
- Next audit actions: rerun after Flux.serve pagination/list bounding and table/list copy follow-up; ask explicitly before replacing `site_audit/baseline.json` with a Command Center known-good baseline.
