import json
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from flux.base.field_config import endpoint_config, ignition_tag_config
from flux.base.models import Tag
from flux.sim.models import FieldEndpoint
from flux.field.ignition import configure_field_agent_ignition, configure_field_device_ignition
from flux.sim.models import DeviceConfig, TagConfig
from flux.sim.testing import create_device_config, create_tag_config


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
        fake = FakeFluxy()
        fluxy_class.return_value = fake
        endpoint = FieldEndpoint.objects.create(name="supervised-field")
        device = create_device_config(endpoint=endpoint, name="Device01")
        create_tag_config(device=device, name="PV", data_type=Tag.DataType.FLOAT, materialized=True)
        output = StringIO()

        call_command(
            "configure_field_ignition",
            "--field-agent-host",
            "127.0.0.1",
            "--supervised-base-port",
            "4900",
            stdout=output,
        )

        fluxy_class.assert_called_once()
        self.assertIn("Configured", output.getvalue())
        self.assertIn("[default]FieldAgent", output.getvalue())
        self.assertIn(
            "opc.tcp://127.0.0.1:%s/flux/sim/supervised-field" % (4900 + endpoint.id),
            [connection["endpoint_url"] for connection in fake.opcua.added],
        )

    def test_field_tag_derives_opc_paths(self):
        endpoint = FieldEndpoint.objects.create(name="path-field")
        device = create_device_config(endpoint=endpoint, name="PathLogix")
        tag = create_tag_config(
            device=device,
            name="Speed",
            data_type=Tag.DataType.INT,
            update_rate_ms=500,
            materialized=True,
        )

        self.assertEqual(tag.opc_item_path, "PathLogix/Speed")
        self.assertEqual(tag.node_id, "ns=2;s=PathLogix.Speed")

    def test_config_payload_is_json_serializable(self):
        response = self.client.get("/sim/field-config.json")

        json.dumps(response.json())

    def test_endpoint_config_exports_multiple_devices_from_database(self):
        endpoint = FieldEndpoint.objects.create(name="multi-field")
        for index in range(3):
            device = create_device_config(
                endpoint=endpoint,
                name="FluxLogix%03d" % (index + 1),
                device_type="ControlLogix",
            )
            create_tag_config(
                device=device,
                name="Value",
                data_type=Tag.DataType.INT,
                update_rate_ms=500,
                materialized=True,
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
        device = create_device_config(endpoint=endpoint, name="MapLogix")
        tag = create_tag_config(
            device=device,
            name="Temperature",
            data_type=Tag.DataType.FLOAT,
            update_rate_ms=1000,
            materialized=True,
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
        device = FakeDeviceConfig(
            endpoint=endpoint,
            name="Device A",
            tags=[FakeTagConfig(device_name="Device A", name="Temperature", data_type="float")],
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


class FakeDeviceConfig:
    def __init__(self, endpoint, name, tags):
        self.endpoint = endpoint
        self.base_device = SimpleNamespace(name=name, device_type="ControlLogix")
        self.name = name
        self.browse_path = "Devices"
        self.mode = DeviceConfig.Mode.STANDARD
        self.response_delay_ms = 0
        self.config = {}
        for tag in tags:
            tag.sim_device = self
        self.tags = FakeTagRelation(tags)


class FakeTagRelation:
    def __init__(self, tags):
        self.tags = tags

    def filter(self, **kwargs):
        if kwargs == {"enabled": True} or kwargs == {"materialized": True, "enabled": True}:
            return self
        raise AssertionError("unexpected filter: %r" % kwargs)

    def select_related(self, *fields):
        if fields != ("base_tag",):
            raise AssertionError("unexpected select_related: %r" % (fields,))
        return self

    def order_by(self, field):
        if field not in {"name", "tag_name"}:
            raise AssertionError("unexpected order_by: %r" % field)
        return sorted(self.tags, key=lambda tag: tag.name)


class FakeTagConfig:
    def __init__(self, device_name, name, data_type):
        self.device_name = device_name
        self.tag_name = name
        self.base_tag = SimpleNamespace(name=name, data_type=data_type, update_rate_ms=1000)
        self.simulation_type = TagConfig.SimulationType.RAMP
        self.min_value = None
        self.max_value = None
        self.variance = 0.0
        self.initial_value = ""
        self.behavior = TagConfig.Behavior.IMMEDIATE
        self.mode_config = None
        self.config = {}

    @property
    def name(self):
        return self.tag_name

    @property
    def data_type(self):
        return self.base_tag.data_type

    @property
    def update_rate_ms(self):
        return self.base_tag.update_rate_ms

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
