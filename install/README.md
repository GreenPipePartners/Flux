# Flux Native Installer

Run a dry-run first:

```bash
python3 install/flux_installer.py --dry-run
```

Install on Ubuntu/RHEL-family hosts:

```bash
sudo python3 install/flux_installer.py --start
```

GreenPipe-hosted installs should use `fluxup`:

```bash
uvx fluxup init
```

Fresh interactive local Postgres installs prompt for the Flux database password. Press Enter to generate one. Reruns reuse `/etc/flux/flux.env` unless `--force-env` is supplied.

The standalone deploy runner remains a compatibility fallback:

```bash
sudo python3 flux-deploy.py apply --manifest-url https://greenpipe.partners/api/flux/deployments/dep_123/manifest --claim-token TOKEN --json
```

See `docs/native-installer.md` for stage details and external Postgres usage.
