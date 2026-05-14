from flux_sim.ignition import configure_ignition_from_field_config, ignition_tag_configs
from flux_sim.configure_ignition import load_selected_paths


def test_ignition_tag_configs_convert_field_agent_tags_to_opc_tags():
    tags = list(ignition_tag_configs(field_config_fixture(), opc_server="Flux Sim ACM02"))

    assert tags == [
        {
            "name": "CASING_PRESSURE_abcd1234",
            "tagType": "AtomicTag",
            "valueSource": "opc",
            "dataType": "Float8",
            "opcServer": "Flux Sim ACM02",
            "opcItemPath": "ns=2;s=RTU_01.41600F",
        },
        {
            "name": "RUNNING_ffff0000",
            "tagType": "AtomicTag",
            "valueSource": "opc",
            "dataType": "Boolean",
            "opcServer": "Flux Sim ACM02",
            "opcItemPath": "ns=2;s=RTU_01.00001B",
        },
    ]


def test_configure_ignition_creates_connection_folder_and_batched_tags():
    fx = FakeFluxy()

    result = configure_ignition_from_field_config(
        fx,
        field_config_fixture(),
        tag_provider="default",
        tag_folder="ACM02",
        opc_server="Flux Sim ACM02",
        batch_size=1,
    )

    assert result.folder_path == "[default]ACM02"
    assert result.tag_count == 2
    assert result.batches == 2
    assert fx.opcua.removed == ["Flux Sim ACM02"]
    assert fx.opcua.added[0]["endpoint_url"] == "opc.tcp://localhost:4840/flux/sim"
    assert fx.tag.configured[0]["base_path"] == "[default]"
    assert fx.tag.configured[0]["tags"] == [{"name": "ACM02", "tagType": "Folder", "tags": []}]
    assert fx.tag.configured[1]["base_path"] == "[default]ACM02"
    assert fx.tag.configured[1]["tags"][0]["opcServer"] == "Flux Sim ACM02"


def test_configure_ignition_preserved_tree_splits_udt_types_from_runtime_tags():
    fx = FakeFluxy()

    result = configure_ignition_from_field_config(
        fx,
        tree_field_config_fixture(),
        tag_provider="default",
        tag_folder="ACM02",
        opc_server="Flux Sim ACM02",
        batch_size=10,
        limit=1,
    )

    assert result.folder_path == "[default]ACM02"
    assert result.tag_count == 2
    assert len(fx.tag.configured) == 3
    assert fx.tag.configured[0]["base_path"] == "[default]"
    assert [tag["name"] for tag in fx.tag.configured[0]["tags"]] == ["_types_"]
    assert fx.tag.configured[1] == {
        "base_path": "[default]",
        "collision_policy": "o",
        "tags": [{"name": "ACM02", "tagType": "Folder", "tags": []}],
    }
    assert fx.tag.configured[2]["base_path"] == "[default]ACM02"
    assert [tag["name"] for tag in fx.tag.configured[2]["tags"]] == ["Area"]


def test_ignition_tag_configs_preserve_provider_tree_and_redirect_udt_parameters():
    tags = list(ignition_tag_configs(tree_field_config_fixture(), opc_server="Flux Sim ACM02", limit=1))

    assert [tag["name"] for tag in tags] == ["_types_", "Area"]
    assert tags[0]["tags"][0]["tagType"] == "UdtType"
    udt_member = tags[0]["tags"][0]["tags"][0]
    assert udt_member["opcServer"] == {"bindType": "parameter", "binding": "{OPC_Server}"}

    device = tags[1]["tags"][0]
    assert device == {
        "name": "Device01",
        "tagType": "UdtInstance",
        "typeId": "[default]_types_/Device/RTU",
        "parameters": {
            "OPC_Server": {"dataType": "String", "value": "Flux Sim ACM02"},
            "OPC_Device": {"dataType": "String", "value": "RTU_01"},
        },
    }


def test_ignition_tag_configs_strip_gateway_specific_tag_groups():
    tags = list(ignition_tag_configs(tree_field_config_fixture(), opc_server="Flux Sim ACM02", limit=1))

    udt_member = tags[0]["tags"][0]["tags"][0]
    assert "tagGroup" not in udt_member


def test_ignition_tag_configs_use_selected_source_paths_from_ui_export():
    field_config = tree_field_config_fixture()
    field_config["ignition"]["selected_source_paths"] = ["Area/Device01/PV"]

    tags = list(ignition_tag_configs(field_config, opc_server="Flux Sim ACM02"))

    assert [tag["name"] for tag in tags] == ["_types_", "Area"]
    assert [child["name"] for child in tags[1]["tags"]] == ["Device01"]


def test_load_selected_paths_accepts_django_export_shape(tmp_path):
    path = tmp_path / "selected.json"
    path.write_text('{"provider":"ACM02","selected_source_paths":["Area/Device01/PV"]}', encoding="utf-8")

    assert load_selected_paths(path) == ["Area/Device01/PV"]


def test_ignition_tag_configs_preserve_direct_opc_tags_under_original_path():
    tags = list(ignition_tag_configs(direct_tree_field_config_fixture(), opc_server="Flux Sim ACM02"))

    assert tags == [
        {
            "name": "Area",
            "tagType": "Folder",
            "tags": [
                {
                    "name": "PV",
                    "tagType": "AtomicTag",
                    "valueSource": "opc",
                    "dataType": "Float4",
                    "opcServer": "Flux Sim ACM02",
                    "opcItemPath": "ns=2;s=RTU_01.40001F",
                }
            ],
        }
    ]


class FakeFluxy:
    def __init__(self):
        self.opcua = FakeOpcUa()
        self.opc = FakeOpc()
        self.tag = FakeTag()
        self.scripting = FakeScripting()


class FakeOpcUa:
    def __init__(self):
        self.removed = []
        self.added = []

    def remove_connection(self, name):
        self.removed.append(name)

    def add_connection(self, name, description, discovery_url, endpoint_url, **kwargs):
        self.added.append(
            {
                "name": name,
                "description": description,
                "discovery_url": discovery_url,
                "endpoint_url": endpoint_url,
                **kwargs,
            }
        )


class FakeOpc:
    def get_servers(self, include_disabled=False):
        return ["Flux Sim ACM02"]

    def get_server_state(self, opc_server):
        return "Connected"


class FakeTag:
    def __init__(self):
        self.configured = []

    def configure(self, tags, *, base_path, collision_policy):
        self.configured.append(
            {"tags": tags, "base_path": base_path, "collision_policy": collision_policy}
        )


class FakeScripting:
    def run_function_file(self, *args, **kwargs):
        raise AssertionError("scripting fallback should not be used")


def field_config_fixture():
    return {
        "endpoints": [
            {
                "name": "ACM02",
                "endpoint_url": "opc.tcp://localhost:4840/flux/sim",
                "namespace_uri": "urn:flux:sim:acm02",
                "devices": [
                    {
                        "name": "RTU_01",
                        "tags": [
                            {
                                "name": "CASING_PRESSURE_abcd1234",
                                "node_id": "ns=2;s=RTU_01.41600F",
                                "data_type": "float",
                            },
                            {
                                "name": "RUNNING_ffff0000",
                                "node_id": "ns=2;s=RTU_01.00001B",
                                "data_type": "bool",
                            },
                        ],
                    }
                ],
            }
        ]
    }


def tree_field_config_fixture():
    return {
        "ignition": {
            "provider_name": "ACM02",
            "tags": [
                {
                    "name": "_types_",
                    "tagType": "Folder",
                    "tags": [
                        {
                            "name": "RTU",
                            "tagType": "UdtType",
                            "tags": [
                                {
                                    "name": "PV",
                                    "tagType": "AtomicTag",
                                    "valueSource": "opc",
                                    "dataType": "Float4",
                                    "opcServer": {"bindType": "parameter", "binding": "{OPC_Server}"},
                                    "opcItemPath": {
                                        "bindType": "parameter",
                                        "binding": "ns=2;s={OPC_Device}.40001F",
                                    },
                                    "tagGroup": "Tubing_Casing",
                                }
                            ],
                        }
                    ],
                },
                {
                    "name": "Area",
                    "tagType": "Folder",
                    "tags": [
                        {
                            "name": "Device01",
                            "tagType": "UdtInstance",
                            "typeId": "[Tag_02]_types_/Device/RTU",
                            "parameters": {
                                "OPC_Server": {"dataType": "String", "value": "ACM_02"},
                                "OPC_Device": {"dataType": "String", "value": "RTU_01"},
                            },
                        },
                        {"name": "Device02", "tagType": "UdtInstance", "typeId": "[Tag_02]_types_/Device/RTU"},
                    ],
                },
            ],
        },
        "endpoints": [
            {
                "endpoint_url": "opc.tcp://localhost:4840/flux/sim",
                "devices": [
                    {
                        "name": "RTU_01",
                        "tags": [
                            {
                                "name": "PV_abcd1234",
                                "node_id": "ns=2;s=RTU_01.40001F",
                                "source_tag_path": "Area/Device01/PV",
                                "data_type": "float",
                            }
                        ],
                    }
                ],
            }
        ],
    }


def direct_tree_field_config_fixture():
    return {
        "ignition": {
            "provider_name": "ACM02",
            "tags": [
                {
                    "name": "Area",
                    "tagType": "Folder",
                    "tags": [
                        {
                            "name": "PV",
                            "tagType": "AtomicTag",
                            "valueSource": "opc",
                            "dataType": "Float4",
                            "opcServer": "ACM_02",
                            "opcItemPath": "ns=2;s=RTU_01.40001F",
                        }
                    ],
                }
            ],
        },
        "endpoints": [{"endpoint_url": "opc.tcp://localhost:4840/flux/sim", "devices": []}],
    }
