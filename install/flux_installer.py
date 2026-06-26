#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import os
import secrets
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit


REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


@dataclass(frozen=True)
class Distro:
    distro_id: str
    distro_like: tuple[str, ...]

    @property
    def family(self) -> str:
        ids = {self.distro_id, *self.distro_like}
        if ids & {"ubuntu", "debian"}:
            return "apt"
        if ids & {"rhel", "fedora", "centos", "rocky", "almalinux"}:
            return "dnf"
        return "unknown"


@dataclass(frozen=True)
class InstallerConfig:
    source_dir: Path
    app_dir: Path
    web_dir: Path
    venv_dir: Path
    config_dir: Path
    env_file: Path
    data_dir: Path
    log_dir: Path
    vendor_dir: Path
    questdb_dist_dir: Path
    questdb_data_dir: Path
    field_runtime_dir: Path
    systemd_dir: Path
    user: str
    group: str
    db_name: str
    db_user: str
    db_password: str
    database_url: str
    django_secret_key: str
    allowed_hosts: str
    csrf_trusted_origins: str
    web_bind: str
    web_workers: int
    web_threads: int
    field_agent_host: str
    field_agent_base_port: int
    skip_system_packages: bool
    skip_postgres_setup: bool
    force_env: bool
    enable: bool
    start: bool

    @property
    def web_src_dir(self) -> Path:
        return self.web_dir / "src"

    @property
    def manage_py(self) -> Path:
        return self.web_dir / "manage.py"


class CommandRunner:
    def __init__(self, *, dry_run: bool):
        self.dry_run = dry_run

    def run(
        self,
        command: list[str],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        display: str | None = None,
    ) -> None:
        text = " ".join(shlex.quote(part) for part in command)
        if cwd is not None:
            text = f"(cd {shlex.quote(str(cwd))} && {text})"
        self.note(display or text)
        if self.dry_run:
            return
        run_env = os.environ.copy()
        if env:
            run_env.update(env)
        subprocess.run(command, cwd=cwd, env=run_env, check=True)

    def shell(self, command: str, *, cwd: Path | None = None, display: str | None = None) -> None:
        text = command if cwd is None else f"(cd {shlex.quote(str(cwd))} && {command})"
        self.note(display or text)
        if self.dry_run:
            return
        subprocess.run(["bash", "-lc", command], cwd=cwd, check=True)

    def note(self, message: str) -> None:
        prefix = "DRY-RUN" if self.dry_run else "RUN"
        print(f"[{prefix}] {message}")


class InstallerStage:
    name = ""
    description = ""

    def run(self, cfg: InstallerConfig, distro: Distro, runner: CommandRunner) -> None:
        raise NotImplementedError


class PreflightStage(InstallerStage):
    name = "preflight"
    description = "Validate host, source tree, distro, and required privileges."

    def run(self, cfg: InstallerConfig, distro: Distro, runner: CommandRunner) -> None:
        if distro.family == "unknown":
            if runner.dry_run:
                runner.note(
                    "unsupported distro accepted for dry-run only: ID=%r ID_LIKE=%r"
                    % (distro.distro_id, ",".join(distro.distro_like))
                )
                return
            raise SystemExit(
                "Unsupported Linux distro ID=%r ID_LIKE=%r. Expected Ubuntu/Debian or RHEL-family."
                % (distro.distro_id, ",".join(distro.distro_like))
            )
        if not runner.dry_run and os.geteuid() != 0:
            raise SystemExit("Flux native install must run as root. Re-run with sudo, or use --dry-run.")
        required = [cfg.source_dir / "pyproject.toml", cfg.source_dir / "web" / "Flux" / "manage.py"]
        missing = [path for path in required if not path.exists()]
        if missing:
            raise SystemExit("Flux source tree is incomplete: %s" % ", ".join(str(path) for path in missing))
        runner.note("preflight ok: distro_family=%s source=%s" % (distro.family, cfg.source_dir))


class SystemPackagesStage(InstallerStage):
    name = "system-packages"
    description = "Install Ubuntu/RHEL OS packages required by Flux."

    APT_PACKAGES = (
        "ca-certificates",
        "curl",
        "git",
        "rsync",
        "python3",
        "python3-venv",
        "python3-pip",
        "postgresql",
        "postgresql-client",
        "openjdk-17-jre-headless",
        "dotnet-sdk-10.0",
    )
    DNF_PACKAGES = (
        "ca-certificates",
        "curl",
        "git",
        "rsync",
        "python3",
        "python3-pip",
        "postgresql",
        "postgresql-server",
        "java-17-openjdk-headless",
        "dotnet-sdk-10.0",
    )

    def run(self, cfg: InstallerConfig, distro: Distro, runner: CommandRunner) -> None:
        if cfg.skip_system_packages:
            runner.note("system package installation skipped")
            return
        if distro.family == "apt":
            runner.run(["apt-get", "update"])
            runner.run(["apt-get", "install", "-y", *self.APT_PACKAGES])
            return
        if distro.family == "unknown":
            if runner.dry_run:
                runner.note("system package stage skipped for unsupported dry-run host")
                return
            raise SystemExit("Unsupported distro for system package installation")
        manager = shutil.which("dnf") or shutil.which("yum") or "dnf"
        runner.run([manager, "install", "-y", *self.DNF_PACKAGES])


class UvStage(InstallerStage):
    name = "uv"
    description = "Install uv into /usr/local/bin when absent."

    def run(self, cfg: InstallerConfig, distro: Distro, runner: CommandRunner) -> None:
        if shutil.which("uv"):
            runner.note("uv already available at %s" % shutil.which("uv"))
            return
        runner.shell("curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh")


class UserStage(InstallerStage):
    name = "user"
    description = "Create the flux system user and group."

    def run(self, cfg: InstallerConfig, distro: Distro, runner: CommandRunner) -> None:
        nologin = "/usr/sbin/nologin" if Path("/usr/sbin/nologin").exists() else "/sbin/nologin"
        runner.shell(
            "getent group {group} >/dev/null || groupadd --system {group}; "
            "id -u {user} >/dev/null 2>&1 || useradd --system --gid {group} "
            "--home-dir {home} --shell {shell} {user}".format(
                group=shlex.quote(cfg.group),
                user=shlex.quote(cfg.user),
                home=shlex.quote(str(cfg.data_dir)),
                shell=shlex.quote(nologin),
            )
        )


class DirectoryStage(InstallerStage):
    name = "directories"
    description = "Create Flux app, config, data, vendor, and log directories."

    def run(self, cfg: InstallerConfig, distro: Distro, runner: CommandRunner) -> None:
        dirs = [
            cfg.app_dir,
            cfg.venv_dir,
            cfg.config_dir,
            cfg.data_dir,
            cfg.log_dir,
            cfg.vendor_dir,
            cfg.questdb_dist_dir,
            cfg.questdb_data_dir,
            cfg.field_runtime_dir,
        ]
        runner.run(["mkdir", "-p", *(str(path) for path in dirs)])
        runner.run(["chown", "-R", f"{cfg.user}:{cfg.group}", str(cfg.app_dir.parent), str(cfg.data_dir), str(cfg.log_dir)])
        runner.run(["chown", "root:%s" % cfg.group, str(cfg.config_dir)])
        runner.run(["chmod", "750", str(cfg.config_dir)])


class SourceStage(InstallerStage):
    name = "source"
    description = "Copy the current Flux source tree into /opt/flux/app."

    EXCLUDES = (
        ".git/",
        ".env",
        ".opencode/",
        ".venv/",
        ".runtime/",
        "__pycache__/",
        ".pytest_cache/",
        ".ruff_cache/",
        ".mypy_cache/",
        "node_modules/",
        "staticfiles/",
        "media/",
        "*.db",
        "*.pyc",
        "*.sqlite",
        "*.sqlite3",
    )

    def run(self, cfg: InstallerConfig, distro: Distro, runner: CommandRunner) -> None:
        if cfg.source_dir.resolve() == cfg.app_dir.resolve():
            runner.note("source already at app dir; rsync skipped")
            return
        command = ["rsync", "-a", "--delete"]
        for pattern in self.EXCLUDES:
            command.extend(["--exclude", pattern])
        command.extend([str(cfg.source_dir) + "/", str(cfg.app_dir) + "/"])
        runner.run(command)
        runner.run(["chown", "-R", f"{cfg.user}:{cfg.group}", str(cfg.app_dir)])


class PythonEnvironmentStage(InstallerStage):
    name = "python"
    description = "Build the Flux uv environment in /opt/flux/venv."

    def run(self, cfg: InstallerConfig, distro: Distro, runner: CommandRunner) -> None:
        runner.run(
            ["uv", "sync", "--frozen", "--no-dev"],
            cwd=cfg.app_dir,
            env={"UV_PROJECT_ENVIRONMENT": str(cfg.venv_dir)},
        )
        runner.run(["chown", "-R", f"{cfg.user}:{cfg.group}", str(cfg.venv_dir)])


class PostgresStage(InstallerStage):
    name = "postgres"
    description = "Initialize/start local Postgres and create the Flux role/database."

    def run(self, cfg: InstallerConfig, distro: Distro, runner: CommandRunner) -> None:
        if cfg.skip_postgres_setup:
            runner.note("local Postgres setup skipped; DATABASE_URL must point to an existing Postgres DB")
            return
        if distro.family == "dnf":
            runner.shell(
                "if command -v postgresql-setup >/dev/null 2>&1 && [ ! -f /var/lib/pgsql/data/PG_VERSION ]; "
                "then postgresql-setup --initdb; fi"
            )
        runner.run(["systemctl", "enable", "--now", "postgresql"])
        db_user = sql_literal(cfg.db_user)
        db_password = sql_literal(cfg.db_password)
        db_ident = sql_identifier(cfg.db_name)
        role_ident = sql_identifier(cfg.db_user)
        runner.shell(
            "runuser -u postgres -- psql -v ON_ERROR_STOP=1 -c "
            + shlex.quote(
                "DO $$ BEGIN "
                "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = %s) THEN "
                "CREATE ROLE %s LOGIN PASSWORD %s; "
                "ELSE ALTER ROLE %s WITH LOGIN PASSWORD %s; "
                "END IF; END $$;"
                % (db_user, role_ident, db_password, role_ident, db_password)
            ),
            display="runuser -u postgres -- psql ... # create/update Flux role password [redacted]",
        )
        runner.shell(
            "runuser -u postgres -- psql -v ON_ERROR_STOP=1 -tc "
            + shlex.quote("SELECT 1 FROM pg_database WHERE datname = %s" % sql_literal(cfg.db_name))
            + " | grep -q 1 || runuser -u postgres -- createdb --owner "
            + shlex.quote(cfg.db_user)
            + " "
            + shlex.quote(cfg.db_name)
        )
        runner.shell(
            "runuser -u postgres -- psql -v ON_ERROR_STOP=1 -d "
            + shlex.quote(cfg.db_name)
            + " -c "
            + shlex.quote("GRANT ALL PRIVILEGES ON DATABASE %s TO %s;" % (db_ident, role_ident))
        )


class EnvStage(InstallerStage):
    name = "env"
    description = "Render /etc/flux/flux.env with Postgres-first settings."

    def run(self, cfg: InstallerConfig, distro: Distro, runner: CommandRunner) -> None:
        if cfg.env_file.exists() and not cfg.force_env:
            runner.note("%s exists; env render skipped. Use --force-env to overwrite." % cfg.env_file)
            return
        content = render_template(
            TEMPLATE_DIR / "flux.env",
            {
                "ALLOWED_HOSTS": cfg.allowed_hosts,
                "APP_DIR": str(cfg.app_dir),
                "CSRF_TRUSTED_ORIGINS": cfg.csrf_trusted_origins,
                "DATABASE_URL": cfg.database_url,
                "DJANGO_SECRET_KEY": cfg.django_secret_key,
                "FIELD_AGENT_BASE_PORT": str(cfg.field_agent_base_port),
                "FIELD_AGENT_HOST": cfg.field_agent_host,
                "QUESTDB_DATA_DIR": str(cfg.questdb_data_dir),
                "QUESTDB_DIST_DIR": str(cfg.questdb_dist_dir),
                "RUNTIME_DIR": str(cfg.data_dir),
                "WEB_BIND": cfg.web_bind,
                "WEB_THREADS": str(cfg.web_threads),
                "WEB_WORKERS": str(cfg.web_workers),
            },
        )
        write_file(cfg.env_file, content, runner)
        runner.run(["chown", f"root:{cfg.group}", str(cfg.env_file)])
        runner.run(["chmod", "640", str(cfg.env_file)])


class StaticAssetsStage(InstallerStage):
    name = "static-assets"
    description = "Collect Django static assets for production web serving."

    def run(self, cfg: InstallerConfig, distro: Distro, runner: CommandRunner) -> None:
        manage = shlex.quote(str(cfg.manage_py))
        python = shlex.quote(str(cfg.venv_dir / "bin" / "python"))
        env_file = shlex.quote(str(cfg.env_file))
        app_dir = shlex.quote(str(cfg.app_dir))
        command = (
            "set -a; . {env_file}; set +a; cd {app_dir}; "
            "{python} {manage} collectstatic --noinput"
        ).format(env_file=env_file, app_dir=app_dir, python=python, manage=manage)
        runner.run(["runuser", "-u", cfg.user, "--", "bash", "-lc", command])


class SystemdStage(InstallerStage):
    name = "systemd"
    description = "Render Flux systemd units for web, workers, FieldAgent, and QuestDB."

    UNIT_FILES = (
        "flux.target",
        "flux-web.service",
        "flux-questdb.service",
        "flux-serve-monitor.service",
        "flux-sim-worker.service",
        "flux-field-supervisor.service",
        "flux-trace-worker.service",
        "flux-sampling-worker.service",
    )

    def run(self, cfg: InstallerConfig, distro: Distro, runner: CommandRunner) -> None:
        values = {
            "APP_DIR": str(cfg.app_dir),
            "ENV_FILE": str(cfg.env_file),
            "FIELD_AGENT_BASE_PORT": str(cfg.field_agent_base_port),
            "FIELD_AGENT_HOST": cfg.field_agent_host,
            "FIELD_RUNTIME_DIR": str(cfg.field_runtime_dir),
            "GROUP": cfg.group,
            "QUESTDB_DATA_DIR": str(cfg.questdb_data_dir),
            "QUESTDB_DIST_DIR": str(cfg.questdb_dist_dir),
            "USER": cfg.user,
            "VENV_DIR": str(cfg.venv_dir),
            "WEB_BIND": cfg.web_bind,
            "WEB_DIR": str(cfg.web_dir),
            "WEB_SRC_DIR": str(cfg.web_src_dir),
            "WEB_THREADS": str(cfg.web_threads),
            "WEB_WORKERS": str(cfg.web_workers),
        }
        for unit in self.UNIT_FILES:
            content = render_template(TEMPLATE_DIR / "systemd" / unit, values)
            write_file(cfg.systemd_dir / unit, content, runner)
        runner.run(["systemctl", "daemon-reload"])


class DatabaseStage(InstallerStage):
    name = "database"
    description = "Run clean migrations and Flux bootstrap defaults."

    def run(self, cfg: InstallerConfig, distro: Distro, runner: CommandRunner) -> None:
        manage = shlex.quote(str(cfg.manage_py))
        python = shlex.quote(str(cfg.venv_dir / "bin" / "python"))
        env_file = shlex.quote(str(cfg.env_file))
        app_dir = shlex.quote(str(cfg.app_dir))
        command = (
            "set -a; . {env_file}; set +a; cd {app_dir}; "
            "{python} {manage} migrate --noinput && "
            "{python} {manage} flux_bootstrap"
        ).format(env_file=env_file, app_dir=app_dir, python=python, manage=manage)
        runner.run(["runuser", "-u", cfg.user, "--", "bash", "-lc", command])


class EnableStage(InstallerStage):
    name = "enable"
    description = "Enable Flux systemd services at boot."

    def run(self, cfg: InstallerConfig, distro: Distro, runner: CommandRunner) -> None:
        if not cfg.enable:
            runner.note("systemd enable skipped")
            return
        runner.run(["systemctl", "enable", "flux.target"])
        for service in SystemdStage.UNIT_FILES:
            if service.endswith(".service"):
                runner.run(["systemctl", "enable", service])


class StartStage(InstallerStage):
    name = "start"
    description = "Start Flux through systemd."

    def run(self, cfg: InstallerConfig, distro: Distro, runner: CommandRunner) -> None:
        if not cfg.start:
            runner.note("systemd start skipped; use --start to launch Flux now")
            return
        runner.run(["systemctl", "start", "flux.target"])
        runner.run(["systemctl", "--no-pager", "--full", "status", "flux.target"])


STAGES: tuple[InstallerStage, ...] = (
    PreflightStage(),
    SystemPackagesStage(),
    UvStage(),
    UserStage(),
    DirectoryStage(),
    SourceStage(),
    PythonEnvironmentStage(),
    PostgresStage(),
    EnvStage(),
    StaticAssetsStage(),
    SystemdStage(),
    DatabaseStage(),
    EnableStage(),
    StartStage(),
)


def detect_distro() -> Distro:
    data: dict[str, str] = {}
    os_release = Path("/etc/os-release")
    if os_release.exists():
        for line in os_release.read_text(encoding="utf-8").splitlines():
            if "=" not in line or line.startswith("#"):
                continue
            key, value = line.split("=", 1)
            data[key] = value.strip().strip('"')
    return Distro(
        distro_id=data.get("ID", "unknown").lower(),
        distro_like=tuple(value.lower() for value in data.get("ID_LIKE", "").split()),
    )


def default_config(args: argparse.Namespace) -> InstallerConfig:
    source_dir = args.source_dir.resolve()
    app_dir = args.app_dir
    env_file = args.config_dir / "flux.env"
    existing_env = {} if args.force_env else read_env_values(env_file)
    database_url, db_password, skip_postgres_setup = resolve_database_config(args, existing_env)
    django_secret_key = args.django_secret_key or existing_env.get("DJANGO_SECRET_KEY") or secrets.token_urlsafe(48)
    return InstallerConfig(
        source_dir=source_dir,
        app_dir=app_dir,
        web_dir=app_dir / "web" / "Flux",
        venv_dir=args.venv_dir,
        config_dir=args.config_dir,
        env_file=env_file,
        data_dir=args.data_dir,
        log_dir=args.log_dir,
        vendor_dir=args.vendor_dir,
        questdb_dist_dir=args.vendor_dir / "questdb-dist",
        questdb_data_dir=args.data_dir / "questdb",
        field_runtime_dir=args.data_dir / "field-agent",
        systemd_dir=args.systemd_dir,
        user=args.user,
        group=args.group,
        db_name=args.db_name,
        db_user=args.db_user,
        db_password=db_password,
        database_url=database_url,
        django_secret_key=django_secret_key,
        allowed_hosts=args.allowed_hosts,
        csrf_trusted_origins=args.csrf_trusted_origins,
        web_bind=args.web_bind,
        web_workers=args.web_workers,
        web_threads=args.web_threads,
        field_agent_host=args.field_agent_host,
        field_agent_base_port=args.field_agent_base_port,
        skip_system_packages=args.skip_system_packages,
        skip_postgres_setup=args.skip_postgres_setup or skip_postgres_setup,
        force_env=args.force_env,
        enable=not args.no_enable,
        start=args.start,
    )


def resolve_database_config(args: argparse.Namespace, existing_env: dict[str, str]) -> tuple[str, str, bool]:
    if args.database_url:
        return args.database_url, database_url_password(args.database_url), True

    existing_database_url = existing_env.get("DATABASE_URL", "")
    if existing_database_url:
        existing_password = database_url_password(existing_database_url)
        if args.db_password and existing_password and args.db_password != existing_password:
            raise SystemExit(
                "--db-password does not match the existing %s; use --force-env to replace it"
                % (args.config_dir / "flux.env")
            )
        if is_local_database_url(existing_database_url, db_user=args.db_user, db_name=args.db_name):
            if not existing_password:
                raise SystemExit(
                    "existing local DATABASE_URL in %s does not include a password; use --force-env with --db-password"
                    % (args.config_dir / "flux.env")
                )
            return existing_database_url, existing_password, False
        return existing_database_url, existing_password, True

    db_password = args.db_password or prompt_local_db_password(args) or secrets.token_urlsafe(24)
    return local_database_url(args.db_user, db_password, args.db_name), db_password, False


def read_env_values(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = strip_env_value(value.strip())
    return values


def strip_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        return value[1:-1]
    return value


def database_url_password(database_url: str) -> str:
    return unquote(urlsplit(database_url).password or "")


def is_local_database_url(database_url: str, *, db_user: str, db_name: str) -> bool:
    parsed = urlsplit(database_url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        return False
    hostname = parsed.hostname or ""
    username = unquote(parsed.username or "")
    path_name = unquote(parsed.path.lstrip("/"))
    return hostname in {"localhost", "127.0.0.1", "::1"} and username == db_user and path_name == db_name


def prompt_local_db_password(args: argparse.Namespace) -> str:
    if not should_prompt_db_password(args):
        return ""
    first = getpass.getpass("Local Postgres password for Flux database user (leave blank to generate): ")
    if not first:
        return ""
    second = getpass.getpass("Confirm local Postgres password: ")
    if first != second:
        raise SystemExit("local Postgres passwords did not match")
    return first


def should_prompt_db_password(args: argparse.Namespace) -> bool:
    if args.dry_run or args.no_prompt_db_password:
        return False
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        return False
    return os.isatty(0)


def local_database_url(db_user: str, db_password: str, db_name: str) -> str:
    return "postgres://%s:%s@localhost:5432/%s" % (
        quote(db_user, safe=""),
        quote(db_password, safe=""),
        quote(db_name, safe=""),
    )


def render_template(path: Path, values: dict[str, str]) -> str:
    content = path.read_text(encoding="utf-8")
    for key, value in values.items():
        content = content.replace("@@%s@@" % key, value)
    return content


def write_file(path: Path, content: str, runner: CommandRunner) -> None:
    runner.note("write %s" % path)
    if runner.dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def sql_literal(value: str) -> str:
    return "'%s'" % value.replace("'", "''")


def sql_identifier(value: str) -> str:
    return '"%s"' % value.replace('"', '""')


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install Flux as a native Ubuntu/RHEL platform.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned actions without changing the host.")
    parser.add_argument("--list-stages", action="store_true", help="List installer stages and exit.")
    parser.add_argument("--stage", action="append", choices=[stage.name for stage in STAGES], help="Run only the selected stage. May be repeated.")
    parser.add_argument("--source-dir", type=Path, default=REPO_ROOT)
    parser.add_argument("--app-dir", type=Path, default=Path("/opt/flux/app"))
    parser.add_argument("--venv-dir", type=Path, default=Path("/opt/flux/venv"))
    parser.add_argument("--config-dir", type=Path, default=Path("/etc/flux"))
    parser.add_argument("--data-dir", type=Path, default=Path("/var/lib/flux"))
    parser.add_argument("--log-dir", type=Path, default=Path("/var/log/flux"))
    parser.add_argument("--vendor-dir", type=Path, default=Path("/opt/flux/vendor"))
    parser.add_argument("--systemd-dir", type=Path, default=Path("/etc/systemd/system"))
    parser.add_argument("--user", default="flux")
    parser.add_argument("--group", default="flux")
    parser.add_argument("--db-name", default="flux")
    parser.add_argument("--db-user", default="flux")
    parser.add_argument("--db-password", default="", help="Local Postgres password. Generated when omitted.")
    parser.add_argument(
        "--no-prompt-db-password",
        action="store_true",
        help="Generate the local Postgres password instead of prompting on interactive installs.",
    )
    parser.add_argument("--database-url", default="", help="External Postgres URL. Skips local Postgres role/db setup.")
    parser.add_argument("--django-secret-key", default="", help="Generated when omitted.")
    parser.add_argument("--allowed-hosts", default="localhost,127.0.0.1")
    parser.add_argument("--csrf-trusted-origins", default="")
    parser.add_argument("--web-bind", default="0.0.0.0:8000")
    parser.add_argument("--web-workers", type=int, default=8)
    parser.add_argument("--web-threads", type=int, default=2)
    parser.add_argument("--field-agent-host", default="localhost")
    parser.add_argument("--field-agent-base-port", type=int, default=4850)
    parser.add_argument("--skip-system-packages", action="store_true")
    parser.add_argument("--skip-postgres-setup", action="store_true")
    parser.add_argument("--force-env", action="store_true", help="Overwrite /etc/flux/flux.env if it already exists.")
    parser.add_argument("--no-enable", action="store_true", help="Do not enable services at boot.")
    parser.add_argument("--start", action="store_true", help="Start Flux services after installation.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.list_stages:
        for stage in STAGES:
            print(f"{stage.name}: {stage.description}")
        return 0
    distro = detect_distro()
    cfg = default_config(args)
    selected = set(args.stage or [stage.name for stage in STAGES])
    runner = CommandRunner(dry_run=args.dry_run)
    for stage in STAGES:
        if stage.name not in selected:
            continue
        print("\n==> %s: %s" % (stage.name, stage.description))
        stage.run(cfg, distro, runner)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
