from __future__ import annotations

import json
from hashlib import sha256
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from django.conf import settings

from flux.base.field_config import endpoint_config
from flux.base.field_selectors import enabled_field_endpoint_queryset
from flux.sim.models import FieldEndpoint


DEFAULT_FIELD_AGENT_HOST = "localhost"


@dataclass(frozen=True)
class FieldServerProcessSpec:
    key: str
    endpoint: FieldEndpoint
    config_path: Path
    endpoint_url: str
    config_hash: str
    command: list[str]


class FieldAgentProcess(Protocol):
    pid: int

    def poll(self) -> int | None: ...

    def terminate(self) -> None: ...

    def wait(self, timeout: float | None = None) -> int: ...

    def kill(self) -> None: ...


@dataclass(frozen=True)
class FieldSupervisorPlan:
    keep_keys: list[str]
    stop_keys: list[str]
    start_specs: list[FieldServerProcessSpec]
    failed: dict[str, int]

    @property
    def start_keys(self) -> list[str]:
        return [spec.key for spec in self.start_specs]

    def as_dict(self) -> dict[str, Any]:
        return {
            "keep": self.keep_keys,
            "stop": self.stop_keys,
            "start": self.start_keys,
            "failed": self.failed,
        }


def enabled_field_endpoints():
    return enabled_field_endpoint_queryset()


def server_endpoint_url(endpoint: FieldEndpoint, *, base_port: int, host: str = DEFAULT_FIELD_AGENT_HOST) -> str:
    port = base_port + int(endpoint.id)
    return "opc.tcp://%s:%s/flux/sim/%s" % (host, port, safe_name(endpoint.name))


def write_server_config(
    endpoint: FieldEndpoint,
    *,
    runtime_dir: Path,
    base_port: int,
    host: str = DEFAULT_FIELD_AGENT_HOST,
) -> tuple[Path, str, dict[str, Any]]:
    endpoint_url = server_endpoint_url(endpoint, base_port=base_port, host=host)
    config = {"endpoints": [endpoint_config(endpoint, endpoint_url=endpoint_url)]}
    config_dir = runtime_dir
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / (safe_name(endpoint.name) + ".json")
    config_json = json.dumps(config, indent=2, sort_keys=True)
    config_path.write_text(config_json, encoding="utf-8")
    return config_path, endpoint_url, config


def process_spec(
    endpoint: FieldEndpoint,
    *,
    runtime_dir: Path,
    base_port: int,
    project_path: Path,
    host: str = DEFAULT_FIELD_AGENT_HOST,
) -> FieldServerProcessSpec:
    config_path, endpoint_url, config = write_server_config(
        endpoint,
        runtime_dir=runtime_dir,
        base_port=base_port,
        host=host,
    )
    config_hash = sha256(json.dumps(config, sort_keys=True).encode("utf-8")).hexdigest()
    return FieldServerProcessSpec(
        key="field-agent:%s" % endpoint.id,
        endpoint=endpoint,
        config_path=config_path,
        endpoint_url=endpoint_url,
        config_hash=config_hash,
        command=[
            "dotnet",
            "run",
            "--project",
            str(project_path),
            "--FluxField:ConfigPath=%s" % config_path,
            "--FluxField:CertificateStorePath=%s" % (runtime_dir / "pki" / safe_name(endpoint.name)),
        ],
    )


def start_process(spec: FieldServerProcessSpec) -> subprocess.Popen:
    return subprocess.Popen(spec.command, cwd=settings.BASE_DIR.parents[1])


def reconciliation_plan(
    specs: list[FieldServerProcessSpec],
    processes: dict[str, FieldAgentProcess],
    running_specs: dict[str, FieldServerProcessSpec] | None = None,
) -> FieldSupervisorPlan:
    running_specs = running_specs or {}
    desired = {spec.key: spec for spec in specs}
    keep_keys = []
    stop_keys = []
    failed = {}
    for key, process in processes.items():
        exit_code = process.poll()
        if exit_code is not None:
            failed[key] = exit_code
        elif key in desired and running_specs.get(key, desired[key]).config_hash == desired[key].config_hash:
            keep_keys.append(key)
        elif key in desired:
            stop_keys.append(key)
        else:
            stop_keys.append(key)
    unavailable_keys = set(keep_keys) | set(failed)
    start_specs = [spec for spec in specs if spec.key not in unavailable_keys]
    return FieldSupervisorPlan(
        keep_keys=keep_keys,
        stop_keys=stop_keys,
        start_specs=start_specs,
        failed=failed,
    )


def apply_reconciliation_plan(
    plan: FieldSupervisorPlan,
    processes: dict[str, FieldAgentProcess],
    *,
    start=start_process,
) -> dict[str, FieldAgentProcess]:
    for key in plan.stop_keys:
        process = processes.pop(key)
        process.terminate()
    for key in plan.failed:
        processes.pop(key, None)
    for spec in plan.start_specs:
        processes[spec.key] = start(spec)
    return processes


def safe_name(value: str) -> str:
    return "".join(character if character.isalnum() or character in "-_" else "_" for character in value)
