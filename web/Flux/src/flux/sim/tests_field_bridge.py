from django.core.management import call_command
from django.test import TestCase

from flux.base.field_config import endpoint_config, single_device_endpoint_config
from flux.base.models import Device, Tag
from flux.sim.models import FieldEndpoint
from flux.sim.models import SimDriver, SimServer, TagProvider
from flux.sim.field_bridge import DEFAULT_SIM_SERVER_NAME, materialize_enabled_sim_devices
from flux.sim.models import DeviceConfig, TagConfig
from flux.sim.testing import create_device_config, create_tag_config


class SimFieldBridgeTests(TestCase):
    def setUp(self):
        FieldEndpoint.objects.all().delete()

    def test_materialize_enabled_sim_device_creates_one_runtime_device_with_tags(self):
        sim_device = self.create_sim_device()
        create_tag_config(device=sim_device, source_path="Area/RTU_01/PV", name="PV", data_type="Float4", enabled=True)
        create_tag_config(device=sim_device, source_path="Area/RTU_01/Running", name="Running", data_type="Boolean", enabled=True)

        result = materialize_enabled_sim_devices(provider_name="Tag_02")

        self.assertEqual(result.device_count, 1)
        self.assertEqual(result.tag_count, 2)
        endpoint = FieldEndpoint.objects.get(name=DEFAULT_SIM_SERVER_NAME)
        runtime_device = DeviceConfig.objects.get(endpoint=endpoint, base_device__name="RTU_01")
        self.assertEqual(DeviceConfig.objects.filter(endpoint=endpoint).count(), 1)
        self.assertEqual(runtime_device.device_type, "OPC UA")
        self.assertEqual(runtime_device.browse_path, "Tag_02")
        self.assertEqual(runtime_device.config["mode"], DeviceConfig.Mode.STANDARD)
        self.assertNotIn("response_delay_ms", runtime_device.config)
        self.assertEqual(
            list(
                runtime_device.tags.filter(materialized=True).order_by("tag_name").values_list(
                    "tag_name", "base_tag__data_type", "base_tag__description"
                )
            ),
            [
                ("PV", Tag.DataType.FLOAT, "Area/RTU_01/PV"),
                ("Running", Tag.DataType.BOOL, "Area/RTU_01/Running"),
            ],
        )
        base_device = Device.objects.get(namespace="provider:Tag_02", name="RTU_01")
        device_config = DeviceConfig.objects.get(base_device=base_device, endpoint=endpoint)
        self.assertEqual(Tag.objects.filter(provider="Tag_02", tagpath="Area/RTU_01/PV").count(), 1)
        self.assertEqual(TagConfig.objects.filter(sim_device=device_config, materialized=True, enabled=True).count(), 2)
        self.assertEqual([device["name"] for device in endpoint_config(endpoint)["devices"]], ["RTU_01"])

    def test_materialize_enabled_sim_device_is_idempotent(self):
        sim_device = self.create_sim_device()
        create_tag_config(device=sim_device, source_path="Area/RTU_01/PV", name="PV", data_type="Float4", enabled=True)

        materialize_enabled_sim_devices(provider_name="Tag_02")
        materialize_enabled_sim_devices(provider_name="Tag_02")

        endpoint = FieldEndpoint.objects.get(name=DEFAULT_SIM_SERVER_NAME)
        self.assertEqual(FieldEndpoint.objects.count(), 1)
        self.assertEqual(DeviceConfig.objects.filter(endpoint=endpoint).count(), 1)
        self.assertEqual(TagConfig.objects.filter(sim_device__endpoint=endpoint, materialized=True).count(), 1)

    def test_materialize_enabled_sim_device_does_not_disable_rehydration_backing_tags(self):
        sim_device = self.create_sim_device(name="RTU_01")
        create_tag_config(device=sim_device, source_path="Area/RTU_01/_Time_Sync", name="_Time_Sync", data_type="Int2", enabled=True)
        create_tag_config(
            device=sim_device,
            source_path="Area/RTU_01/TimeSync",
            name="TimeSync",
            data_type=Tag.DataType.INT,
            enabled=True,
            materialized=True,
            config={"expected_node_id": "ns=2;s=RTU_01.TimeSync", "rehydrated_source_path": "Area/RTU_01/_Time_Sync"},
        )

        materialize_enabled_sim_devices(provider_name="Tag_02")

        self.assertTrue(TagConfig.objects.get(sim_device=sim_device, tag_name="TimeSync").materialized)
        self.assertTrue(TagConfig.objects.get(sim_device=sim_device, tag_name="_Time_Sync").materialized)

    def test_materialize_multiple_sim_devices_under_one_runtime_server(self):
        first = self.create_sim_device(name="RTU_01")
        second = self.create_sim_device(name="RTU_02")
        for sim_device in [first, second]:
            create_tag_config(
                device=sim_device,
                source_path="Area/%s/PV" % sim_device.name,
                name="PV",
                data_type="Float4",
                enabled=True,
            )

        result = materialize_enabled_sim_devices(provider_name="Tag_02")

        self.assertEqual(result.endpoint_count, 1)
        self.assertEqual(result.device_count, 2)
        endpoint = FieldEndpoint.objects.get(name=DEFAULT_SIM_SERVER_NAME)
        self.assertEqual(
            list(DeviceConfig.objects.filter(endpoint=endpoint).order_by("base_device__name").values_list("base_device__name", flat=True)),
            ["RTU_01", "RTU_02"],
        )
        self.assertEqual([device["name"] for device in endpoint_config(endpoint)["devices"]], ["RTU_01", "RTU_02"])

    def test_materialize_different_providers_under_default_runtime_server(self):
        first = self.create_sim_device(provider_name="Tag_02", name="RTU_01")
        second = self.create_sim_device(provider_name="Tag_05", name="PLC_01")
        for sim_device in [first, second]:
            create_tag_config(
                device=sim_device,
                source_path="Area/%s/PV" % sim_device.name,
                name="PV",
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
        create_tag_config(device=sim_device, source_path="Remote/PLC/PV", name="PV", data_type="Float4", enabled=True)

        result = materialize_enabled_sim_devices(provider_name="Partner")

        self.assertEqual(result.endpoint_count, 1)
        self.assertEqual(FieldEndpoint.objects.get().name, "Flux sim Partner Server")

    def test_standard_mode_exports_mode_without_delay_metadata(self):
        sim_device = self.create_sim_device(response_delay_ms=250)
        create_tag_config(device=sim_device, source_path="Area/RTU_01/PV", name="PV", data_type="Float4", enabled=True)

        materialize_enabled_sim_devices(provider_name="Tag_02")

        runtime_device = DeviceConfig.objects.get(base_device__name="RTU_01", endpoint__name=DEFAULT_SIM_SERVER_NAME)
        config = single_device_endpoint_config(runtime_device)
        device_config = config["devices"][0]
        self.assertEqual(device_config["mode"], DeviceConfig.Mode.STANDARD)
        self.assertNotIn("response_delay_ms", device_config)
        self.assertEqual(device_config["metadata"]["mode"], DeviceConfig.Mode.STANDARD)
        self.assertNotIn("response_delay_ms", device_config["metadata"])

    def test_slow_network_mode_exports_deterministic_delay_metadata(self):
        sim_device = self.create_sim_device(
            mode=DeviceConfig.Mode.SLOW_NETWORK,
            response_delay_ms=750,
        )
        create_tag_config(device=sim_device, source_path="Area/RTU_01/PV", name="PV", data_type="Float4", enabled=True)

        materialize_enabled_sim_devices(provider_name="Tag_02")

        runtime_device = DeviceConfig.objects.get(base_device__name="RTU_01", endpoint__name=DEFAULT_SIM_SERVER_NAME)
        config = single_device_endpoint_config(runtime_device)
        device_config = config["devices"][0]
        self.assertEqual(runtime_device.config["mode"], DeviceConfig.Mode.SLOW_NETWORK)
        self.assertEqual(runtime_device.config["response_delay_ms"], 750)
        self.assertEqual(device_config["mode"], DeviceConfig.Mode.SLOW_NETWORK)
        self.assertEqual(device_config["response_delay_ms"], 750)
        self.assertEqual(device_config["metadata"]["source"], "sim_device_config")
        self.assertEqual(device_config["metadata"]["sim_device_config_id"], sim_device.id)
        self.assertEqual(TagConfig.objects.get(sim_device=runtime_device, materialized=True).name, "PV")

    def test_tag_behavior_metadata_survives_materialize_and_config_export(self):
        sim_device = self.create_sim_device()
        sim_tag = create_tag_config(
            device=sim_device,
            source_path="Area/RTU_01/Command",
            name="Command",
            data_type="Int4",
            behavior=TagConfig.Behavior.WRITE_TO_OTHER_TAG_RESPONSE,
            mode_config={"response_tag_path": "[default]Area/RTU_01/Response", "response_value": 10},
            enabled=True,
        )

        materialize_enabled_sim_devices(provider_name="Tag_02")

        sim_tag.refresh_from_db()
        self.assertEqual(sim_tag.behavior, TagConfig.Behavior.WRITE_TO_OTHER_TAG_RESPONSE)
        self.assertEqual(sim_tag.mode_config["response_value"], 10)
        self.assertEqual(sim_tag.config["source"], "sim_tag_config")
        self.assertEqual(sim_tag.config["sim_tag_config_id"], sim_tag.id)
        self.assertEqual(sim_tag.config["source_path"], "Area/RTU_01/Command")
        self.assertEqual(sim_tag.config["behavior"], TagConfig.Behavior.WRITE_TO_OTHER_TAG_RESPONSE)
        self.assertEqual(sim_tag.config["mode_config"]["response_value"], 10)

        runtime_device = DeviceConfig.objects.get(base_device__name="RTU_01", endpoint__name=DEFAULT_SIM_SERVER_NAME)
        tag_config = single_device_endpoint_config(runtime_device)["devices"][0]["tags"][0]
        self.assertEqual(tag_config["behavior"], TagConfig.Behavior.WRITE_TO_OTHER_TAG_RESPONSE)
        self.assertEqual(tag_config["mode_config"]["response_value"], 10)
        self.assertEqual(tag_config["metadata"]["sim_tag_config_id"], sim_tag.id)

    def test_materialize_command_runs_bridge(self):
        sim_device = self.create_sim_device()
        create_tag_config(device=sim_device, source_path="Area/RTU_01/PV", name="PV", data_type="Float4", enabled=True)

        call_command("materialize_sim_field_config", "--provider", "Tag_02")

        endpoint = FieldEndpoint.objects.get(name=DEFAULT_SIM_SERVER_NAME)
        self.assertEqual(DeviceConfig.objects.filter(endpoint=endpoint).count(), 1)
        self.assertEqual(TagConfig.objects.filter(sim_device__endpoint=endpoint, materialized=True).count(), 1)

    def create_sim_device(self, *, provider_name="Tag_02", name="RTU_01", mode=DeviceConfig.Mode.STANDARD, response_delay_ms=0, sim_server=None):
        provider, _created = TagProvider.objects.get_or_create(name=provider_name, defaults={"sim_server": sim_server})
        if sim_server is not None and provider.sim_server_id != sim_server.id:
            provider.sim_server = sim_server
            provider.save(update_fields=["sim_server"])
        driver, _created = SimDriver.objects.get_or_create(key="opc_ua", defaults={"label": "OPC UA", "strategy_key": "acm"})
        return create_device_config(
            provider=provider,
            name=name,
            device_type=driver.label,
            driver=driver,
            sim_server=sim_server or provider.sim_server,
            mode=mode,
            response_delay_ms=response_delay_ms,
            enabled=True,
        )
