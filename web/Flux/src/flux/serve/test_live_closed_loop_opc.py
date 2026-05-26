from dataclasses import replace
import os
import socket
import time
from pathlib import Path
from uuid import uuid4

import pytest

from flux.base.models import Tag
from flux.sim.models import FieldEndpoint
from flux.field.ignition import configure_field_device_ignition, safe_name
from flux.serve.field_supervisor import process_spec, start_process
from flux.sim.models import TagConfig
from flux.sim.testing import create_device_config, create_tag_config


@pytest.mark.django_db(transaction=True)
@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("FLUX_LIVE_CLOSED_LOOP_OPC") != "1",
    reason="Set FLUX_LIVE_CLOSED_LOOP_OPC=1 to run one-device live closed-loop OPC test",
)
def test_live_one_device_closed_loop_opc_read_changes_and_cleans_up(tmp_path):
    import fluxy
    from fluxy import FluxyError

    repo_root = Path(__file__).resolve().parents[5]
    project_path = Path(
        os.getenv(
            "FLUX_FIELD_AGENT_PROJECT_PATH",
            str(repo_root / "field" / "Flux.FieldAgent" / "Flux.FieldAgent.csproj"),
        )
    )
    if not project_path.exists():
        pytest.skip("Flux.FieldAgent project is required for live closed-loop OPC test")

    unique = safe_name("live-closed-loop-%s" % uuid4().hex[:10])
    public_host = os.getenv("FLUX_LIVE_CLOSED_LOOP_HOST", "localhost")
    base_port = int(os.getenv("FLUX_LIVE_CLOSED_LOOP_BASE_PORT", "4960"))
    tag_provider = os.getenv("FLUX_LIVE_CLOSED_LOOP_TAG_PROVIDER", "default")
    tag_folder = os.getenv("FLUX_LIVE_CLOSED_LOOP_TAG_FOLDER", "FluxLiveClosedLoop_%s" % unique)
    connection_name = os.getenv("FLUX_LIVE_CLOSED_LOOP_CONNECTION", "Flux Spot Closed Loop %s" % unique)
    fx = fluxy.Fluxy(
        base_url=os.getenv("FLUXY_BASE_URL", "http://localhost:8088/system/webdev/flux"),
        token=os.getenv("FLUXY_TOKEN"),
        project_location=os.getenv("FLUXY_PROJECT_LOCATION", str(repo_root / "web" / "ignition_flux_project")),
    )

    endpoint, device, tag = create_unique_closed_loop_device(unique)
    spec = process_spec(
        endpoint,
        runtime_dir=tmp_path / "runtime",
        base_port=base_port,
        project_path=project_path,
        host=public_host,
    )

    try:
        initial, changed = run_one_device_closed_loop(
            fx,
            device=device,
            tag=tag,
            spec=spec,
            public_host=public_host,
            tag_provider=tag_provider,
            tag_folder=tag_folder,
            connection_name=connection_name,
            cert_path=tmp_path / "pki" / unique,
        )
    except FluxyError as exc:
        cleanup_db_rows(endpoint)
        if "Trial Expired" in str(exc):
            pytest.skip("Ignition trial expired during live closed-loop OPC test")
        pytest.fail("live closed-loop OPC test failed: %s" % exc)
    finally:
        cleanup_db_rows(endpoint)

    assert "Good" in initial.quality
    assert "Good" in changed.quality
    assert changed.value != initial.value


def test_one_device_closed_loop_runner_sequences_standard_api_and_cleanup():
    fx = FakeFluxy(
        values=[
            FakeQualifiedValue(10, "Good"),
            FakeQualifiedValue(11, "Good"),
            FakeQualifiedValue(None, "Bad_NotFound"),
        ]
    )
    endpoint = FakeEndpoint(name="unit-endpoint")
    device = FakeDevice(endpoint=endpoint, name="Unit Device", tags=[FakeTag("Value")])
    tag = device.tags.tags[0]
    spec = FakeSpec(endpoint_url="opc.tcp://0.0.0.0:4981/flux/field/Unit_Device")
    process = FakeProcess()
    events = []

    initial, changed = run_one_device_closed_loop(
        fx,
        device=device,
        tag=tag,
        spec=spec,
        public_host="localhost",
        tag_provider="testing",
        tag_folder="UnitClosedLoop",
        connection_name="Flux Unit Connection",
        cert_path=Path("/tmp/unit-pki"),
        start=lambda spec, cert_path: events.append(("start", cert_path)) or process,
        wait_port=lambda host, port: events.append(("wait_port", host, port)),
        wait_opc=lambda fx, connection_name: events.append(("wait_opc", connection_name)),
        wait_change=lambda fx, tag_path, initial_value, timeout_seconds: fx.tag.read_blocking(tag_path),
    )

    assert initial.value == 10
    assert changed.value == 11
    assert events == [
        ("start", Path("/tmp/unit-pki")),
        ("wait_port", "localhost", 4981),
        ("wait_opc", "Flux Unit Connection"),
    ]
    assert fx.opcua.added[0]["name"] == "Flux Unit Connection"
    assert fx.tag.configured[0]["base_path"] == "[testing]"
    assert fx.tag.deleted == ["[testing]UnitClosedLoop", "[testing]UnitClosedLoop"]
    assert fx.opcua.removed == ["Flux Unit Connection", "Flux Unit Connection"]
    assert process.terminated


def run_one_device_closed_loop(
    fx,
    *,
    device,
    tag,
    spec,
    public_host,
    tag_provider,
    tag_folder,
    connection_name,
    cert_path,
    start=None,
    wait_port=None,
    wait_opc=None,
    wait_change=None,
):
    process = None
    tag_path = "[%s]%s/%s_%s" % (tag_provider, tag_folder, safe_name(device.name), safe_name(tag.name))
    endpoint_url = public_endpoint_url(spec.endpoint_url, public_host)
    completed = False
    start = start or start_process_with_cert
    wait_port = wait_port or wait_for_port
    wait_opc = wait_opc or wait_for_opc_connected
    wait_change = wait_change or wait_for_tag_value_change

    try:
        process = start(spec, cert_path)
        wait_port(public_host, endpoint_port(spec.endpoint_url))
        configure_field_device_ignition(
            fx,
            device,
            tag_provider=tag_provider,
            tag_folder=tag_folder,
            endpoint_url=endpoint_url,
            connection_name=connection_name,
            cleanup_existing=True,
            collision_policy="o",
        )
        wait_opc(fx, connection_name)
        initial = wait_for_good_tag_value(
            fx,
            tag_path,
            float(os.getenv("FLUX_LIVE_CLOSED_LOOP_INITIAL_READ_TIMEOUT_SECONDS", "30")),
        )
        changed = wait_change(
            fx,
            tag_path,
            initial.value,
            float(os.getenv("FLUX_LIVE_CLOSED_LOOP_CHANGE_TIMEOUT_SECONDS", "30")),
        )
        completed = True
        return initial, changed
    finally:
        cleanup_live_ignition(
            fx,
            tag_provider,
            tag_folder,
            [connection_name],
            deleted_tag_path=tag_path if completed else None,
        )
        if process is not None:
            stop_process(process)


def create_unique_closed_loop_device(unique):
    endpoint = FieldEndpoint.objects.create(name="endpoint-%s" % unique, security_policy="None")
    device = create_device_config(
        endpoint=endpoint,
        name="device-%s" % unique,
        device_type="ControlLogix",
    )
    tag = create_tag_config(
        device=device,
        name="Value",
        data_type=Tag.DataType.INT,
        update_rate_ms=250,
        simulation_type=TagConfig.SimulationType.RAMP,
        min_value=0,
        max_value=100000,
        initial_value="1",
        materialized=True,
    )
    return endpoint, device, tag


def start_process_with_cert(spec, cert_path):
    command = [*spec.command, "--FluxField:CertificateStorePath=%s" % cert_path]
    return start_process(replace(spec, command=command))


def wait_for_opc_connected(fx, connection_name):
    deadline = time.monotonic() + float(os.getenv("FLUX_LIVE_CLOSED_LOOP_CONNECT_TIMEOUT_SECONDS", "30"))
    last_state = None
    while time.monotonic() < deadline:
        servers = fx.opc.get_servers(include_disabled=True)
        if connection_name in servers:
            last_state = fx.opc.get_server_state(connection_name)
            if last_state and "CONNECT" in last_state.upper():
                return
        time.sleep(1)
    pytest.fail("OPC server %r did not connect; last_state=%r" % (connection_name, last_state))


def wait_for_tag_value_change(fx, tag_path, initial_value, timeout_seconds):
    deadline = time.monotonic() + timeout_seconds
    last_value = initial_value
    last_quality = None
    while time.monotonic() < deadline:
        value = fx.tag.read_blocking(tag_path)
        last_value = value.value
        last_quality = value.quality
        if "Good" in value.quality and value.value != initial_value:
            return value
        time.sleep(0.5)
    pytest.fail(
        "Tag %s did not change from %r within %.1fs; last_value=%r last_quality=%r"
        % (tag_path, initial_value, timeout_seconds, last_value, last_quality)
    )


def wait_for_good_tag_value(fx, tag_path, timeout_seconds):
    deadline = time.monotonic() + timeout_seconds
    last_value = None
    last_quality = None
    while time.monotonic() < deadline:
        value = fx.tag.read_blocking(tag_path)
        last_value = value.value
        last_quality = value.quality
        if "Good" in value.quality:
            return value
        time.sleep(0.5)
    pytest.fail(
        "Tag %s did not read Good within %.1fs; last_value=%r last_quality=%r"
        % (tag_path, timeout_seconds, last_value, last_quality)
    )


def cleanup_live_ignition(fx, tag_provider, tag_folder, connection_names, deleted_tag_path=None):
    try:
        fx.tag.delete_tags("[%s]%s" % (tag_provider, tag_folder))
    except Exception:
        pass
    if deleted_tag_path is not None:
        try:
            deleted_value = fx.tag.read_blocking(deleted_tag_path)
        except Exception:
            deleted_value = None
        if deleted_value is not None and "Good" in deleted_value.quality:
            pytest.fail("Deleted tag %s still reads Good" % deleted_tag_path)
    for connection_name in connection_names:
        try:
            fx.opcua.remove_connection(connection_name)
        except Exception:
            pass


def cleanup_db_rows(endpoint):
    try:
        endpoint.delete()
    except Exception:
        pass


def wait_for_port(host, port):
    deadline = time.monotonic() + float(os.getenv("FLUX_LIVE_CLOSED_LOOP_PORT_TIMEOUT_SECONDS", "30"))
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


class FakeQualifiedValue:
    def __init__(self, value, quality):
        self.value = value
        self.quality = quality


class FakeFluxy:
    def __init__(self, values):
        self.tag = FakeTagNamespace(values)
        self.opcua = FakeOpcUaNamespace()


class FakeTagNamespace:
    def __init__(self, values):
        self.values = list(values)
        self.configured = []
        self.deleted = []

    def configure(self, tags, base_path=None, collision_policy="o"):
        self.configured.append(
            {"tags": tags, "base_path": base_path, "collision_policy": collision_policy}
        )
        return []

    def read_blocking(self, tag_path):
        return self.values.pop(0)

    def delete_tags(self, tag_path):
        self.deleted.append(tag_path)
        return []


class FakeOpcUaNamespace:
    def __init__(self):
        self.added = []
        self.removed = []

    def add_connection(
        self,
        name,
        description,
        discovery_url,
        endpoint_url,
        security_policy="None",
        security_mode="None",
        settings=None,
    ):
        self.added.append(
            {
                "name": name,
                "description": description,
                "discovery_url": discovery_url,
                "endpoint_url": endpoint_url,
                "security_policy": security_policy,
                "security_mode": security_mode,
                "settings": settings,
            }
        )
        return True

    def remove_connection(self, name):
        self.removed.append(name)
        return True


class FakeEndpoint:
    def __init__(self, name):
        self.name = name
        self.endpoint_url = "opc.tcp://0.0.0.0:4981/flux/field/unit"
        self.application_uri = "urn:flux:test"
        self.product_uri = "urn:flux:test"
        self.namespace_uri = "urn:flux:test"
        self.security_policy = "None"


class FakeDevice:
    def __init__(self, endpoint, name, tags):
        self.endpoint = endpoint
        self.name = name
        self.device_type = "ControlLogix"
        self.browse_path = "Devices"
        self.tags = FakeTagRelation(tags)


class FakeTagRelation:
    def __init__(self, tags):
        self.tags = tags

    def filter(self, **kwargs):
        if kwargs == {"enabled": True}:
            return self
        raise AssertionError("unexpected filter: %r" % kwargs)

    def order_by(self, field):
        if field != "name":
            raise AssertionError("unexpected order_by: %r" % field)
        return sorted(self.tags, key=lambda tag: tag.name)


class FakeTag:
    def __init__(self, name):
        self.device_name = "Unit Device"
        self.name = name
        self.data_type = "int"
        self.update_rate_ms = 1000
        self.simulation_type = "ramp"
        self.min_value = 0
        self.max_value = 100
        self.variance = 0.0
        self.initial_value = "10"

    @property
    def node_id(self):
        return "ns=2;s=%s.%s" % (self.device_name, self.name)

    @property
    def browse_name(self):
        return self.name

    @property
    def opc_item_path(self):
        return "%s/%s" % (self.device_name, self.name)


class FakeSpec:
    def __init__(self, endpoint_url):
        self.endpoint_url = endpoint_url


class FakeProcess:
    def __init__(self):
        self.terminated = False
        self.killed = False

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.killed = True
