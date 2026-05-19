# Flux Docs

Flux is performance-first Ignition companion tooling. If a path creates unnecessary Ignition IO, browser IO, or database churn, it does not fit Flux.

Start here:

- `docs/operator-guide.md`: local `flux` CLI, background service, dashboard, and health workflow.
- `docs/flux-architecture.md`: high-level system boundaries and ownership.
- `docs/ignition-dev-cell.md`: managed local Ignition dev-cell commands.
- `docs/live-extraction.md`: live-to-sim tag/history extraction trial and cleanup limits.
- `docs/trace-architecture.md`: uPlot trace JavaScript architecture and performance rules.

Project-specific app docs:

- `web/Flux/README.md`: Django app setup, local database, sim provider workflow, Trace basics.
- `web/Flux/docs/architecture-roadmap.md`: Django app roadmap and experimental boundaries.

Current local operator loop:

```bash
flux intro
flux install-service
flux start
flux doctor
```

Current field simulation loop from `tag_data/`:

```bash
flux field import-tag-data Tag_02 --devices "tag_data/tag_data/tag_02 devices.txt" --tags tag_data/tag_data/tags02.json
flux field materialize --provider Tag_02
FLUX_FIELD_AGENT_MODE=supervised flux start
flux field configure-ignition --tag-provider default --tag-folder FieldAgent
flux doctor
```

Main local URLs:

```text
Flux web UI:      http://localhost:8000/
Live view:        http://localhost:8000/live/
Trace:            http://localhost:8000/trace/
Ignition Gateway: http://localhost:8088/web/home
Fluxy bridge:     http://localhost:8088/system/webdev/flux
```
