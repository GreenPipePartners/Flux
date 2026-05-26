# Documentation Core Area Files

Last updated: 2026-05-24 during runtime-health and charts documentation pass.

## Ownership

Docs Steward owns MkDocs documentation stewardship, surfaced-process capture, docs navigation hygiene, and UI documentation pointer alignment.

Docs Steward does not own runtime behavior, tests, migrations, models, service scripts, dependency manifests, generated data, Ignition configuration, or product logic.

## Agent-Domain Files

- `documentation/core_area_files.md` - this continuous documentation index.
- `documentation/agent_notices.md` - Coordinator-written notice inbox for next-run and long-term documentation handoffs.
- `documentation/daily/documentation_YYYY-MM-DD/documentation_YYYY-MM-DD.md` - append-only Docs Steward activity ledger.

## Published Docs Files

- `mkdocs.yml` - authoritative MkDocs navigation and docs build configuration.
- `docs/index.md` - docs landing page and documentation contract.
- `docs/operator-guide.md` - operator workflows and local service usage.
- `docs/flux-architecture.md` - system boundaries and ownership.
- `docs/live-extraction.md` - live extraction architecture notes.
- `docs/trace-architecture.md` - Trace demand and historical-time architecture.
- `docs/apps/*.md` - app behavior documentation.
- `docs/runbooks/*.md` - repeatable operations and recovery workflows.
- `docs/live-card-context.md` - Live card copy/export context contract.

Current high-value documentation homes:

- `docs/apps/dashboard.md` - dashboard readiness cards, Ignition Bridge token/build explanations, interface health, OPC runtime truth, and dashboard Flux.links anchors.
- `docs/apps/live.md` - cached Live state, sampler service contract, hot/warm/cold target contract, and stale/freshness operator checks.
- `docs/apps/serve.md` - service snapshots, FieldAgent runtime truth evidence, PID/port/heartbeat expectations, and interface sampler ownership.
- `docs/apps/opt.md` - runtime sampling, demand, hot/warm/cold planning, and block-read boundaries.
- `docs/apps/charts.md` - Charts operator surfaces, chart CSV import schema, and stress/navigation-well single-page workflow.
- `docs/charts-architecture.md` - chart cache/data-plane ownership, navigation-well stress restore path, and large chart-set pagination expectations.

## Documentation Pointer Files

Docs Steward may update documentation pointer values only in these application files:

- `web/Flux/src/flux/live/views.py`
- `web/Flux/src/flux/live/copy_context.py`
- `web/Flux/src/flux/serve/views.py`
- `web/Flux/src/flux/opt/views.py`
- `web/Flux/src/flux/sim/views.py`
- `web/Flux/src/flux/charts/views.py`
- `web/Flux/src/flux/nav/views.py`
- `web/Flux/src/flux/time/views.py`

Allowed pointer edits are limited to `docs_path=` values, copy-context docs URL constants, and equivalent documentation target strings. Behavior changes belong to Sam/Build or another specialist.

## Validation

Run from repo root when feasible:

```bash
uv run --project web/Flux mkdocs build --strict
```

Docs hygiene item fixed during setup: `mkdocs.yml` referenced missing `trace-architecture.md` and `apps/trace.md`; both pages were added, and existing Charts docs were added to nav.

## Process Contract

- Document current reality and target architecture separately when they differ.
- Prefer improving an existing page over adding a new page, unless the process needs a stable standalone contract.
- Add nav entries for new published docs pages.
- Do not place agent notes under `docs/`.
- Update Flux.links/copy-context docs pointers after the docs target exists.
