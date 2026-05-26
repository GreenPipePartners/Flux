from types import SimpleNamespace

from django.test import TestCase

from flux.sim.models import SimDriver, TagProvider
from flux.sim.export_compare import (
    compare_ignition_tag_configs,
    configure_export_compare_field_device_ignition,
    normalize_ignition_tag_configs,
)
from flux.sim.field_bridge import materialize_enabled_sim_devices
from flux.sim.models import DeviceConfig
from flux.sim.testing import create_device_config, create_tag_config


class SimExportCompareTests(TestCase):
    def test_materialized_sim_device_configures_exports_and_compares_with_mock_fluxy(self):
        sim_device = self.create_sim_device()
        create_tag_config(
            device=sim_device,
            source_path="Area/RTU_01/PV",
            name="PV",
            data_type="Float4",
            value_source="opc",
            opc_server="Original OPC",
            opc_item_path="ns=2;s=RTU_01.40001F",
            enabled=True,
        )
        create_tag_config(
            device=sim_device,
            source_path="Area/RTU_01/Running",
            name="Running",
            data_type="Boolean",
            value_source="opc",
            opc_server="Original OPC",
            opc_item_path="ns=2;s=RTU_01.00001B",
            enabled=True,
        )
        materialize_enabled_sim_devices(provider_name="Tag_02")
        field_device = DeviceConfig.objects.get(base_device__name="RTU_01", endpoint__isnull=False)
        fx = FakeFluxy()

        result = configure_export_compare_field_device_ignition(
            fx,
            field_device,
            tag_provider="testing",
            tag_folder="FluxSimCompare",
            connection_name="Flux Field Test OPC",
        )

        self.assertTrue(result.matches, result.differences)
        self.assertEqual(result.configuration.tag_count, 2)
        self.assertEqual(fx.tag.export_calls, [("[testing]FluxSimCompare", True)])
        self.assertEqual(fx.tag.configured[0]["base_path"], "[testing]")
        self.assertEqual(
            [tag["path"] for tag in result.source_tags],
            ["FluxSimCompare/RTU_01_PV", "FluxSimCompare/RTU_01_Running"],
        )
        self.assertEqual(result.source_tags, result.exported_tags)

    def test_compare_reports_important_field_mismatch(self):
        source = normalize_ignition_tag_configs(
            {
                "name": "Folder",
                "tagType": "Folder",
                "tags": [
                    {
                        "name": "PV",
                        "tagType": "AtomicTag",
                        "valueSource": "opc",
                        "dataType": "Float8",
                        "opcServer": "Flux Field A",
                        "opcItemPath": "ns=2;s=RTU_01.PV",
                    }
                ],
            }
        )
        exported = normalize_ignition_tag_configs(
            {
                "name": "Folder",
                "tagType": "Folder",
                "tags": [
                    {
                        "name": "PV",
                        "tagType": "AtomicTag",
                        "valueSource": "opc",
                        "dataType": "Int4",
                        "opcServer": "Flux Field A",
                        "opcItemPath": "ns=2;s=RTU_01.PV",
                    }
                ],
            }
        )

        self.assertEqual(
            compare_ignition_tag_configs(source, exported),
            ["Folder/PV dataType mismatch: source='Float8' exported='Int4'"],
        )

    def create_sim_device(self):
        provider = TagProvider.objects.create(name="Tag_02")
        driver = SimDriver.objects.create(key="opc_ua", label="OPC UA", strategy_key="acm")
        return create_device_config(
            provider=provider,
            name="RTU_01",
            device_type=driver.label,
            driver=driver,
            enabled=True,
        )


class FakeFluxy:
    def __init__(self):
        self.tag = FakeTagApi()
        self.opcua = FakeOpcUaApi()


class FakeTagApi:
    def __init__(self):
        self.configured = []
        self.deleted = []
        self.export_calls = []

    def configure(self, tags, base_path=None, collision_policy="o"):
        self.configured.append(
            {"tags": tags, "base_path": base_path, "collision_policy": collision_policy}
        )
        return []

    def export_tags(self, tag_path, recursive=True):
        self.export_calls.append((tag_path, recursive))
        return SimpleNamespace(tags=self.configured[-1]["tags"][0])

    def delete_tags(self, tag_path):
        self.deleted.append(tag_path)
        return []


class FakeOpcUaApi:
    def __init__(self):
        self.added = []
        self.removed = []

    def add_connection(self, name, description, discovery_url, endpoint_url, **kwargs):
        self.added.append(
            {
                "name": name,
                "description": description,
                "discovery_url": discovery_url,
                "endpoint_url": endpoint_url,
                "kwargs": kwargs,
            }
        )
        return True

    def remove_connection(self, name):
        self.removed.append(name)
        return True
