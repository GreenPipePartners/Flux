import json

from django.core.management import call_command
from django.test import TestCase

from .config import endpoint_config, ignition_tag_config
from .models import FieldDevice, FieldEndpoint, FieldNode, FieldTag


class FieldSmokeTests(TestCase):
    def test_field_index_loads(self):
        response = self.client.get("/field/")

        self.assertEqual(response.status_code, 200)

    def test_field_config_exports_seeded_nodes(self):
        response = self.client.get("/field/config.json")

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
        response = self.client.get("/field/config.json")

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
