# Flux Native Installer

Run a dry-run first:

```bash
python3 install/flux_installer.py --dry-run
```

Install on Ubuntu/RHEL-family hosts:

```bash
sudo python3 install/flux_installer.py --start
```

GreenPipe-hosted installs use the standalone deploy runner:

```bash
sudo python3 flux-deploy.py apply --manifest-url https://greenpipe.partners/api/flux/deployments/dep_123/manifest --claim-token TOKEN --json
```

See `docs/native-installer.md` for stage details and external Postgres usage.
