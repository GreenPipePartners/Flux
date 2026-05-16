# Flux Ignition Dev Cell

The Flux Ignition dev cell is a known local Ignition environment that Flux can inspect and provision.

Current scope is intentionally narrow:

- Check that the Ignition Gateway is reachable.
- Check that Fluxy WebDev is deployed and authenticated.
- Deploy or refresh Fluxy WebDev resources into a project export.
- Request an Ignition project scan after deployment.

Flux does not yet install Ignition from scratch. Start with an already-running Gateway.

## Defaults

```text
Gateway URL:      http://localhost:8088
Fluxy base URL:   http://localhost:8088/system/webdev/flux
Project export:   web/ignition_flux_project
Fluxy token:      FLUXY_TOKEN from web/Flux/.env
```

Override with environment variables when needed:

```bash
export IGNITION_GATEWAY_URL=http://localhost:8088
export FLUXY_BASE_URL=http://localhost:8088/system/webdev/flux
export FLUXY_PROJECT_LOCATION=/path/to/ignition/project/export
export FLUXY_TOKEN=your-token
```

## Commands

Show configured dev-cell paths and URLs:

```bash
flux ignition info
```

Check Gateway and Fluxy WebDev readiness:

```bash
flux ignition doctor
```

Check the whole local Flux stack plus the Ignition dev cell:

```bash
flux doctor
```

Deploy or refresh Fluxy WebDev resources and request a project scan:

```bash
flux ignition deploy-fluxy
```

Request only a project scan:

```bash
flux ignition request-scan
```

Open the Gateway home page:

```bash
flux ignition open
```

## Direction

This is the first managed-cell slice. The next useful layers are:

- `flux doctor` for whole-stack checks: local service, ports, Postgres, FieldAgent, Gateway, Fluxy.
- `flux ignition configure-demo` to create the known demo OPC/tag setup through Fluxy.
- `flux ignition reset-demo-cell` to return a Gateway to a known-good demo state.
- Windows VM smoke checks that run these same commands inside the target OS.

Keep the boundary clear: systemd owns whether the local Flux stack is running; Fluxy owns safe Gateway automation; `flux.serve` should grow into domain lifecycle/status, not raw process ownership from web requests.
