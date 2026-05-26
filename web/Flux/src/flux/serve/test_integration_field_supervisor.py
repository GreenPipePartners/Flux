from dataclasses import replace
import os
import socket
import time
from pathlib import Path

import pytest

from flux.base.field_config import ignition_tag_config
from flux.base.models import Tag
from flux.sim.models import FieldEndpoint
from flux.sim.models import TagConfig
from flux.sim.testing import create_device_config, create_tag_config
from flux.serve.field_supervisor import process_spec, start_process


pytestmark = pytest.mark.integration


@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(
    os.getenv("FLUX_FIELD_SUPERVISOR_INTEGRATION") != "1",
    reason="Set FLUX_FIELD_SUPERVISOR_INTEGRATION=1 to run multi-process FieldAgent integration",
)
def test_field_supervisor_multi_process_devices_read_through_fluxy(tmp_path):
    import fluxy
    from fluxy import FluxyError

    repo_root = Path(__file__).resolve().parents[5]
    project_path = repo_root / "field" / "Flux.FieldAgent" / "Flux.FieldAgent.csproj"
    if not project_path.exists():
        pytest.skip("Flux.FieldAgent project is required for supervisor integration")

    public_host = os.getenv("FLUX_FIELD_SUPERVISOR_HOST", "localhost")
    base_port = int(os.getenv("FLUX_FIELD_SUPERVISOR_BASE_PORT", "4860"))
    tag_provider = os.getenv("FLUX_FIELD_TAG_PROVIDER", "default")
    tag_folder = os.getenv("FLUX_FIELD_SUPERVISOR_TAG_FOLDER", "FluxFieldSupervisor")
    cert_path = tmp_path / "pki"
    endpoint, field_tags = create_supervised_devices()
    spec = process_spec(
        endpoint,
        runtime_dir=tmp_path / "runtime",
        base_port=base_port,
        project_path=project_path,
        host=public_host,
    )
    specs = [spec]
    processes = []
    fx = fluxy.Fluxy(
        base_url=os.getenv("FLUXY_BASE_URL", "http://localhost:8088/system/webdev/flux"),
        token=os.getenv("FLUXY_TOKEN"),
        project_location=os.getenv(
            "FLUXY_PROJECT_LOCATION",
            str(repo_root / "web" / "ignition_flux_project"),
        ),
    )

    tag_paths = [
        "[%s]%s/%s_%s" % (tag_provider, tag_folder, tag.device.name, tag.name)
        for tag in field_tags
    ]
    try:
        processes = [start_supervised_process(spec, cert_path) for spec in specs]
        wait_for_port(public_host, endpoint_port(spec.endpoint_url))
        ensure_opcua_connection(
            fx,
            opc_server_name(spec.endpoint),
            public_endpoint_url(spec.endpoint_url, public_host),
        )
        wait_for_opc_connected(fx, opc_server_name(spec.endpoint))
        configure_supervised_tags(fx, tag_provider, tag_folder, field_tags)
        seen = sample_tag_changes(fx, tag_paths, timeout_seconds=30)
    except FluxyError as exc:
        if "Trial Expired" in str(exc):
            pytest.skip("Ignition trial expired during multi-process FieldAgent integration")
        pytest.fail("multi-process FieldAgent integration failed: %s" % exc)
    finally:
        cleanup_supervised_integration(fx, tag_provider, tag_folder, specs)
        for process in processes:
            stop_process(process)

    assert all(len(values) > 1 for values in seen.values()), seen


def create_supervised_devices():
    endpoint = FieldEndpoint.objects.create(name="supervised-field", security_policy="None")
    field_tags = []
    for index, device_name in enumerate(["SupervisorA", "SupervisorB"], start=1):
        device = create_device_config(endpoint=endpoint, name=device_name, device_type="ControlLogix")
        field_tags.append(
            create_tag_config(
                device=device,
                name="Value",
                data_type=Tag.DataType.INT,
                update_rate_ms=500,
                simulation_type=TagConfig.SimulationType.RAMP,
                min_value=0,
                max_value=1000,
                initial_value=str(index),
                materialized=True,
            )
        )
    return endpoint, field_tags


def start_supervised_process(spec, cert_path):
    command = [
        *spec.command,
        "--FluxField:CertificateStorePath=%s" % (cert_path / spec.config_path.stem),
    ]
    return start_process(replace(spec, command=command))


def configure_supervised_tags(fx, tag_provider, tag_folder, field_tags):
    fx.tag.configure(
        [
            {
                "name": tag_folder,
                "tagType": "Folder",
                "tags": [
                    ignition_tag_config(
                        tag,
                        opc_server_name(tag.device.endpoint),
                        tag_name="%s_%s" % (tag.device.name, tag.name),
                    )
                    for tag in field_tags
                ],
            }
        ],
        base_path="[%s]" % tag_provider,
        collision_policy="o",
    )


def ensure_opcua_connection(fx, opc_server, endpoint_url):
    try:
        fx.opcua.remove_connection(opc_server)
    except Exception:
        pass
    fx.opcua.add_connection(
        opc_server,
        "Flux Field supervisor OPC UA simulator",
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


def wait_for_opc_connected(fx, opc_server):
    deadline = time.monotonic() + float(os.getenv("FLUX_FIELD_CONNECT_TIMEOUT_SECONDS", "30"))
    last_state = None
    while time.monotonic() < deadline:
        servers = fx.opc.get_servers(include_disabled=True)
        if opc_server in servers:
            last_state = fx.opc.get_server_state(opc_server)
            if last_state and "CONNECT" in last_state.upper():
                return
        time.sleep(1)
    pytest.fail("OPC server %r did not connect; last_state=%r" % (opc_server, last_state))


def sample_tag_changes(fx, tag_paths, timeout_seconds):
    seen = {path: set() for path in tag_paths}
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline and not all(len(values) > 1 for values in seen.values()):
        values = fx.tag.read_blocking(tag_paths)
        for value in values:
            if "Good" in value.quality and value.tag_path in seen:
                seen[value.tag_path].add(value.value)
        time.sleep(0.5)
    return seen


def cleanup_supervised_integration(fx, tag_provider, tag_folder, specs):
    try:
        fx.tag.delete_tags("[%s]%s" % (tag_provider, tag_folder))
    except Exception:
        pass
    for spec in specs:
        try:
            fx.opcua.remove_connection(opc_server_name(spec.endpoint))
        except Exception:
            pass


def wait_for_port(host, port):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            if sock.connect_ex((host, port)) == 0:
                return
        time.sleep(0.25)
    pytest.fail("Timed out waiting for %s:%s" % (host, port))


def stop_process(process):
    process.terminate()
    try:
        process.wait(timeout=10)
    except Exception:
        process.kill()
        process.wait(timeout=10)


def public_endpoint_url(endpoint_url, host):
    return endpoint_url.replace("0.0.0.0", host)


def endpoint_port(endpoint_url):
    return int(endpoint_url.split(":", 2)[2].split("/", 1)[0])


def opc_server_name(endpoint):
    return "Flux Sim %s Server" % endpoint.name
