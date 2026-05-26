# Flux.test

`test/` is the top-level Flux.test workspace: a lightweight acceptance spine for Flux suites.

The default mode does not run product-fixing automation. It parses `manifest.toml`, validates suite definitions, and reports the commands, environment gates, services touched, cleanup expectations, and destructive scope for each suite. Explicit `--execute` mode runs the selected suites sequentially so tester agents can cover more ground with fewer tool calls.

## Usage

```bash
uv run python test/runner.py
uv run python test/runner.py fluxolot-fishtank closed-loop
uv run python test/runner.py --json
uv run python test/runner.py --list-profiles
uv run python test/runner.py --profile fast --execute
uv run python test/runner.py --profile web --execute --json
uv run python test/runner.py activate-ignition --execute
uv run python test/runner.py --live-audit-env --profile e2e --profile live --execute
```

## Tester Shortcuts

Profiles are the tester-agent shortcut layer. They reduce many manual commands into one safe, sequential runner invocation.

- `fast`: Django system check plus root, mine, build, sim non-integration, and Fluxy non-integration tests.
- `web`: Django system check plus the main web/Django suites that use the test database.
- `e2e`: browser smoke suites gated by `FLUX_PLAYWRIGHT`.
- `live`: live Ignition/Fluxy/FieldAgent integration suites gated by live-service env vars.
- `audit`: broad audit profile combining fast, web, e2e, and live suite definitions.

Use `--profile` more than once to combine bundles. Suite names passed positionally are appended after profile suites. Duplicate suites are deduplicated in first-seen order.

Recommended tester-agent commands:

```bash
uv run python test/runner.py --profile fast --execute
uv run python test/runner.py --profile web --execute
uv run python test/runner.py --profile audit --json
uv run python test/runner.py --live-audit-env --profile e2e --profile live --execute
```

For a complete live audit, use `--live-audit-env` instead of shell-sourcing `.env` files. It safely loads project `.env` files when present, sets `FLUXY_BASE_URL` to the local WebDev default when missing, and enables `FLUX_PLAYWRIGHT=1` plus `FLUX_FULL_INTEGRATION=1`. `FLUXY_TOKEN` must still be present in the process environment, a loaded env file, or an explicit `--env FLUXY_TOKEN=...` value.

If a live run reports `Gateway Trial Expired` or Fluxy HTTP 402 `Trial Expired`, run `uv run python test/runner.py activate-ignition --execute` from the repository root, then retry the focused live suite. This invokes `scripts/activate_ignition_selenium.py` through the auditable Flux.test manifest with transient Selenium support, without changing dependency files.

Flux.test treats zero-test and all-skipped successful subprocess output as a failed suite. Optional live surfaces should be modeled as explicit suites with `required_env` gates instead of hidden `pytest.skip` success. For example, PostgreSQL-backed Fluxy integration lives in `integration-fluxy-postgres` and is blocked unless `FLUXY_POSTGRES_ENABLED` is present.

The main Flux CLI does not yet expose `flux test`. Until it does, use `uv run python test/runner.py ...` directly and allowlist that command for tester agents.

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

This workspace should describe or run suite readiness first. It should not auto-edit product code, deploy Ignition resources, activate services, or clean up data unless a future explicit runner mode is added.

Fluxolot Fishtank is persistent verification infrastructure. Tests may create temporary live, trace, or sim configuration around it, but cleanup must not delete Fluxolot Fishtank unless explicitly requested.
