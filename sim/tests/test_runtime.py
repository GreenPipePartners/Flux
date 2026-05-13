from dataclasses import dataclass

from flux_sim.reconstruction import SimProviderModel
from flux_sim.runtime import SimulatedOpcServer


@dataclass(frozen=True)
class FakeTagRequest:
    tag_path: str
    value_source: str
    payload: str
    opc_server: str = ""
    data_type: str = ""
    resolved: bool = True


def test_simulated_opc_server_materializes_resolved_opc_requests():
    model = SimProviderModel(
        provider_name="ACM02",
        tags=(),
        requests=(
            FakeTagRequest(
                tag_path="Pad_A/Well_01/CASING_PRESSURE",
                value_source="opc",
                payload="ns=2;s=RTU_01.41600F<I3>",
                opc_server="ACM_02",
                data_type="Float4",
            ),
            FakeTagRequest(
                tag_path="Pad_A/Well_01/BAD",
                value_source="opc",
                payload="{Missing}",
                opc_server="ACM_02",
                data_type="Float4",
                resolved=False,
            ),
            FakeTagRequest(tag_path="Pad_A/Calc", value_source="expr", payload="{[.]A}+1"),
        ),
    )

    server = SimulatedOpcServer.from_provider_model(model)

    assert server.tag_count == 1
    result = server.read("ACM_02", "ns=2;s=RTU_01.41600F<I3>")
    assert result.quality == "Good"
    assert result.source_tag_path == "Pad_A/Well_01/CASING_PRESSURE"
    assert isinstance(result.value, float)


def test_simulated_opc_server_supports_write_tick_and_snapshot():
    model = SimProviderModel(
        provider_name="ACM02",
        tags=(),
        requests=(
            FakeTagRequest(
                tag_path="Pad_A/Well_01/RUNNING",
                value_source="opc",
                payload="ns=2;s=RTU_01.00001B",
                opc_server="ACM_02",
                data_type="Boolean",
            ),
        ),
    )
    server = SimulatedOpcServer.from_provider_model(model)

    server.write("ACM_02", "ns=2;s=RTU_01.00001B", True)
    assert server.read("ACM_02", "ns=2;s=RTU_01.00001B").value is True

    server.tick()
    snapshot = server.snapshot()

    row = snapshot["ACM_02|ns=2;s=RTU_01.00001B"]
    assert row["sampleIndex"] == 1
    assert row["quality"] == "Good"


def test_simulated_opc_server_exports_field_agent_config():
    model = SimProviderModel(
        provider_name="ACM02",
        tags=(),
        requests=(
            FakeTagRequest(
                tag_path="Pad_A/Well_01/CASING_PRESSURE",
                value_source="opc",
                payload="ns=2;s=RTU_01.41600F<I3>",
                opc_server="ACM_02",
                data_type="Float4",
            ),
            FakeTagRequest(
                tag_path="Pad_A/Well_02/CASING_PRESSURE",
                value_source="opc",
                payload="ns=2;s=RTU_02.41600F<I3>",
                opc_server="ACM_02",
                data_type="Float4",
            ),
        ),
    )

    config = SimulatedOpcServer.from_provider_model(model).to_field_agent_config(endpoint_name="ACM02")

    endpoint = config["endpoints"][0]
    assert endpoint["name"] == "ACM02"
    assert [device["name"] for device in endpoint["devices"]] == ["RTU_01", "RTU_02"]
    assert endpoint["devices"][0]["browse_path"] == "ACM_02"
    assert endpoint["devices"][0]["tags"][0]["node_id"] == "ns=2;s=RTU_01.41600F<I3>"
    assert endpoint["devices"][0]["tags"][0]["data_type"] == "float"
