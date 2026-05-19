from django.core.management import call_command
from django.test import TestCase

from flux.base.models import (
    FieldDevice,
    FieldEndpoint,
    FieldTag,
    SimDevice,
    SimDeviceTag,
    SimDriver,
    TagProvider,
)
from flux.base.field_config import single_device_endpoint_config
from flux.sim.field_bridge import field_endpoint_name, materialize_enabled_sim_devices


class SimFieldBridgeTests(TestCase):
    def setUp(self):
        FieldEndpoint.objects.all().delete()

    def test_materialize_enabled_sim_device_creates_one_runtime_device_with_tags(self):
        sim_device = self.create_sim_device()
        SimDeviceTag.objects.create(
            provider=sim_device.provider,
            device=sim_device,
            source_path="Area/RTU_01/PV",
            tag_name="PV",
            data_type="Float4",
            enabled=True,
        )
        SimDeviceTag.objects.create(
            provider=sim_device.provider,
            device=sim_device,
            source_path="Area/RTU_01/Running",
            tag_name="Running",
            data_type="Boolean",
            enabled=True,
        )

        result = materialize_enabled_sim_devices(provider_name="Tag_02")

        self.assertEqual(result.device_count, 1)
        self.assertEqual(result.tag_count, 2)
        endpoint = FieldEndpoint.objects.get(name=field_endpoint_name(sim_device))
        runtime_device = FieldDevice.objects.get(endpoint=endpoint, name="RTU_01")
        self.assertEqual(FieldDevice.objects.count(), 1)
        self.assertEqual(runtime_device.device_type, "OPC UA")
        self.assertEqual(runtime_device.browse_path, "Tag_02")
        self.assertEqual(runtime_device.config["mode"], SimDevice.Mode.STANDARD)
        self.assertNotIn("response_delay_ms", runtime_device.config)
        self.assertEqual(
            list(
                runtime_device.tags.order_by("name").values_list("name", "data_type", "description")
            ),
            [
                ("PV", FieldTag.DataType.FLOAT, "Area/RTU_01/PV"),
                ("Running", FieldTag.DataType.BOOL, "Area/RTU_01/Running"),
            ],
        )

    def test_materialize_enabled_sim_device_is_idempotent(self):
        sim_device = self.create_sim_device()
        SimDeviceTag.objects.create(
            provider=sim_device.provider,
            device=sim_device,
            source_path="Area/RTU_01/PV",
            tag_name="PV",
            data_type="Float4",
            enabled=True,
        )

        materialize_enabled_sim_devices(provider_name="Tag_02")
        materialize_enabled_sim_devices(provider_name="Tag_02")

        self.assertEqual(FieldEndpoint.objects.count(), 1)
        self.assertEqual(FieldDevice.objects.count(), 1)
        self.assertEqual(FieldTag.objects.count(), 1)

    def test_standard_mode_exports_mode_without_delay_metadata(self):
        sim_device = self.create_sim_device(response_delay_ms=250)
        SimDeviceTag.objects.create(
            provider=sim_device.provider,
            device=sim_device,
            source_path="Area/RTU_01/PV",
            tag_name="PV",
            data_type="Float4",
            enabled=True,
        )

        materialize_enabled_sim_devices(provider_name="Tag_02")

        runtime_device = FieldDevice.objects.get(name="RTU_01")
        config = single_device_endpoint_config(runtime_device)
        device_config = config["devices"][0]
        self.assertEqual(device_config["mode"], SimDevice.Mode.STANDARD)
        self.assertNotIn("response_delay_ms", device_config)
        self.assertEqual(device_config["metadata"]["mode"], SimDevice.Mode.STANDARD)
        self.assertNotIn("response_delay_ms", device_config["metadata"])

    def test_slow_network_mode_exports_deterministic_delay_metadata(self):
        sim_device = self.create_sim_device(
            mode=SimDevice.Mode.SLOW_NETWORK,
            response_delay_ms=750,
        )
        SimDeviceTag.objects.create(
            provider=sim_device.provider,
            device=sim_device,
            source_path="Area/RTU_01/PV",
            tag_name="PV",
            data_type="Float4",
            enabled=True,
        )

        materialize_enabled_sim_devices(provider_name="Tag_02")

        runtime_device = FieldDevice.objects.get(name="RTU_01")
        config = single_device_endpoint_config(runtime_device)
        device_config = config["devices"][0]
        self.assertEqual(runtime_device.config["mode"], SimDevice.Mode.SLOW_NETWORK)
        self.assertEqual(runtime_device.config["response_delay_ms"], 750)
        self.assertEqual(device_config["mode"], SimDevice.Mode.SLOW_NETWORK)
        self.assertEqual(device_config["response_delay_ms"], 750)
        self.assertEqual(device_config["metadata"]["source"], "sim_device")
        self.assertEqual(device_config["metadata"]["sim_device_id"], sim_device.id)
        self.assertEqual(FieldTag.objects.get().name, "PV")

    def test_tag_behavior_metadata_survives_materialize_and_config_export(self):
        sim_device = self.create_sim_device()
        sim_tag = SimDeviceTag.objects.create(
            provider=sim_device.provider,
            device=sim_device,
            source_path="Area/RTU_01/Command",
            tag_name="Command",
            data_type="Int4",
            behavior=SimDeviceTag.Behavior.WRITE_TO_OTHER_TAG_RESPONSE,
            mode_config={"response_tag_path": "[default]Area/RTU_01/Response", "response_value": 10},
            enabled=True,
        )

        materialize_enabled_sim_devices(provider_name="Tag_02")

        sim_tag.refresh_from_db()
        self.assertEqual(sim_tag.behavior, SimDeviceTag.Behavior.WRITE_TO_OTHER_TAG_RESPONSE)
        self.assertEqual(sim_tag.mode_config["response_value"], 10)
        field_tag = FieldTag.objects.get(name="Command")
        self.assertEqual(field_tag.config["source"], "sim_device_tag")
        self.assertEqual(field_tag.config["sim_device_tag_id"], sim_tag.id)
        self.assertEqual(field_tag.config["source_path"], "Area/RTU_01/Command")
        self.assertEqual(field_tag.config["behavior"], SimDeviceTag.Behavior.WRITE_TO_OTHER_TAG_RESPONSE)
        self.assertEqual(field_tag.config["mode_config"]["response_value"], 10)

        runtime_device = FieldDevice.objects.get(name="RTU_01")
        tag_config = single_device_endpoint_config(runtime_device)["devices"][0]["tags"][0]
        self.assertEqual(tag_config["behavior"], SimDeviceTag.Behavior.WRITE_TO_OTHER_TAG_RESPONSE)
        self.assertEqual(tag_config["mode_config"]["response_value"], 10)
        self.assertEqual(tag_config["metadata"]["sim_device_tag_id"], sim_tag.id)

    def test_materialize_command_runs_bridge(self):
        sim_device = self.create_sim_device()
        SimDeviceTag.objects.create(
            provider=sim_device.provider,
            device=sim_device,
            source_path="Area/RTU_01/PV",
            tag_name="PV",
            data_type="Float4",
            enabled=True,
        )

        call_command("materialize_sim_field_config", "--provider", "Tag_02")

        self.assertEqual(FieldDevice.objects.count(), 1)
        self.assertEqual(FieldTag.objects.count(), 1)

    def create_sim_device(self, *, mode=SimDevice.Mode.STANDARD, response_delay_ms=0):
        provider = TagProvider.objects.create(name="Tag_02")
        driver = SimDriver.objects.create(key="opc_ua", label="OPC UA", strategy_key="acm")
        return SimDevice.objects.create(
            provider=provider,
            name="RTU_01",
            driver=driver,
            endpoint_url="opc.tcp://0.0.0.0:4840/flux/rtu_01",
            namespace_uri="urn:flux:test:rtu_01",
            mode=mode,
            response_delay_ms=response_delay_ms,
            enabled=True,
        )
