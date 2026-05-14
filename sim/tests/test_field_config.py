import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flux_sim.field_config import build_field_agent_config
from flux_sim.provider_import import import_provider_export


@dataclass(frozen=True)
class FakeTagRequest:
    tag_path: str
    value_source: str
    payload: str
    opc_server: str = ""
    data_type: str = ""
    resolved: bool = True


class FakeExpressionInterface:
    def flatten_tag_requests(self, tags: Any) -> tuple[FakeTagRequest, ...]:
        return (
            FakeTagRequest(
                tag_path="Area/Device01/PV",
                value_source="opc",
                payload="ns=2;s=Device01.40001F",
                opc_server="ACM_02",
                data_type="Float4",
            ),
        )

    def build_udt_type_index(self, tags: Any) -> dict[str, Any]:
        return {}

    def extract_expression_references(self, expression: str) -> tuple[str, ...]:
        return ()

    def resolve_parameter_binding(self, template: str, context: Any) -> Any:
        return template


def test_build_field_agent_config_uses_reconstruction_and_runtime(tmp_path: Path):
    source = tmp_path / "provider.json"
    database = tmp_path / "sim.db"
    source.write_text(json.dumps(provider_fixture()), encoding="utf-8")
    import_provider_export(source, database, provider_name="ACM02")

    config = build_field_agent_config(
        database,
        provider_name="ACM02",
        expression_interface=FakeExpressionInterface(),
        endpoint_url="opc.tcp://localhost:4840/acm02",
        namespace_uri="urn:test:acm02",
    )

    endpoint = config["endpoints"][0]
    assert endpoint["name"] == "ACM02"
    assert endpoint["endpoint_url"] == "opc.tcp://localhost:4840/acm02"
    assert endpoint["namespace_uri"] == "urn:test:acm02"
    assert endpoint["devices"][0]["name"] == "Device01"
    assert endpoint["devices"][0]["tags"][0]["node_id"] == "ns=2;s=Device01.40001F"
    assert endpoint["devices"][0]["tags"][0]["source_tag_path"] == "Area/Device01/PV"


def provider_fixture():
    return {
        "name": "",
        "tagType": "Provider",
        "tags": [
            {
                "name": "Area",
                "tagType": "Folder",
                "tags": [
                    {
                        "name": "Device01",
                        "tagType": "UdtInstance",
                        "typeId": "[Tag_02]_types_/Device/SP/RTU",
                    }
                ],
            }
        ],
    }
