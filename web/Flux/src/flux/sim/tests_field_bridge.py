from django.core.management import call_command
from django.test import TestCase

from flux.base.models import (
    FieldDevice,
    FieldEndpoint,
    FieldTag,
    SimDevice,
    SimDeviceTag,
    SimDriver,
    SimServer,
    TagProvider,
)
from flux.base.field_config import endpoint_config, single_device_endpoint_config
from flux.sim.field_bridge import DEFAULT_SIM_SERVER_NAME, materialize_enabled_sim_devices


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
        endpoint = FieldEndpoint.objects.get(name=DEFAULT_SIM_SERVER_NAME)
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

    def test_materialize_multiple_sim_devices_under_one_runtime_server(self):
        first = self.create_sim_device(name="RTU_01")
        second = self.create_sim_device(name="RTU_02")
        for sim_device in [first, second]:
            SimDeviceTag.objects.create(
                provider=sim_device.provider,
                device=sim_device,
                source_path="Area/%s/PV" % sim_device.name,
                tag_name="PV",
                data_type="Float4",
                enabled=True,
            )

        result = materialize_enabled_sim_devices(provider_name="Tag_02")

        self.assertEqual(result.endpoint_count, 1)
        self.assertEqual(result.device_count, 2)
        endpoint = FieldEndpoint.objects.get(name=DEFAULT_SIM_SERVER_NAME)
        self.assertEqual(list(endpoint.devices.order_by("name").values_list("name", flat=True)), ["RTU_01", "RTU_02"])
        self.assertEqual([device["name"] for device in endpoint_config(endpoint)["devices"]], ["RTU_01", "RTU_02"])

    def test_materialize_different_providers_under_default_runtime_server(self):
        first = self.create_sim_device(provider_name="Tag_02", name="RTU_01")
        second = self.create_sim_device(provider_name="Tag_05", name="PLC_01")
        for sim_device in [first, second]:
            SimDeviceTag.objects.create(
                provider=sim_device.provider,
                device=sim_device,
                source_path="Area/%s/PV" % sim_device.name,
                tag_name="PV",
                data_type="Float4",
                enabled=True,
            )

        result = materialize_enabled_sim_devices()

        self.assertEqual(result.endpoint_count, 1)
        self.assertEqual(result.device_count, 2)
        self.assertEqual(
            list(FieldEndpoint.objects.order_by("name").values_list("name", flat=True)),
            [DEFAULT_SIM_SERVER_NAME],
        )

    def test_materialize_provider_with_explicit_server_under_that_runtime_server(self):
        sim_server = SimServer.objects.create(name="Flux sim Partner Server")
        sim_device = self.create_sim_device(provider_name="Partner", name="RemotePLC", sim_server=sim_server)
        SimDeviceTag.objects.create(
            provider=sim_device.provider,
            device=sim_device,
            source_path="Remote/PLC/PV",
            tag_name="PV",
            data_type="Float4",
            enabled=True,
        )

        result = materialize_enabled_sim_devices(provider_name="Partner")

        self.assertEqual(result.endpoint_count, 1)
        self.assertEqual(FieldEndpoint.objects.get().name, "Flux sim Partner Server")

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

    def create_sim_device(self, *, provider_name="Tag_02", name="RTU_01", mode=SimDevice.Mode.STANDARD, response_delay_ms=0, sim_server=None):
        provider, _created = TagProvider.objects.get_or_create(name=provider_name, defaults={"sim_server": sim_server})
        if sim_server is not None and provider.sim_server_id != sim_server.id:
            provider.sim_server = sim_server
            provider.save(update_fields=["sim_server"])
        driver, _created = SimDriver.objects.get_or_create(key="opc_ua", defaults={"label": "OPC UA", "strategy_key": "acm"})
        return SimDevice.objects.create(
            provider=provider,
            name=name,
            driver=driver,
            endpoint_url="opc.tcp://0.0.0.0:4840/flux/rtu_01",
            namespace_uri="urn:flux:test:rtu_01",
            mode=mode,
            response_delay_ms=response_delay_ms,
            enabled=True,
        )
