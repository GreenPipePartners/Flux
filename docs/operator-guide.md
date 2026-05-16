# Flux Operator Guide

This guide covers the local operator workflow built around the top-level `flux` command.

## CLI

Install or refresh the user service and CLI symlink:

```bash
./scripts/flux-service-install.sh
```

This installs:

- `~/.config/systemd/user/flux-stack.service`
- `~/.local/bin/flux` symlinked to `scripts/flux`

Show the getting-started intro:

```bash
flux
flux intro
```

Common commands:

```bash
flux start
flux stop
flux status
flux logs
flux open
flux doctor
```

Ignition dev-cell commands:

```bash
flux ignition info
flux ignition doctor
flux ignition deploy-fluxy
flux ignition request-scan
flux ignition open
```

## Background Service

`flux-stack.service` runs the local development stack in the background:

- Django web app on `http://localhost:8000/`
- FieldAgent OPC UA simulator on `opc.tcp://localhost:4840/flux/field`
- demo reader that reads Ignition through Fluxy and writes latest values into Flux

The service runs `scripts/flux-start.sh`.

The launcher intentionally:

- runs migrations
- repairs Postgres sequences for copied legacy IDs
- exports FieldAgent config
- starts Django with `--noreload -6 [::]:8000` so `localhost` works on IPv4 and IPv6
- waits until Django responds before declaring the stack ready
- keeps all child services under one cleanup boundary

Start/stop/status wrappers:

```bash
./scripts/flux-service-start.sh
./scripts/flux-service-stop.sh
./scripts/flux-service-status.sh
./scripts/flux-service-logs.sh
```

The desktop app launcher entries are:

- `Flux Stack Start`
- `Flux Stack Stop`

## Dashboard

The main page is an operator console, not a branding page.

It shows:

- runtime tag readiness
- latest read freshness
- FieldAgent port/config state
- Live Ignition Bridge state
- stale tag recovery actions

The stale recovery action performs one Fluxy `read_blocking([...])` block read for the stale set, then updates `LatestTagValue` and `TagSample`. Avoid per-tag read loops.

The Live Ignition Bridge configuration is stored in Django as `dashboard.IgnitionBridgeConfig`.

Token behavior:

- token is never rendered back into HTML
- blank token input keeps the existing token
- `Clear stored token` explicitly clears it
- `Test connection` calls Fluxy `util_get_version`

## Health

Run:

```bash
flux doctor
```

The health check currently covers:

- user systemd service state
- Flux web response
- FieldAgent OPC UA port
- runtime tag count, stale count, bad quality count, and latest read age
- Live Ignition Bridge token/config and live Ignition version probe
- historian datasource type/status
- Ignition Gateway and Fluxy WebDev readiness

Architecture boundary:

- `scripts/flux` is the operator CLI and process-orchestration boundary.
- `dashboard.management.commands.flux_doctor_state` emits Django/app health as JSON.
- `dashboard.services` owns runtime/bridge state calculations used by both the dashboard and doctor-state command.
- Fluxy owns Gateway and datasource probes.
- Django request handlers should not directly own long-lived process supervision.

Known good output ends with:

```text
Flux is healthy.
```

## Windows

Windows foreground startup exists:

```cmd
scripts\flux-start.cmd
```

Windows background service management is not wired yet. The repo contains placeholder `.cmd` service scripts that fail clearly instead of pretending Windows background service support exists.

## Optional Browser Tests

Trace interaction tests use Playwright and are gated behind `FLUX_PLAYWRIGHT=1`.

```bash
cd web/Flux
uv run python -m playwright install chromium
FLUX_PLAYWRIGHT=1 DATABASE_URL= uv run pytest src/flux/trace/test_e2e_playwright.py -q
```
