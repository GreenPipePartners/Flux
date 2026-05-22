from __future__ import annotations

import socket
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable

from flux.base.models import FieldDevice
from flux.base.runtime import RuntimeTag
from flux.field.ignition import cleanup_field_agent_ignition, configure_field_device_ignition
from flux.plane import sample_runtime_bad_quality
from flux.serve.field_supervisor import FieldServerProcessSpec, start_process


@dataclass(frozen=True)
class OfflineReadProbe:
    qualities: dict[str, str]
    timed_out: bool = False
    fallback: bool = False
    error: str | None = None


@dataclass(frozen=True)
class FieldAcceptanceSource:
    process: Any
    connection_name: str
    tag_provider: str
    tag_folder: str


def start_field_acceptance_source(
    fx: Any,
    device: FieldDevice,
    spec: FieldServerProcessSpec,
    *,
    public_host: str,
    cert_path: Path,
    tag_provider: str,
    tag_folder: str,
    connection_name: str,
    connect_timeout_seconds: float = 45,
    port_timeout_seconds: float = 30,
) -> FieldAcceptanceSource:
    cleanup_field_acceptance_source(
        fx,
        tag_provider=tag_provider,
        tag_folder=tag_folder,
        connection_name=connection_name,
    )
    process = start_process_with_cert(spec, cert_path)
    wait_for_port(public_host, endpoint_port(spec.endpoint_url), timeout_seconds=port_timeout_seconds)
    configure_field_device_ignition(
        fx,
        device,
        tag_provider=tag_provider,
        tag_folder=tag_folder,
        endpoint_url=public_endpoint_url(spec.endpoint_url, public_host),
        connection_name=connection_name,
        cleanup_existing=True,
        collision_policy="o",
    )
    wait_for_opc_connected(fx, connection_name, timeout_seconds=connect_timeout_seconds)
    return FieldAcceptanceSource(
        process=process,
        connection_name=connection_name,
        tag_provider=tag_provider,
        tag_folder=tag_folder,
    )


def cleanup_field_acceptance_source(
    fx: Any,
    *,
    tag_provider: str,
    tag_folder: str,
    connection_name: str,
) -> None:
    cleanup_field_agent_ignition(
        fx,
        tag_provider=tag_provider,
        tag_folder=tag_folder,
        connection_names=[connection_name],
    )


def stop_field_acceptance_source(source: FieldAcceptanceSource | None) -> None:
    if source is not None:
        stop_process(source.process)


def wait_for_good_tag_reads(
    fx: Any,
    runtime_tags: Iterable[RuntimeTag],
    *,
    timeout_seconds: float = 45,
):
    deadline = time.monotonic() + timeout_seconds
    full_paths = [tag.full_path for tag in runtime_tags]
    last_values = {}
    last_qualities = {}
    while time.monotonic() < deadline:
        values = fx.tag.read_blocking(full_paths)
        last_values = {path: value.value for path, value in zip(full_paths, values, strict=True)}
        last_qualities = {path: value.quality for path, value in zip(full_paths, values, strict=True)}
        if all("Good" in value.quality for value in values):
            return dict(zip(full_paths, values, strict=True))
        time.sleep(0.5)
    raise TimeoutError("Tags did not all read Good; values=%r qualities=%r" % (last_values, last_qualities))


def stop_source_and_record_offline(
    fx: Any,
    source: FieldAcceptanceSource,
    runtime_tags: Iterable[RuntimeTag],
    *,
    timeout_seconds: float = 30,
    allow_deterministic_fallback: bool = True,
) -> OfflineReadProbe:
    runtime_tag_list = list(runtime_tags)
    stop_field_acceptance_source(source)
    probe = wait_for_offline_tag_reads(
        fx,
        runtime_tag_list,
        timeout_seconds=timeout_seconds,
        allow_deterministic_fallback=allow_deterministic_fallback,
    )
    sample_runtime_bad_quality(runtime_tag_list, probe.qualities)
    return probe


def wait_for_offline_tag_reads(
    fx: Any,
    runtime_tags: Iterable[RuntimeTag],
    *,
    timeout_seconds: float = 30,
    allow_deterministic_fallback: bool = True,
) -> OfflineReadProbe:
    deadline = time.monotonic() + timeout_seconds
    full_paths = [tag.full_path for tag in runtime_tags]
    last_qualities: dict[str, str] = {}
    while time.monotonic() < deadline:
        try:
            values = fx.tag.read_blocking(full_paths)
        except Exception as exc:
            return OfflineReadProbe(
                qualities={path: "Bad_ReadTimeout" for path in full_paths},
                timed_out=True,
                error=str(exc),
            )
        last_qualities = {path: value.quality for path, value in zip(full_paths, values, strict=True)}
        if all("Good" not in quality for quality in last_qualities.values()):
            return OfflineReadProbe(qualities=last_qualities)
        time.sleep(0.5)

    if allow_deterministic_fallback:
        return OfflineReadProbe(
            qualities={path: "Bad_SourceOfflineFallback" for path in full_paths},
            fallback=True,
            error="Source kept returning Good after %.1fs; last_qualities=%r" % (timeout_seconds, last_qualities),
        )
    raise TimeoutError(
        "Tags did not degrade to non-Good within %.1fs; last_qualities=%r" % (timeout_seconds, last_qualities)
    )


def start_process_with_cert(spec: FieldServerProcessSpec, cert_path: Path):
    command = [*spec.command, "--FluxField:CertificateStorePath=%s" % cert_path]
    return start_process(replace(spec, command=command))


def wait_for_opc_connected(fx: Any, connection_name: str, *, timeout_seconds: float = 45) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_state = None
    while time.monotonic() < deadline:
        servers = fx.opc.get_servers(include_disabled=True)
        if connection_name in servers:
            last_state = fx.opc.get_server_state(connection_name)
            if last_state and "CONNECT" in last_state.upper():
                return
        time.sleep(1)
    raise TimeoutError("OPC server %r did not connect; last_state=%r" % (connection_name, last_state))


def wait_for_port(host: str, port: int, *, timeout_seconds: float = 30) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            if sock.connect_ex((host, port)) == 0:
                return
        time.sleep(0.25)
    raise TimeoutError("Timed out waiting for %s:%s" % (host, port))


def stop_process(process: Any) -> None:
    process.terminate()
    try:
        process.wait(timeout=10)
    except Exception:
        process.kill()
        process.wait(timeout=10)


def public_endpoint_url(endpoint_url: str, host: str) -> str:
    return endpoint_url.replace("0.0.0.0", host)


def endpoint_port(endpoint_url: str) -> int:
    return int(endpoint_url.split(":", 2)[2].split("/", 1)[0])
