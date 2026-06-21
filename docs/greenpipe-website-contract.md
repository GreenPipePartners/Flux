# GreenPipe Website Contract

This contract lets `greenpipe.partners` publish Flux installs and Flux MkDocs documentation without becoming a remote shell or Flux runtime host.

## Deployment Interface

Public bootstrap route:

```text
GET https://greenpipe.partners/install
```

The install page should show a typed deploy command, not arbitrary shell generated per request. Do not show placeholder deployment IDs or tokens in the primary CTA.

First, the page must provide the deploy runner:

```text
GET https://greenpipe.partners/release/flux/0.1.0/flux-deploy.py
GET https://greenpipe.partners/release/flux/0.1.0/flux-deploy.py.sha256
GET https://greenpipe.partners/release/flux/0.1.0/flux-deploy.py.sig
```

Then a managed install command can be generated from a real deployment record:

```bash
sudo python3 flux-deploy.py apply \
  --manifest-url https://greenpipe.partners/api/flux/deployments/dep_123/manifest \
  --claim-token <one-time-token> \
  --json
```

Required release files:

```text
GET https://greenpipe.partners/release/flux/0.1.0/flux-0.1.0.tar.zst
GET https://greenpipe.partners/release/flux/0.1.0/flux-0.1.0.tar.zst.sha256
GET https://greenpipe.partners/release/flux/0.1.0/flux-0.1.0.tar.zst.sig
```

Canonical path is `/release/...`. If `/realease/...` appears, redirect it to `/release/...`.

Manifest shape. The deploy runner consumes JSON; YAML may be shown as documentation only.

```json
{
  "apiVersion": "flux.greenpipe.partners/v1",
  "kind": "FluxInstall",
  "metadata": {"deployment_id": "dep_123"},
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
    "services": {"enable": true, "start": true}
  }
}
```

The target host downloads, verifies, unpacks, and runs:

```bash
sudo python3 install/flux_installer.py --start
```

## Deployment API

Minimum website API for managed installs:

```text
POST /api/flux/deployments
GET  /api/flux/deployments/{id}/manifest
POST /api/flux/deployments/{id}/events
POST /api/flux/deployments/{id}/complete
```

Event payload:

```json
{
  "deployment_id": "dep_123",
  "stage": "systemd",
  "state": "running",
  "message": "Rendering Flux systemd units",
  "timestamp": "2026-06-21T12:00:00Z"
}
```

## MkDocs Interface

Flux docs are static MkDocs output. The website should mount the built site, not rewrite the docs at request time.

Source inputs:

```text
mkdocs.yml
docs/
```

Build command:

```bash
uv run mkdocs build --strict
```

Build output:

```text
.runtime/site/
```

Recommended published docs routes:

```text
GET https://greenpipe.partners/docs/flux/0.1.0/
GET https://greenpipe.partners/docs/flux/latest/ -> redirect to /docs/flux/0.1.0/
```

Optional docs artifact files:

```text
GET https://greenpipe.partners/release/flux/0.1.0/flux-docs-0.1.0.tar.zst
GET https://greenpipe.partners/release/flux/0.1.0/flux-docs-0.1.0.tar.zst.sha256
GET https://greenpipe.partners/release/flux/0.1.0/flux-docs-0.1.0.tar.zst.sig
```

For production docs builds, set MkDocs `site_url` to the mounted docs URL before build:

```text
https://greenpipe.partners/docs/flux/0.1.0/
```

## Security Rules

- Website publishes typed install intent, immutable artifacts, checksums, signatures, docs, and status views.
- Website must not SSH into targets or execute arbitrary root shell strings.
- Target hosts execute the installer locally and report events back.
- Secrets must be claim-scoped or resolved by the target runner; do not expose database URLs in public release metadata.
