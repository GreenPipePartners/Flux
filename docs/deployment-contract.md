# Deployment Contract

Flux deployment is split into three boundaries:

- GreenPipe website: deployment control plane and release publisher.
- Release artifact: immutable Flux platform bundle.
- Target host: Ubuntu/RHEL execution plane running the native installer locally.

The website should publish install intent and immutable artifacts. It should not act as a remote root shell for arbitrary commands.

## Bootstrap Entrypoint

The public install entrypoint is:

```text
https://greenpipe.partners/install
```

This endpoint is the human/operator bootstrap surface. It may return a short install page, a deploy runner download, or a one-line command, but the command must resolve to a typed Flux deployment flow.

Recommended operator command shape:

```bash
sudo python3 flux-deploy.py apply \
  --manifest-url https://greenpipe.partners/api/flux/deployments/dep_123/manifest \
  --claim-token <one-time-token> \
  --json
```

For a simple no-account public install path, `https://greenpipe.partners/install` may emit a manifest that points at the current release artifact.

## Release Artifact URLs

The current Flux release artifact root is:

```text
https://greenpipe.partners/release/flux/0.1.0/
```

Required files for the `0.1.0` release:

```text
https://greenpipe.partners/release/flux/0.1.0/flux-deploy.py
https://greenpipe.partners/release/flux/0.1.0/flux-deploy.py.sha256
https://greenpipe.partners/release/flux/0.1.0/flux-deploy.py.sig
https://greenpipe.partners/release/flux/0.1.0/flux-0.1.0.tar.zst
https://greenpipe.partners/release/flux/0.1.0/flux-0.1.0.tar.zst.sha256
https://greenpipe.partners/release/flux/0.1.0/flux-0.1.0.tar.zst.sig
```

The canonical path is `/release/...`. If `/realease/...` is ever exposed by mistake, it should redirect to `/release/...` rather than become part of the contract.

## Manifest Contract

Deployment manifests identify what Flux release should be installed and how the target host should configure it.

```json
{
  "apiVersion": "flux.greenpipe.partners/v1",
  "kind": "FluxInstall",
  "metadata": {"deployment_id": "dep_123", "site": "customer-a"},
  "spec": {
    "release": {
      "version": "0.1.0",
      "artifact_url": "https://greenpipe.partners/release/flux/0.1.0/flux-0.1.0.tar.zst",
      "sha256": "<hex-digest>",
      "checksum_url": "https://greenpipe.partners/release/flux/0.1.0/flux-0.1.0.tar.zst.sha256",
      "signature_url": "https://greenpipe.partners/release/flux/0.1.0/flux-0.1.0.tar.zst.sig"
    },
    "target": {"allowed_hosts": "localhost,127.0.0.1", "web_bind": "0.0.0.0:8000"},
    "database": {"mode": "local"},
    "services": {"enable": true, "start": true, "web_workers": 8, "web_threads": 2, "field_agent_base_port": 4850}
  }
}
```

For external Postgres, `database.mode` should be `external` and the deploy runner should resolve the database URL from a secret value, not from a logged plain-text manifest.

## Release Bundle Shape

The source release bundle should unpack to a complete Flux source tree with the installer and lockfile present:

```text
flux-0.1.0/
  pyproject.toml
  uv.lock
  install/
  scripts/
  web/Flux/
  fluxy/
  sim/
  mine/
  build/
  deep/
  field/Flux.FieldAgent/
```

The bundle must exclude local state, secrets, virtual environments, caches, generated media, and runtime databases.

## Target Host Execution

The deploy runner downloads the artifact, verifies the manifest checksum and release signature, unpacks the bundle, and executes the native installer on the target host:

```bash
sudo python3 install/flux_installer.py --start
```

The native installer owns distro detection, system packages, uv sync, Postgres setup, environment rendering, systemd units, migrations, bootstrap defaults, and service start.

## Status Events

The target host should report deployment progress back to GreenPipe as stage events:

```json
{
  "deployment_id": "dep_123",
  "stage": "systemd",
  "state": "running",
  "message": "Rendering Flux systemd units",
  "timestamp": "2026-06-21T12:00:00Z"
}
```

The event stream is observability only. The target host remains responsible for local execution and verification.
