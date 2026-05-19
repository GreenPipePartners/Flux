import json
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from flux.base.field_config import endpoint_config, ignition_tag_config
from flux.base.models import FieldDevice, FieldEndpoint, FieldNode, FieldTag
from flux.field.ignition import configure_field_agent_ignition, configure_field_device_ignition


class FieldSmokeTests(TestCase):
    def test_sim_index_loads(self):
        response = self.client.get("/sim/")

        self.assertEqual(response.status_code, 200)

    def test_field_config_exports_seeded_nodes(self):
        response = self.client.get("/sim/field-config.json")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["endpoints"][0]["name"], "local-field")
        self.assertEqual(payload["endpoints"][0]["devices"][0]["name"], "FluxLogix001")
        self.assertEqual(len(payload["endpoints"][0]["devices"][0]["tags"]), 3)
        self.assertEqual(
            {tag["data_type"] for tag in payload["endpoints"][0]["devices"][0]["tags"]},
            {"bool", "int", "float"},
        )

    def test_export_field_config_command(self):
        call_command("export_field_config")

    @patch("flux.field.management.commands.configure_field_ignition.fluxy.Fluxy")
    def test_configure_field_ignition_command_uses_fluxy_helper(self, fluxy_class):
        fluxy_class.return_value = FakeFluxy()
        output = StringIO()

        call_command("configure_field_ignition", stdout=output)

        fluxy_class.assert_called_once()
        self.assertIn("Configured", output.getvalue())
        self.assertIn("[default]FieldAgent", output.getvalue())

    def test_field_node_can_map_custom_device_tag(self):
        endpoint = FieldEndpoint.objects.create(name="custom-field")
        device = FieldDevice.objects.create(endpoint=endpoint, name="CustomLogix")
        tag = FieldTag.objects.create(
            device=device,
            name="CustomFloat",
            data_type=FieldTag.DataType.FLOAT,
            simulation_type=FieldTag.SimulationType.WAVE,
            update_rate_ms=250,
        )

        node = FieldNode.objects.create(
            endpoint=endpoint,
            field_tag=tag,
            node_id=tag.node_id,
            browse_name="CustomFloat",
        )

        self.assertEqual(node.label, "CustomFloat")

    def test_field_tag_derives_opc_paths(self):
        endpoint = FieldEndpoint.objects.create(name="path-field")
        device = FieldDevice.objects.create(endpoint=endpoint, name="PathLogix")
        tag = FieldTag.objects.create(
            device=device,
            name="Speed",
            data_type=FieldTag.DataType.INT,
            update_rate_ms=500,
        )

        self.assertEqual(tag.opc_item_path, "PathLogix/Speed")
        self.assertEqual(tag.node_id, "ns=2;s=PathLogix.Speed")

    def test_config_payload_is_json_serializable(self):
        response = self.client.get("/sim/field-config.json")

        json.dumps(response.json())

    def test_endpoint_config_exports_multiple_devices_from_database(self):
        endpoint = FieldEndpoint.objects.create(name="multi-field")
        for index in range(3):
            device = FieldDevice.objects.create(
                endpoint=endpoint,
                name="FluxLogix%03d" % (index + 1),
                device_type="ControlLogix",
            )
            FieldTag.objects.create(
                device=device,
                name="Value",
                data_type=FieldTag.DataType.INT,
                update_rate_ms=500,
            )

        config = endpoint_config(endpoint)

        self.assertEqual(len(config["devices"]), 3)
        self.assertEqual(
            [device["name"] for device in config["devices"]],
            ["FluxLogix001", "FluxLogix002", "FluxLogix003"],
        )
        self.assertEqual(config["devices"][0]["tags"][0]["node_id"], "ns=2;s=FluxLogix001.Value")

    def test_ignition_tag_config_uses_field_tag_mapping(self):
        endpoint = FieldEndpoint.objects.create(name="ignition-map-field")
        device = FieldDevice.objects.create(endpoint=endpoint, name="MapLogix")
        tag = FieldTag.objects.create(
            device=device,
            name="Temperature",
            data_type=FieldTag.DataType.FLOAT,
            update_rate_ms=1000,
        )

        config = ignition_tag_config(tag, "Flux Field", tag_name="MapLogix_Temperature")

        self.assertEqual(config["name"], "MapLogix_Temperature")
        self.assertEqual(config["dataType"], "Float8")
        self.assertEqual(config["opcItemPath"], "ns=2;s=MapLogix.Temperature")

class FieldIgnitionServiceTests(SimpleTestCase):
    def test_configure_field_device_ignition_uses_fluxy_opcua_and_tag_apis(self):
        endpoint = FakeFieldEndpoint(
            name="device-field",
            endpoint_url="opc.tcp://127.0.0.1:54840/flux/field/device",
        )
        device = FakeFieldDevice(
            endpoint=endpoint,
            name="Device A",
            tags=[FakeFieldTag(device_name="Device A", name="Temperature", data_type="float")],
        )
        fx = FakeFluxy()

        result = configure_field_device_ignition(fx, device, tag_provider="testing")

        self.assertEqual(result.connection_names, ["Flux Field device-field"])
        self.assertEqual(result.tag_base_path, "[testing]")
        self.assertEqual(result.tag_folder, "Device_A")
        self.assertEqual(result.tag_count, 1)
        self.assertEqual(fx.tag.deleted, ["[testing]Device_A"])
        self.assertEqual(fx.opcua.removed, ["Flux Field device-field"])
        self.assertEqual(fx.opcua.added[0]["name"], "Flux Field device-field")
        self.assertEqual(fx.opcua.added[0]["endpoint_url"], endpoint.endpoint_url)
        self.assertEqual(fx.opcua.added[0]["settings"]["CERTIFICATEVALIDATIONENABLED"], False)
        self.assertEqual(fx.tag.configured[0]["base_path"], "[testing]")
        configured_tag = fx.tag.configured[0]["tags"][0]["tags"][0]
        self.assertEqual(configured_tag["name"], "Device_A_Temperature")
        self.assertEqual(configured_tag["dataType"], "Float8")
        self.assertEqual(configured_tag["opcServer"], "Flux Field device-field")
        self.assertEqual(configured_tag["opcItemPath"], "ns=2;s=Device A.Temperature")

    def test_configure_field_agent_ignition_configures_multiple_connections_and_tags(self):
        fx = FakeFluxy()
        config = {
            "endpoints": [
                {
                    "name": "agent-a",
                    "endpoint_url": "opc.tcp://127.0.0.1:54841/flux/field/a",
                    "security_policy": "None",
                    "devices": [
                        {
                            "name": "PLC 1",
                            "tags": [
                                {"name": "Running", "data_type": "bool", "node_id": "ns=2;s=PLC1.Running"}
                            ],
                        }
                    ],
                },
                {
                    "name": "agent-b",
                    "endpoint_url": "opc.tcp://127.0.0.1:54842/flux/field/b",
                    "security_policy": "None",
                    "devices": [
                        {
                            "name": "PLC 2",
                            "tags": [
                                {"name": "Count", "data_type": "int", "node_id": "ns=2;s=PLC2.Count"}
                            ],
                        }
                    ],
                },
            ]
        }

        result = configure_field_agent_ignition(fx, config, tag_provider="[default]", tag_folder="TestField")

        self.assertEqual(result.connection_names, ["Flux Field agent-a", "Flux Field agent-b"])
        self.assertEqual(result.tag_count, 2)
        self.assertEqual([call["name"] for call in fx.opcua.added], result.connection_names)
        configured_tags = fx.tag.configured[0]["tags"][0]["tags"]
        self.assertEqual([tag["name"] for tag in configured_tags], ["PLC_1_Running", "PLC_2_Count"])
        self.assertEqual([tag["opcServer"] for tag in configured_tags], result.connection_names)


class FakeFieldEndpoint:
    def __init__(self, name, endpoint_url):
        self.name = name
        self.endpoint_url = endpoint_url
        self.application_uri = "urn:flux:test"
        self.product_uri = "urn:flux:test"
        self.namespace_uri = "urn:flux:test"
        self.security_policy = "None"


class FakeFieldDevice:
    def __init__(self, endpoint, name, tags):
        self.endpoint = endpoint
        self.name = name
        self.device_type = "ControlLogix"
        self.browse_path = "Devices"
        self.config = {}
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


class FakeFieldTag:
    def __init__(self, device_name, name, data_type):
        self.device_name = device_name
        self.name = name
        self.data_type = data_type
        self.update_rate_ms = 1000
        self.simulation_type = "ramp"
        self.min_value = None
        self.max_value = None
        self.variance = 0.0
        self.initial_value = ""
        self.config = {}

    @property
    def node_id(self):
        return "ns=2;s=%s.%s" % (self.device_name, self.name)

    @property
    def browse_name(self):
        return self.name

    @property
    def opc_item_path(self):
        return "%s/%s" % (self.device_name, self.name)


class FakeFluxy:
    def __init__(self):
        self.opcua = FakeOpcUaNamespace()
        self.tag = FakeTagNamespace()


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


class FakeTagNamespace:
    def __init__(self):
        self.configured = []
        self.deleted = []

    def configure(self, tags, base_path=None, collision_policy="o"):
        self.configured.append(
            {"tags": tags, "base_path": base_path, "collision_policy": collision_policy}
        )
        return []

    def delete_tags(self, tag_paths):
        self.deleted.append(tag_paths)
        return []
