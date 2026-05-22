from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from django.conf import settings

from flux.base.field_config import endpoint_config
from flux.base.models import FieldEndpoint


@dataclass(frozen=True)
class FieldServerProcessSpec:
    key: str
    endpoint: FieldEndpoint
    config_path: Path
    endpoint_url: str
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
    return (
        FieldEndpoint.objects.prefetch_related("devices__tags")
        .filter(enabled=True, devices__enabled=True)
        .distinct()
        .order_by("name")
    )


def server_endpoint_url(endpoint: FieldEndpoint, *, base_port: int, host: str = "0.0.0.0") -> str:
    port = base_port + int(endpoint.id)
    return "opc.tcp://%s:%s/flux/sim/%s" % (host, port, safe_name(endpoint.name))


def write_server_config(
    endpoint: FieldEndpoint,
    *,
    runtime_dir: Path,
    base_port: int,
    host: str = "0.0.0.0",
) -> tuple[Path, str, dict[str, Any]]:
    endpoint_url = server_endpoint_url(endpoint, base_port=base_port, host=host)
    config = {"endpoints": [endpoint_config(endpoint, endpoint_url=endpoint_url)]}
    config_dir = runtime_dir
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / (safe_name(endpoint.name) + ".json")
    config_path.write_text(json.dumps(config, indent=2, sort_keys=True), encoding="utf-8")
    return config_path, endpoint_url, config


def process_spec(
    endpoint: FieldEndpoint,
    *,
    runtime_dir: Path,
    base_port: int,
    project_path: Path,
    host: str = "0.0.0.0",
) -> FieldServerProcessSpec:
    config_path, endpoint_url, _config = write_server_config(
        endpoint,
        runtime_dir=runtime_dir,
        base_port=base_port,
        host=host,
    )
    return FieldServerProcessSpec(
        key="field-agent:%s" % endpoint.id,
        endpoint=endpoint,
        config_path=config_path,
        endpoint_url=endpoint_url,
        command=[
            "dotnet",
            "run",
            "--project",
            str(project_path),
            "--FluxField:ConfigPath=%s" % config_path,
        ],
    )


def start_process(spec: FieldServerProcessSpec) -> subprocess.Popen:
    return subprocess.Popen(spec.command, cwd=settings.BASE_DIR.parents[1])


def reconciliation_plan(
    specs: list[FieldServerProcessSpec],
    processes: dict[str, FieldAgentProcess],
) -> FieldSupervisorPlan:
    desired = {spec.key: spec for spec in specs}
    keep_keys = []
    stop_keys = []
    failed = {}
    for key, process in processes.items():
        exit_code = process.poll()
        if exit_code is not None:
            failed[key] = exit_code
        elif key in desired:
            keep_keys.append(key)
        else:
            stop_keys.append(key)
    occupied_keys = set(keep_keys) | set(stop_keys) | set(failed)
    start_specs = [spec for spec in specs if spec.key not in occupied_keys]
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
