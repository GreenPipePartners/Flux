import json
from pathlib import Path
from typing import Any

from flux_sim.provider_import import import_provider_export
from flux_sim.reconstruction import build_sim_provider_model, load_imported_provider_tree


def test_load_imported_provider_tree_reconstructs_tag_config(tmp_path: Path):
    database = import_fixture(tmp_path)

    tree = load_imported_provider_tree(database, "ACM02")

    assert tree.to_tag_config() == provider_fixture()
    assert tree.tags[0]["tags"][0]["tags"][0]["opcItemPath"] == "ns=2;s=Device01.40001F"


def test_build_sim_provider_model_uses_expression_interface_boundary(tmp_path: Path):
    database = import_fixture(tmp_path)
    tree = load_imported_provider_tree(database, "ACM02")
    expression_interface = FakeExpressionInterface()

    model = build_sim_provider_model(tree, expression_interface=expression_interface)

    assert [tag.path for tag in model.tags] == ["Area", "Area/Device01", "Area/Device01/PV", "Area/Calc"]
    assert model.tags[2].opc_item_path == "ns=2;s=Device01.40001F"
    assert model.tags[3].expression == "{[.]PV} + 1"
    assert model.requests == ("request:Area",)
    assert model.udt_type_index == {"Device/Type": {"tagType": "UdtType"}}
    assert expression_interface.seen_tags[0]["name"] == "Area"


class FakeExpressionInterface:
    def __init__(self):
        self.seen_tags: tuple[dict[str, Any], ...] = ()

    def flatten_tag_requests(self, tags: Any) -> tuple[str, ...]:
        self.seen_tags = tuple(tags)
        return ("request:Area",)

    def build_udt_type_index(self, tags: Any) -> dict[str, Any]:
        return {"Device/Type": {"tagType": "UdtType"}}

    def extract_expression_references(self, expression: str) -> tuple[str, ...]:
        return (expression,)

    def resolve_parameter_binding(self, template: str, context: Any) -> str:
        return template


def import_fixture(tmp_path: Path) -> Path:
    source = tmp_path / "provider.json"
    database = tmp_path / "sim.db"
    source.write_text(json.dumps(provider_fixture()), encoding="utf-8")
    import_provider_export(source, database, provider_name="ACM02")
    return database


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
                        "parameters": {"OPC_Server": {"value": "ACM_02", "dataType": "String"}},
                        "tags": [
                            {
                                "name": "PV",
                                "tagType": "AtomicTag",
                                "valueSource": "opc",
                                "dataType": "Float4",
                                "opcServer": "ACM_02",
                                "opcItemPath": "ns=2;s=Device01.40001F",
                            }
                        ],
                    },
                    {
                        "name": "Calc",
                        "tagType": "AtomicTag",
                        "valueSource": "expr",
                        "dataType": "Float4",
                        "expression": "{[.]PV} + 1",
                    },
                ],
            }
        ],
    }
