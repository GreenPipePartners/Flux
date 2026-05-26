from django.test import TestCase

from flux.base.runtime import RuntimeTag
from flux.sim.models import DeviceConfig
from flux.sim.field_demo import ensure_demo_field_config
from flux.sim.demo import ensure_demo_runtime_config


class SimDemoConfigTests(TestCase):
    def test_demo_sim_config_creates_well_meter_and_tank(self):
        endpoint, tags = ensure_demo_field_config()

        self.assertEqual(endpoint.name, "local-sim")
        self.assertEqual(endpoint.sim_device_configs.count(), 6)
        self.assertEqual(len(tags), 20)
        self.assertEqual(
            sorted(DeviceConfig.objects.filter(endpoint=endpoint).values_list("base_device__device_type", flat=True)),
            ["Meter", "Meter", "Tank", "Tank", "Well", "Well"],
        )

    def test_demo_runtime_config_maps_field_tags_to_runtime_tags(self):
        runtime_tags = ensure_demo_runtime_config()

        self.assertEqual(len(runtime_tags), 20)
        self.assertTrue(RuntimeTag.objects.filter(asset_name="Well: DemoWell_01").exists())
        self.assertTrue(RuntimeTag.objects.filter(path="FluxLiveDemo/DemoTank_01_LEVEL").exists())
