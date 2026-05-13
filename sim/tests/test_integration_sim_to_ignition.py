import json
import os
import socket
import subprocess
import time
from pathlib import Path

import pytest

from flux_sim.field_config import build_field_agent_config
from flux_sim.provider_import import import_provider_export


pytestmark = pytest.mark.integration


def test_sim_provider_fixture_reads_through_ignition(tmp_path: Path):
    if os.getenv("FLUX_SIM_IGNITION_INTEGRATION") != "1":
        pytest.skip("Set FLUX_SIM_IGNITION_INTEGRATION=1 to run sim-to-Ignition functional test")

    import fluxy
    from fluxy import FluxyError

    endpoint_port = int(os.getenv("FLUX_SIM_FIELD_PORT", "4850"))
    endpoint_url = os.getenv("FLUX_SIM_FIELD_ENDPOINT_URL", f"opc.tcp://localhost:{endpoint_port}/flux/sim")
    opc_server = os.getenv("FLUX_SIM_OPC_SERVER", "Flux Sim Functional")
    tag_provider = os.getenv("FLUX_SIM_TAG_PROVIDER", "default")
    tag_folder = os.getenv("FLUX_SIM_TAG_FOLDER", "FluxSimFunctional")
    timeout_ms = int(os.getenv("FLUX_SIM_READ_TIMEOUT_MS", "45000"))

    provider_export_path = tmp_path / "provider.json"
    database_path = tmp_path / "sim.db"
    config_path = tmp_path / "field-config.json"
    cert_path = tmp_path / "pki"

    provider_export_path.write_text(json.dumps(provider_fixture()), encoding="utf-8")
    import_provider_export(provider_export_path, database_path, provider_name="ACM02")
    field_config = build_field_agent_config(
        database_path,
        provider_name="ACM02",
        endpoint_url=endpoint_url,
        namespace_uri="urn:flux:sim:functional",
    )
    probe_tags = select_probe_tags(field_config, limit=2)
    config_path.write_text(json.dumps(field_config, indent=2), encoding="utf-8")
    process = start_field_agent(config_path, cert_path)
    fx = fluxy.Fluxy(
        base_url=os.getenv("FLUXY_BASE_URL", "http://localhost:8088/system/webdev/flux"),
        token=os.getenv("FLUXY_TOKEN"),
        project_location=os.getenv("FLUXY_PROJECT_LOCATION", "../ignition_flux_project"),
    )

    tag_paths = [f"[{tag_provider}]{tag_folder}/{tag['name']}" for tag in probe_tags]
    try:
        wait_for_port("localhost", endpoint_port)
        ensure_opcua_connection(fx, opc_server, endpoint_url)
        wait_for_opc_connected(fx, opc_server)
        configure_ignition_probe_tags(fx, tag_provider, tag_folder, opc_server, probe_tags)
        values = wait_for_good_tag_values(fx, tag_paths, timeout_ms=timeout_ms)
        seen = sample_tag_changes(fx, tag_paths, timeout_ms=timeout_ms)
    except FluxyError as exc:
        if "Trial Expired" in str(exc):
            pytest.skip("Ignition trial expired during sim-to-Ignition functional test")
        pytest.fail(f"sim-to-Ignition functional test failed: {exc}")
    finally:
        cleanup_ignition(fx, tag_provider, tag_folder, opc_server, endpoint_url)
        stop_field_agent(process)

    assert all(value.quality.startswith("Good") for value in values), values
    assert all(len(samples) > 1 for samples in seen.values()), seen


def select_probe_tags(field_config: dict, *, limit: int) -> list[dict]:
    tags = []
    for endpoint in field_config["endpoints"]:
        for device in endpoint["devices"]:
            for tag in device["tags"]:
                if tag["data_type"] in {"float", "int", "bool"}:
                    tags.append(tag)
                    if len(tags) == limit:
                        return tags
    pytest.fail("Field config did not contain enough numeric/bool probe tags")


def configure_ignition_probe_tags(fx, tag_provider, tag_folder, opc_server, probe_tags):
    fx.tag.configure(
        [
            {
                "name": tag_folder,
                "tagType": "Folder",
                "tags": [ignition_opc_tag_config(tag, opc_server) for tag in probe_tags],
            }
        ],
        base_path=f"[{tag_provider}]",
        collision_policy="o",
    )


def ignition_opc_tag_config(tag: dict, opc_server: str) -> dict:
    return {
        "name": tag["name"],
        "tagType": "AtomicTag",
        "valueSource": "opc",
        "dataType": ignition_data_type(tag["data_type"]),
        "opcServer": opc_server,
        "opcItemPath": tag["node_id"],
    }


def ignition_data_type(data_type: str) -> str:
    return {
        "bool": "Boolean",
        "int": "Int4",
        "float": "Float8",
        "string": "String",
    }[data_type]


def ensure_opcua_connection(fx, opc_server: str, endpoint_url: str) -> None:
    try:
        fx.opcua.remove_connection(opc_server)
    except Exception:
        pass
    try:
        fx.opcua.add_connection(
            opc_server,
            "Flux Sim functional OPC UA simulator",
            endpoint_url,
            endpoint_url,
            security_policy="None",
            security_mode="None",
            settings={
                "ENABLED": True,
                "DISCOVERYURL": endpoint_url,
                "ENDPOINTURL": endpoint_url,
                "SECURITYPOLICY": "None",
                "SECURITYMODE": "None",
                "CERTIFICATEVALIDATIONENABLED": False,
                "CONNECTTIMEOUT": 5000,
                "ACKNOWLEDGETIMEOUT": 5000,
                "REQUESTTIMEOUT": 5000,
                "SESSIONTIMEOUT": 60000,
            },
        )
    except Exception:
        fx.scripting.run_function_file("opcua_connection", "remove", opc_server, endpoint_url, target_directory="field")
        fx.scripting.run_function_file("opcua_connection", "add", opc_server, endpoint_url, target_directory="field")


def wait_for_opc_connected(fx, opc_server: str) -> None:
    timeout_seconds = float(os.getenv("FLUX_SIM_CONNECT_TIMEOUT_SECONDS", "45"))
    deadline = time.monotonic() + timeout_seconds
    last_state = None
    while time.monotonic() < deadline:
        servers = fx.opc.get_servers(include_disabled=True)
        if opc_server in servers:
            last_state = fx.opc.get_server_state(opc_server)
            if last_state and "CONNECT" in last_state.upper():
                return
        time.sleep(1)
    pytest.fail(f"OPC server {opc_server!r} did not connect; last_state={last_state!r}")


def wait_for_good_tag_values(fx, tag_paths: list[str], *, timeout_ms: int):
    deadline = time.monotonic() + timeout_ms / 1000.0
    last_values = []
    while time.monotonic() < deadline:
        last_values = fx.tag.read_blocking(tag_paths, timeout_ms=timeout_ms)
        if all(value.quality.startswith("Good") for value in last_values):
            return last_values
        time.sleep(1)
    pytest.fail(f"Timed out waiting for Good values. Last values={last_values!r}")


def sample_tag_changes(fx, tag_paths: list[str], *, timeout_ms: int) -> dict[str, set]:
    seen = {path: set() for path in tag_paths}
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline and not all(len(samples) > 1 for samples in seen.values()):
        values = fx.tag.read_blocking(tag_paths, timeout_ms=timeout_ms)
        for value in values:
            if value.quality.startswith("Good") and value.tag_path in seen:
                seen[value.tag_path].add(normalize_sample(value.value))
        time.sleep(0.5)
    return seen


def normalize_sample(value):
    if isinstance(value, float):
        return round(value, 6)
    return value


def cleanup_ignition(fx, tag_provider: str, tag_folder: str, opc_server: str, endpoint_url: str) -> None:
    try:
        fx.tag.delete_tags(f"[{tag_provider}]{tag_folder}")
    except Exception:
        pass
    try:
        fx.opcua.remove_connection(opc_server)
    except Exception:
        try:
            fx.scripting.run_function_file("opcua_connection", "remove", opc_server, endpoint_url, target_directory="field")
        except Exception:
            pass


def start_field_agent(config_path: Path, cert_path: Path):
    repo_root = Path(__file__).resolve().parents[2]
    project_path = repo_root / "field" / "Flux.FieldAgent" / "Flux.FieldAgent.csproj"
    return subprocess.Popen(
        [
            "dotnet",
            "run",
            "--project",
            str(project_path),
            f"--FluxField:ConfigPath={config_path}",
            f"--FluxField:CertificateStorePath={cert_path}",
        ],
        cwd=repo_root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def stop_field_agent(process) -> None:
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def wait_for_port(host: str, port: int) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            if sock.connect_ex((host, port)) == 0:
                return
        time.sleep(0.25)
    pytest.fail(f"Timed out waiting for {host}:{port}")


def provider_fixture() -> dict:
    return {
        "name": "Tag_02",
        "tagType": "Provider",
        "tags": [
            {
                "name": "_types_",
                "tagType": "Folder",
                "tags": [
                    {
                        "name": "Well",
                        "tagType": "UdtType",
                        "parameters": {
                            "OPC_Prefix": {"dataType": "String", "value": "ns=2;s="},
                            "Interval_Trend": {"dataType": "String", "value": ""},
                        },
                        "tags": [
                            {
                                "name": "CASING_PRESSURE",
                                "tagType": "AtomicTag",
                                "valueSource": "opc",
                                "dataType": "Float4",
                                "opcServer": {"bindType": "parameter", "binding": "{OPC_Server}"},
                                "opcItemPath": {
                                    "bindType": "parameter",
                                    "binding": "{OPC_Prefix}{OPC_Device}.{IO_Address}F{Interval_Trend}",
                                },
                            },
                            {
                                "name": "FLOW_RATE",
                                "tagType": "AtomicTag",
                                "valueSource": "opc",
                                "dataType": "Float4",
                                "opcServer": {"bindType": "parameter", "binding": "{OPC_Server}"},
                                "opcItemPath": {
                                    "bindType": "parameter",
                                    "binding": "{OPC_Prefix}{OPC_Device}.{IO_Address+2}F{Interval_Trend}",
                                },
                            },
                        ],
                    }
                ],
            },
            {
                "name": "Pad_A",
                "tagType": "Folder",
                "tags": [
                    {
                        "name": "Well_01",
                        "tagType": "UdtInstance",
                        "typeId": "[Tag_02]_types_/Well",
                        "parameters": {
                            "OPC_Server": {"dataType": "String", "value": "ACM_02"},
                            "OPC_Device": {"dataType": "String", "value": "RTU_01"},
                            "IO_Address": {"dataType": "String", "value": "41600"},
                        },
                    }
                ],
            },
        ],
    }
