# Flux

Flux is a performance-first Ignition companion stack for fast local operations views, simulation, tracing, and live-to-sim extraction workflows.

Start with the docs index:

```text
docs/README.md
```

Local operator quick start:

```bash
flux install-service
flux start
flux doctor
```

Local docs server:

```bash
flux docs serve
flux docs open
```

Root uv development commands:

```bash
uv sync
uv run python web/Flux/manage.py check
uv run python web/Flux/manage.py migrate
uv run mkdocs build --strict
```

Main local URLs:

```text
Flux web UI:      http://localhost:8000/
Docs server:      http://localhost:8001/
Spot view:        http://localhost:8000/spot/
Chart view:       http://localhost:8000/chart/
Ignition Gateway: http://localhost:8088/web/home
```

Major docs:

- `docs/operator-guide.md`: CLI, background service, dashboard, and health checks.
- `docs/operator-guide.md#field-simulation-operator-workflow`: tag_data import, materialize, supervised FieldAgent, Fluxy/Ignition config, and doctor workflow.
- `docs/flux-architecture.md`: system boundaries and ownership.
- `docs/ignition-dev-cell.md`: managed local Ignition dev-cell workflow.
- `docs/deep-openplc.md`: isolated Flux.Deep OpenPLC emulation workspace.
- `docs/live-extraction.md`: live-to-sim tag/history extraction and cleanup limits.
- `docs/charts-architecture.md`: uPlot chart architecture and performance rules.
- `web/Flux/README.md`: Django app setup and app-specific workflows.
