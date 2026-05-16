import json
import os
import socket
import subprocess
import time
from pathlib import Path

import pytest

from flux.base.field_config import endpoint_config, ignition_tag_config
from flux.base.models import FieldDevice, FieldEndpoint, FieldTag


pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    ("tag_name", "data_type", "update_rate_ms", "sample_count"),
    [
        ("BoolTag", FieldTag.DataType.BOOL, 1000, 6),
        ("IntegerTag", FieldTag.DataType.INT, 5000, 8),
        ("FloatTag", FieldTag.DataType.FLOAT, 10000, 12),
    ],
)
@pytest.mark.django_db(transaction=True)
def test_flux_field_opc_tag_reads_changing_values(
    tag_name, data_type, update_rate_ms, sample_count
):
    if os.getenv("FLUX_FIELD_INTEGRATION") != "1":
        pytest.skip("Set FLUX_FIELD_INTEGRATION=1 to run Flux Field Ignition integration")

    import fluxy
    from fluxy import FluxyError

    base_url = os.getenv("FLUXY_BASE_URL", "http://localhost:8088/system/webdev/flux")
    token = os.getenv("FLUXY_TOKEN")
    project_location = os.getenv("FLUXY_PROJECT_LOCATION", "../ignition_flux_project")
    tag_provider = os.getenv("FLUX_FIELD_TAG_PROVIDER", "default")
    opc_server = os.getenv("FLUX_FIELD_OPC_SERVER", "Flux Field")
    endpoint_url = os.getenv("FLUX_FIELD_ENDPOINT_URL", "opc.tcp://localhost:4840/flux/field")
    tag_folder = os.getenv("FLUX_FIELD_TAG_FOLDER", "FluxFieldIntegration")
    tag_path = "[%s]%s/%s" % (tag_provider, tag_folder, tag_name)

    fx = fluxy.Fluxy(base_url=base_url, token=token, project_location=project_location)

    try:
        if os.getenv("FLUX_FIELD_DEPLOY_WEBDEV") == "1":
            fx.deploy_webdev()
            fx.project.request_scan()
        ensure_opcua_connection(fx, opc_server, endpoint_url)
        wait_for_opc_connected(fx, opc_server)
        configure_opc_tag(fx, tag_provider, tag_folder, tag_name, data_type, opc_server)
        values = sample_tag_values(fx, tag_path, sample_count, update_rate_ms)
    except FluxyError as exc:
        if "Trial Expired" in str(exc):
            pytest.skip("Ignition trial expired during Flux Field integration test")
        pytest.fail("Flux Field integration failed: %s" % exc)
    finally:
        try:
            fx.tag.delete_tags(tag_path)
        except FluxyError:
            pass

    assert all("Good" in value.quality for value in values), values
    assert len({normalize_sample(value.value) for value in values}) > 1, values


@pytest.mark.django_db(transaction=True)
def test_flux_field_integration_reads_three_devices(tmp_path):
    if os.getenv("FLUX_FIELD_INTEGRATION") != "1":
        pytest.skip("Set FLUX_FIELD_INTEGRATION=1 to run Flux Field Ignition integration")

    import fluxy
    from fluxy import FluxyError

    endpoint_url = os.getenv("FLUX_FIELD_THREE_DEVICE_ENDPOINT_URL", "opc.tcp://localhost:4841/flux/field")
    opc_server = os.getenv("FLUX_FIELD_THREE_DEVICE_OPC_SERVER", "Flux Field 3 Device")
    tag_provider = os.getenv("FLUX_FIELD_TAG_PROVIDER", "default")
    tag_folder = os.getenv("FLUX_FIELD_THREE_DEVICE_TAG_FOLDER", "FluxFieldThreeDevice")
    config_path = tmp_path / "three-device-field-config.json"
    cert_path = tmp_path / "pki"
    endpoint, field_tags = create_three_device_config(endpoint_url)
    config_path.write_text(
        json.dumps({"endpoints": [endpoint_config(endpoint)]}, indent=2),
        encoding="utf-8",
    )
    process = start_field_agent(config_path, cert_path)
    fx = fluxy.Fluxy(
        base_url=os.getenv("FLUXY_BASE_URL", "http://localhost:8088/system/webdev/flux"),
        token=os.getenv("FLUXY_TOKEN"),
        project_location=os.getenv("FLUXY_PROJECT_LOCATION", "../ignition_flux_project"),
    )

    tag_paths = ["[%s]%s/%s_%s" % (tag_provider, tag_folder, tag.device.name, tag.name) for tag in field_tags]
    try:
        wait_for_port("localhost", 4841)
        ensure_opcua_connection(fx, opc_server, endpoint_url)
        wait_for_opc_connected(fx, opc_server)
        configure_field_tags(fx, tag_provider, tag_folder, opc_server, field_tags)
        seen = {path: set() for path in tag_paths}
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and not all(len(values) > 1 for values in seen.values()):
            values = fx.tag.read_blocking(tag_paths)
            for value in values:
                if "Good" in value.quality:
                    seen[value.tag_path].add(normalize_sample(value.value))
            time.sleep(0.5)
    except FluxyError as exc:
        if "Trial Expired" in str(exc):
            pytest.skip("Ignition trial expired during Flux Field integration test")
        pytest.fail("Flux Field three-device integration failed: %s" % exc)
    finally:
        try:
            fx.tag.delete_tags("[%s]%s" % (tag_provider, tag_folder))
        except FluxyError:
            pass
        try:
            fx.opcua.remove_connection(opc_server)
        except Exception:
            try:
                run_opcua_connection_script(fx, "remove", opc_server, endpoint_url)
            except Exception:
                pass
        stop_field_agent(process)

    assert all(len(values) > 1 for values in seen.values()), seen


@pytest.mark.django_db(transaction=True)
def test_flux_field_integration_reads_string_tag(tmp_path):
    if os.getenv("FLUX_FIELD_INTEGRATION") != "1":
        pytest.skip("Set FLUX_FIELD_INTEGRATION=1 to run Flux Field Ignition integration")

    import fluxy
    from fluxy import FluxyError

    endpoint_url = os.getenv("FLUX_FIELD_STRING_ENDPOINT_URL", "opc.tcp://localhost:4842/flux/field")
    opc_server = os.getenv("FLUX_FIELD_STRING_OPC_SERVER", "Flux Field String")
    tag_provider = os.getenv("FLUX_FIELD_TAG_PROVIDER", "default")
    tag_folder = os.getenv("FLUX_FIELD_STRING_TAG_FOLDER", "FluxFieldString")
    config_path = tmp_path / "string-field-config.json"
    cert_path = tmp_path / "pki"
    endpoint, tag = create_single_string_config(endpoint_url)
    config_path.write_text(
        json.dumps({"endpoints": [endpoint_config(endpoint)]}, indent=2),
        encoding="utf-8",
    )
    process = start_field_agent(config_path, cert_path)
    fx = fluxy.Fluxy(
        base_url=os.getenv("FLUXY_BASE_URL", "http://localhost:8088/system/webdev/flux"),
        token=os.getenv("FLUXY_TOKEN"),
        project_location=os.getenv("FLUXY_PROJECT_LOCATION", "../ignition_flux_project"),
    )
    tag_path = "[%s]%s/%s_%s" % (tag_provider, tag_folder, tag.device.name, tag.name)

    try:
        wait_for_port("localhost", 4842)
        ensure_opcua_connection(fx, opc_server, endpoint_url)
        wait_for_opc_connected(fx, opc_server)
        configure_field_tags(fx, tag_provider, tag_folder, opc_server, [tag])
        values = sample_tag_values(fx, tag_path, 4, tag.update_rate_ms)
    except FluxyError as exc:
        if "Trial Expired" in str(exc):
            pytest.skip("Ignition trial expired during Flux Field integration test")
        pytest.fail("Flux Field string integration failed: %s" % exc)
    finally:
        cleanup_field_integration(fx, tag_provider, tag_folder, opc_server, endpoint_url)
        stop_field_agent(process)

    assert all("Good" in value.quality for value in values), values
    assert all(isinstance(value.value, str) for value in values), values
    assert len({value.value for value in values}) > 1, values


@pytest.mark.django_db(transaction=True)
def test_flux_field_stress_4000_tags_across_4_devices(tmp_path):
    if os.getenv("FLUX_FIELD_STRESS") != "1":
        pytest.skip("Set FLUX_FIELD_STRESS=1 to run 4000-tag Flux Field stress test")

    import fluxy
    from fluxy import FluxyError

    endpoint_url = os.getenv("FLUX_FIELD_STRESS_ENDPOINT_URL", "opc.tcp://localhost:4843/flux/field")
    opc_server = os.getenv("FLUX_FIELD_STRESS_OPC_SERVER", "Flux Field Stress")
    tag_provider = os.getenv("FLUX_FIELD_TAG_PROVIDER", "default")
    tag_folder = os.getenv("FLUX_FIELD_STRESS_TAG_FOLDER", "FluxFieldStress")
    config_path = tmp_path / "stress-field-config.json"
    cert_path = tmp_path / "pki"
    endpoint, field_tags = create_stress_config(endpoint_url, device_count=4, tags_per_device=1000)
    config_path.write_text(
        json.dumps({"endpoints": [endpoint_config(endpoint)]}, indent=2),
        encoding="utf-8",
    )
    process = start_field_agent(config_path, cert_path)
    fx = fluxy.Fluxy(
        base_url=os.getenv("FLUXY_BASE_URL", "http://localhost:8088/system/webdev/flux"),
        token=os.getenv("FLUXY_TOKEN"),
        project_location=os.getenv("FLUXY_PROJECT_LOCATION", "../ignition_flux_project"),
    )
    tag_paths = ["[%s]%s/%s_%s" % (tag_provider, tag_folder, tag.device.name, tag.name) for tag in field_tags]
    probe_paths = [
        "[%s]%s/%s_%s" % (tag_provider, tag_folder, tag.device.name, tag.name)
        for tag in [field_tags[0], field_tags[999], field_tags[1999], field_tags[3999]]
    ]

    try:
        wait_for_port("localhost", 4843)
        ensure_opcua_connection(fx, opc_server, endpoint_url)
        wait_for_opc_connected(fx, opc_server, timeout_seconds=60)
        configure_field_tags(fx, tag_provider, tag_folder, opc_server, field_tags)
        good_values = wait_for_good_values(fx, tag_paths, minimum_good_count=4000, timeout_seconds=120)
        seen = sample_probe_changes(fx, probe_paths, timeout_seconds=30)
    except FluxyError as exc:
        if "Trial Expired" in str(exc):
            pytest.skip("Ignition trial expired during Flux Field stress test")
        pytest.fail("Flux Field 4000-tag stress test failed: %s" % exc)
    finally:
        cleanup_field_integration(fx, tag_provider, tag_folder, opc_server, endpoint_url)
        stop_field_agent(process)

    assert len(good_values) == 4000
    assert all(len(values) > 1 for values in seen.values()), seen


def ensure_opcua_connection(fx, opc_server, endpoint_url):
    try:
        fx.opcua.remove_connection(opc_server)
    except Exception:
        pass
    try:
        fx.opcua.add_connection(
            opc_server,
            "Flux Field OPC UA simulator",
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
        run_opcua_connection_script(fx, "remove", opc_server, endpoint_url)
        run_opcua_connection_script(fx, "add", opc_server, endpoint_url)


def run_opcua_connection_script(fx, action, name, endpoint_url):
    fx.scripting.run_function_file(
        "opcua_connection",
        action,
        name,
        endpoint_url,
        target_directory="field",
    )


def wait_for_opc_connected(fx, opc_server, timeout_seconds=None):
    timeout_seconds = timeout_seconds or float(os.getenv("FLUX_FIELD_CONNECT_TIMEOUT_SECONDS", "30"))
    deadline = time.monotonic() + timeout_seconds
    last_state = None
    while time.monotonic() < deadline:
        servers = fx.opc.get_servers(include_disabled=True)
        if opc_server in servers:
            last_state = fx.opc.get_server_state(opc_server)
            if last_state and "CONNECT" in last_state.upper():
                return
        time.sleep(1)
    pytest.fail("OPC server %r did not connect; last_state=%r" % (opc_server, last_state))


def configure_opc_tag(
    fx, tag_provider, tag_folder, tag_name, data_type, opc_server, opc_item_path=None
):
    fx.tag.configure(
        [
            {
                "name": tag_folder,
                "tagType": "Folder",
                "tags": [
                    {
                        "name": tag_name,
                        "tagType": "AtomicTag",
                        "valueSource": "opc",
                        "dataType": ignition_data_type(data_type),
                        "opcServer": opc_server,
                        "opcItemPath": opc_item_path or "ns=2;s=FluxLogix001.%s" % tag_name,
                    }
                ],
            }
        ],
        base_path="[%s]" % tag_provider,
        collision_policy="o",
    )


def sample_tag_values(fx, tag_path, sample_count, update_rate_ms):
    values = []
    deadline = time.monotonic() + float(os.getenv("FLUX_FIELD_SAMPLE_TIMEOUT_SECONDS", "30"))
    sleep_seconds = max(update_rate_ms / 1000.0, 0.1)
    while len(values) < sample_count and time.monotonic() < deadline:
        value = fx.tag.read_blocking(tag_path)
        if "Good" in value.quality:
            values.append(value)
        time.sleep(sleep_seconds)
    return values


def configure_field_tags(fx, tag_provider, tag_folder, opc_server, field_tags):
    fx.tag.configure(
        [
            {
                "name": tag_folder,
                "tagType": "Folder",
                "tags": [
                    ignition_tag_config(tag, opc_server, tag_name="%s_%s" % (tag.device.name, tag.name))
                    for tag in field_tags
                ],
            }
        ],
        base_path="[%s]" % tag_provider,
        collision_policy="o",
    )


def wait_for_good_values(fx, tag_paths, minimum_good_count, timeout_seconds):
    deadline = time.monotonic() + timeout_seconds
    last_values = []
    while time.monotonic() < deadline:
        last_values = fx.tag.read_blocking(tag_paths)
        good_values = [value for value in last_values if "Good" in value.quality]
        if len(good_values) >= minimum_good_count:
            return good_values
        time.sleep(1)
    pytest.fail(
        "Expected %s Good values, got %s. Last qualities=%s"
        % (
            minimum_good_count,
            len([value for value in last_values if "Good" in value.quality]),
            sorted({value.quality for value in last_values})[:10],
        )
    )


def sample_probe_changes(fx, probe_paths, timeout_seconds):
    seen = {path: set() for path in probe_paths}
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline and not all(len(values) > 1 for values in seen.values()):
        values = fx.tag.read_blocking(probe_paths)
        for value in values:
            if "Good" in value.quality:
                seen[value.tag_path].add(normalize_sample(value.value))
        time.sleep(0.5)
    return seen


def cleanup_field_integration(fx, tag_provider, tag_folder, opc_server, endpoint_url):
    try:
        fx.tag.delete_tags("[%s]%s" % (tag_provider, tag_folder))
    except Exception:
        pass
    try:
        fx.opcua.remove_connection(opc_server)
    except Exception:
        try:
            run_opcua_connection_script(fx, "remove", opc_server, endpoint_url)
        except Exception:
            pass


def create_three_device_config(endpoint_url):
    endpoint = FieldEndpoint.objects.create(
        name="three-device-field",
        endpoint_url=endpoint_url,
        application_uri="urn:flux:field:three-device",
        product_uri="urn:flux:field",
        namespace_uri="urn:flux:field:three-device",
        security_policy="None",
    )
    tags = []
    for device_name in device_names():
        device = FieldDevice.objects.create(
            endpoint=endpoint,
            name=device_name,
            device_type="ControlLogix",
            browse_path="Devices",
        )
        tags.append(
            FieldTag.objects.create(
                device=device,
                name="Value",
                data_type=FieldTag.DataType.INT,
                update_rate_ms=500,
                simulation_type=FieldTag.SimulationType.RAMP,
                min_value=0,
                max_value=1000,
                variance=0,
                initial_value="0",
            )
        )
    return endpoint, tags


def create_single_string_config(endpoint_url):
    endpoint = FieldEndpoint.objects.create(
        name="string-field",
        endpoint_url=endpoint_url,
        application_uri="urn:flux:field:string",
        product_uri="urn:flux:field",
        namespace_uri="urn:flux:field:string",
        security_policy="None",
    )
    device = FieldDevice.objects.create(
        endpoint=endpoint,
        name="FluxLogixString",
        device_type="ControlLogix",
        browse_path="Devices",
    )
    tag = FieldTag.objects.create(
        device=device,
        name="StringTag",
        data_type=FieldTag.DataType.STRING,
        update_rate_ms=500,
        simulation_type=FieldTag.SimulationType.RAMP,
        initial_value="message",
    )
    return endpoint, tag


def create_stress_config(endpoint_url, device_count, tags_per_device):
    endpoint = FieldEndpoint.objects.create(
        name="stress-field",
        endpoint_url=endpoint_url,
        application_uri="urn:flux:field:stress",
        product_uri="urn:flux:field",
        namespace_uri="urn:flux:field:stress",
        security_policy="None",
    )
    field_tags = []
    for device_index in range(device_count):
        device = FieldDevice.objects.create(
            endpoint=endpoint,
            name="FluxStress%03d" % (device_index + 1),
            device_type="ControlLogix",
            browse_path="Devices",
        )
        tags = [
            FieldTag(
                device=device,
                name="Tag%04d" % tag_index,
                data_type=FieldTag.DataType.INT,
                update_rate_ms=1000,
                simulation_type=FieldTag.SimulationType.RAMP,
                min_value=0,
                max_value=100000,
                variance=0,
                initial_value="0",
            )
            for tag_index in range(tags_per_device)
        ]
        FieldTag.objects.bulk_create(tags)
        field_tags.extend(FieldTag.objects.filter(device=device).order_by("name"))
    return endpoint, field_tags


def device_names():
    return ["FluxLogix001", "FluxLogix002", "FluxLogix003"]


def start_field_agent(config_path, cert_path):
    repo_root = Path(__file__).resolve().parents[5]
    project_path = repo_root / "field" / "Flux.FieldAgent" / "Flux.FieldAgent.csproj"
    return subprocess.Popen(
        [
            "dotnet",
            "run",
            "--project",
            str(project_path),
            "--FluxField:ConfigPath=%s" % config_path,
            "--FluxField:CertificateStorePath=%s" % cert_path,
        ],
        cwd=repo_root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def stop_field_agent(process):
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def wait_for_port(host, port):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            if sock.connect_ex((host, port)) == 0:
                return
        time.sleep(0.25)
    pytest.fail("Timed out waiting for %s:%s" % (host, port))


def ignition_data_type(data_type):
    return {
        FieldTag.DataType.BOOL: "Boolean",
        FieldTag.DataType.INT: "Int4",
        FieldTag.DataType.FLOAT: "Float8",
        FieldTag.DataType.STRING: "String",
    }[data_type]


def normalize_sample(value):
    if isinstance(value, float):
        return round(value, 6)
    return value
