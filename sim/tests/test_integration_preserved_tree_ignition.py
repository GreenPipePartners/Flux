import json
import os
import socket
import time
from pathlib import Path

import pytest

from flux_sim.configure_ignition import with_ignition_tree
from flux_sim.ignition import configure_ignition_from_field_config


pytestmark = pytest.mark.integration


def test_preserved_udt_member_adds_reads_deletes_and_confirms_gone():
    if os.getenv("FLUX_SIM_IGNITION_INTEGRATION") != "1":
        pytest.skip("Set FLUX_SIM_IGNITION_INTEGRATION=1 to run preserved-tree Ignition integration")

    import fluxy

    repo_root = Path(__file__).resolve().parents[2]
    field_config_path = repo_root / "sim" / "field-config.sim.json"
    database_path = repo_root / "sim" / "flux-sim.db"
    if not field_config_path.exists() or not database_path.exists():
        pytest.skip("field-config.sim.json and flux-sim.db are required for preserved-tree integration")

    field_config = with_ignition_tree(
        json.loads(field_config_path.read_text(encoding="utf-8")),
        database_path=database_path,
        provider_name="ACM02",
    )
    endpoint_url = field_config["endpoints"][0]["endpoint_url"]
    endpoint_host, endpoint_port = endpoint_host_port(endpoint_url)
    if not is_port_open(endpoint_host, endpoint_port):
        pytest.skip(f"FieldAgent endpoint is not listening: {endpoint_url}")

    fx = fluxy.Fluxy(
        base_url=os.getenv("FLUXY_BASE_URL", "http://localhost:8088/system/webdev/flux"),
        token=os.getenv("FLUXY_TOKEN"),
        project_location=os.getenv("FLUXY_PROJECT_LOCATION", str(repo_root / "ignition_flux_project")),
    )
    tag_provider = os.getenv("FLUX_SIM_TAG_PROVIDER", "default")
    tag_folder = os.getenv("FLUX_SIM_TAG_FOLDER", "ACM02")
    opc_server = os.getenv("FLUX_SIM_OPC_SERVER", "Flux Sim ACM02")
    target_path = (
        f"[{tag_provider}]{tag_folder}"
        "/WY/AL/PADS/AL01-16/AL01-16_RTU_35/METER/Meter_Gas_Sales_01/OPC/PRESSURE_DIFF"
    )

    runtime_root = f"[{tag_provider}]{tag_folder}"
    try:
        delete_if_present(fx, runtime_root)

        configure_ignition_from_field_config(
            fx,
            field_config,
            tag_provider=tag_provider,
            tag_folder=tag_folder,
            opc_server=opc_server,
            limit=100,
            batch_size=1,
            collision_policy="o",
        )

        value = wait_for_good_value(fx, target_path, timeout_ms=45000)
        assert value.quality.startswith("Good"), value
        assert value.value is not None

        delete_results = fx.tag.delete_tags([runtime_root])
        assert all(result.quality.startswith("Good") for result in delete_results), delete_results

        deleted_value = fx.tag.read_blocking(target_path, timeout_ms=45000)
        assert not deleted_value.quality.startswith("Good"), deleted_value
        assert "NotFound" in deleted_value.quality or "not found" in deleted_value.quality.lower(), deleted_value
    finally:
        delete_if_present(fx, runtime_root)


def wait_for_good_value(fx, tag_path: str, *, timeout_ms: int):
    deadline = time.monotonic() + timeout_ms / 1000.0
    last_value = None
    while time.monotonic() < deadline:
        last_value = fx.tag.read_blocking(tag_path, timeout_ms=timeout_ms)
        if last_value.quality.startswith("Good"):
            return last_value
        time.sleep(1)
    return last_value


def delete_if_present(fx, tag_path: str) -> None:
    try:
        fx.tag.delete_tags([tag_path])
    except Exception:
        pass


def endpoint_host_port(endpoint_url: str) -> tuple[str, int]:
    without_scheme = endpoint_url.split("://", 1)[-1]
    host_port = without_scheme.split("/", 1)[0]
    host, port = host_port.rsplit(":", 1)
    return host, int(port)


def is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(2)
        return sock.connect_ex((host, port)) == 0
