import json
import sqlite3
from pathlib import Path

from flux_sim.provider_import import import_provider_export, iter_tag_rows


def test_iter_tag_rows_preserves_hierarchy_and_opc_fields():
    rows = list(iter_tag_rows(provider_fixture()))

    assert [row["path"] for row in rows] == ["", "Area", "Area/Device01", "Area/Device01/PV"]
    assert rows[2]["type_id"] == "[Tag_02]_types_/Device/SP/RTU"
    assert rows[3]["opc_server"] == "ACM_02"
    assert rows[3]["opc_item_path"] == "ns=2;s=Device01.40001F"
    assert "tags" not in rows[2]["raw_config"]


def test_import_provider_export_writes_sqlite_schema(tmp_path: Path):
    source = tmp_path / "provider.json"
    database = tmp_path / "sim.db"
    source.write_text(json.dumps(provider_fixture()), encoding="utf-8")

    result = import_provider_export(source, database, provider_name="ACM02", batch_size=2)

    assert result.total_nodes == 4
    with sqlite3.connect(database) as connection:
        provider = connection.execute(
            "SELECT name, total_nodes, folder_count, atomic_tag_count, udt_instance_count FROM sim_provider"
        ).fetchone()
        tags = connection.execute(
            "SELECT path, tag_type, opc_server, opc_item_path FROM sim_imported_tag ORDER BY path"
        ).fetchall()
    assert provider == ("ACM02", 4, 1, 1, 1)
    assert tags == [
        ("", "Provider", "", ""),
        ("Area", "Folder", "", ""),
        ("Area/Device01", "UdtInstance", "", ""),
        ("Area/Device01/PV", "AtomicTag", "ACM_02", "ns=2;s=Device01.40001F"),
    ]


def provider_fixture():
    return {
        "name": "Tag_02",
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
                    }
                ],
            }
        ],
    }
