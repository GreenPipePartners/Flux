# Flux.test

`test/` is the top-level Flux.test workspace: a lightweight, report-only acceptance spine for Flux suites.

The first pass does not run product-fixing automation. It parses `manifest.toml`, validates suite definitions, and reports the commands, environment gates, services touched, cleanup expectations, and destructive scope for each suite.

## Usage

```bash
uv run python test/runner.py
uv run python test/runner.py fluxolot-fishtank closed-loop
uv run python test/runner.py --json
```

## Suite Contract

Each `[[suite]]` in `manifest.toml` declares:

- `name`
- `description`
- `command`
- `cwd`
- `required_env`
- `timeout_seconds`
- `external_services`
- `cleanup_expectations`
- `destructive_scope`

`status` is computed by the runner:

- `defined`: the suite is present and required environment variables are set or not required.
- `blocked`: the suite is present but one or more required environment variables are missing.

## Boundaries

This workspace should describe or report suite readiness first. It should not auto-edit product code, deploy Ignition resources, activate services, or clean up data unless a future explicit runner mode is added.

Fluxolot Fishtank is persistent verification infrastructure. Tests may create temporary live, trace, or sim configuration around it, but cleanup must not delete Fluxolot Fishtank unless explicitly requested.
