import json
from collections import Counter

from flux_sim.tag_data import load_tag_data_catalog, parse_device_inventory, strategy_key_for_driver


def test_parse_device_inventory_skips_details_rows_and_assigns_strategy_keys():
    devices = parse_device_inventory(
        "AB_CGF02\tControlLogix\tConnected: Protocol: EIP - Run Mode\t\n"
        "Details\n"
        "CGF04_EPOD\tModbusTcp\tConnected\t\n"
    )

    assert [device.name for device in devices] == ["AB_CGF02", "CGF04_EPOD"]
    assert devices[0].strategy_key == "logix"
    assert devices[1].strategy_key == "modbus"


def test_strategy_key_for_driver_maps_known_driver_families():
    assert strategy_key_for_driver("OPC UA") == "acm"
    assert strategy_key_for_driver("ControlLogix") == "logix"
    assert strategy_key_for_driver("CompactLogix") == "logix"
    assert strategy_key_for_driver("MicroLogix") == "logix"
    assert strategy_key_for_driver("ModbusTcp") == "modbus"
    assert strategy_key_for_driver("S7300") == "siemens"
    assert strategy_key_for_driver("SomethingElse") == "generic"


def test_load_tag_data_catalog_correlates_device_inventory_with_provider_export(tmp_path):
    devices_path = tmp_path / "devices.txt"
    tags_path = tmp_path / "tags.json"
    devices_path.write_text("RTU_01\tOPC UA\tCONNECTED\tServerClient\nPLC_01\tControlLogix\tConnected\t\n", encoding="utf-8")
    tags_path.write_text(json.dumps(provider_export_fixture()), encoding="utf-8")

    catalog = load_tag_data_catalog("Tag_02", devices_path=devices_path, tags_path=tags_path)
    profiles = catalog.device_profiles()
    bindings = catalog.device_tag_bindings()

    assert catalog.provider_name == "Tag_02"
    assert catalog.referenced_device_names == {"RTU_01", "PLC_01"}
    assert catalog.unreferenced_device_names == set()
    assert catalog.unknown_device_names == set()
    assert [(profile.device.name, profile.tag_count) for profile in profiles] == [("PLC_01", 1), ("RTU_01", 2)]
    assert profiles[0].device.strategy_key == "logix"
    assert profiles[1].data_type_counts == Counter({"Float4": 1, "Boolean": 1})
    assert [(binding.device_name, binding.tag_name, binding.strategy_key) for binding in bindings] == [
        ("RTU_01", "PV", "acm"),
        ("RTU_01", "Running", "acm"),
        ("PLC_01", "Standalone", "logix"),
    ]
    assert bindings[-1].address["local_member"] == "1:I.Data.0"


def test_single_acm_inventory_device_collects_referenced_field_devices(tmp_path):
    devices_path = tmp_path / "devices.txt"
    tags_path = tmp_path / "tags.json"
    devices_path.write_text("ACM_02\tOPC UA\tCONNECTED\tServerClient\n", encoding="utf-8")
    tags_path.write_text(json.dumps(provider_export_fixture()), encoding="utf-8")

    catalog = load_tag_data_catalog("Tag_02", devices_path=devices_path, tags_path=tags_path)
    bindings = catalog.device_tag_bindings()

    assert catalog.referenced_device_names == {"ACM_02"}
    assert catalog.unknown_device_names == set()
    assert catalog.unreferenced_device_names == set()
    assert {binding.device_name for binding in bindings} == {"ACM_02"}
    assert len(bindings) == 3


def provider_export_fixture():
    return {
        "name": "",
        "tagType": "Provider",
        "tags": [
            {
                "name": "Area",
                "tagType": "Folder",
                "tags": [
                    {
                        "name": "RTU_01",
                        "tagType": "UdtInstance",
                        "parameters": {"OPC_Device": "RTU_01"},
                        "tags": [
                            {
                                "name": "PV",
                                "tagType": "AtomicTag",
                                "valueSource": "opc",
                                "dataType": "Float4",
                                "opcItemPath": "ns=2;s=RTU_01.40001F",
                            },
                            {
                                "name": "Running",
                                "tagType": "AtomicTag",
                                "valueSource": "opc",
                                "dataType": "Boolean",
                                "opcItemPath": "ns=2;s=RTU_01.00001B",
                            },
                        ],
                    },
                    {
                        "name": "Standalone",
                        "tagType": "AtomicTag",
                        "valueSource": "opc",
                        "dataType": "Int4",
                        "opcItemPath": "ns=2;s=PLC_01.Local:1:I.Data.0",
                    },
                ],
            }
        ],
    }
