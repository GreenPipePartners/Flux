# Native Installer

Flux is installed as one platform. The native installer is modular internally so a failed host operation can be dry-run, resumed, or isolated by stage, but it does not install partial Flux feature sets.

Supported target families:

- Ubuntu/Debian through `apt-get`
- RHEL/Rocky/Alma/CentOS/Fedora through `dnf` or `yum`

## Quick Start

Always inspect the plan first:

```bash
python3 install/flux_installer.py --dry-run
```

Install and start Flux:

```bash
sudo python3 install/flux_installer.py --start
```

The installer creates:

- `/opt/flux/app` for the Flux source tree
- `/opt/flux/venv` for the uv-managed Python environment
- `/opt/flux/vendor` for managed vendor payloads such as QuestDB
- `/etc/flux/flux.env` for Postgres-first runtime configuration
- `/var/lib/flux` for Flux runtime state
- `/var/lib/flux/questdb` for QuestDB data
- `/var/lib/flux/field-agent` for FieldAgent runtime config and PKI
- systemd units under `/etc/systemd/system`

## Transferable Deploy Contract

The native installer is the target-host execution engine for the GreenPipe deployment contract. The public bootstrap entrypoint is:

```text
https://greenpipe.partners/install
```

The current release artifact root is:

```text
https://greenpipe.partners/release/flux/0.1.0/
```

The release manifest points at:

```text
https://greenpipe.partners/release/flux/0.1.0/flux-deploy.py
https://greenpipe.partners/release/flux/0.1.0/flux-0.1.0.tar.zst
https://greenpipe.partners/release/flux/0.1.0/flux-0.1.0.tar.zst.sha256
https://greenpipe.partners/release/flux/0.1.0/flux-0.1.0.tar.zst.sig
```

See [Deployment Contract](deployment-contract.md) for the website/manifest/artifact boundary. GreenPipe publishes deployment intent and immutable artifacts; the target host executes the installer locally.

## Installer Stages

List stages:

```bash
python3 install/flux_installer.py --list-stages
```

Current stages:

- `preflight`: validate distro, source tree, and privileges
- `system-packages`: install OS packages
- `uv`: install `uv` if absent
- `user`: create the `flux` system user/group
- `directories`: create platform directories
- `source`: copy the current source tree into `/opt/flux/app`
- `python`: run `uv sync --frozen --no-dev` into `/opt/flux/venv`
- `postgres`: initialize local Postgres and create Flux DB/role
- `env`: render `/etc/flux/flux.env`
- `systemd`: render Flux systemd units
- `database`: run `migrate` and `flux_bootstrap`
- `enable`: enable systemd services
- `start`: start Flux services when `--start` is supplied

Run only selected stages:

```bash
sudo python3 install/flux_installer.py --stage env --stage systemd --force-env
```

## Postgres Contract

Flux is Postgres-first. The installer either creates a local Postgres database or uses an external `DATABASE_URL`.

Local default:

```text
postgres://flux:<generated-password>@localhost:5432/flux
```

External Postgres:

```bash
sudo python3 install/flux_installer.py \
  --database-url 'postgres://flux:secret@db-host:5432/flux' \
  --skip-postgres-setup \
  --start
```

The database stage runs:

```bash
python web/Flux/manage.py migrate --noinput
python web/Flux/manage.py flux_bootstrap
```

`flux_bootstrap` owns runtime defaults that should not be hidden in migrations: scheduler config, refresh lanes, schematics catalog defaults, and default bridge config.

## Systemd Units

The installer renders these units:

- `flux.target`
- `flux-web.service`
- `flux-questdb.service`
- `flux-serve-monitor.service`
- `flux-sim-worker.service`
- `flux-field-supervisor.service`
- `flux-trace-worker.service`
- `flux-sampling-worker.service`

Check status:

```bash
systemctl status flux.target
systemctl status flux-web.service
journalctl -u flux-web.service -f
```

## Package Notes

The system package stage requests `dotnet-sdk-10.0` because the current FieldAgent supervisor still runs the C# project through `dotnet run`. If the distro repositories do not provide this package, install the Microsoft package repository or install the .NET SDK manually, then rerun with:

```bash
sudo python3 install/flux_installer.py --skip-system-packages
```

This is an installer-stage limitation, not a Flux module split. The long-term target is to publish FieldAgent as a native runtime artifact during packaging.
