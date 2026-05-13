from django.test import TestCase

from flux.field.demo import ensure_demo_field_config
from flux.opt.demo import ensure_demo_runtime_config
from runtime.models import RuntimeTag


class FieldDemoConfigTests(TestCase):
    def test_demo_field_config_creates_well_meter_and_tank(self):
        endpoint, tags = ensure_demo_field_config()

        self.assertEqual(endpoint.name, "local-field")
        self.assertEqual(endpoint.devices.count(), 3)
        self.assertEqual(len(tags), 10)
        self.assertEqual(
            sorted(endpoint.devices.values_list("device_type", flat=True)),
            ["Meter", "Tank", "Well"],
        )

    def test_demo_runtime_config_maps_field_tags_to_runtime_tags(self):
        runtime_tags = ensure_demo_runtime_config()

        self.assertEqual(len(runtime_tags), 10)
        self.assertTrue(RuntimeTag.objects.filter(asset_name="Well: DemoWell_01").exists())
        self.assertTrue(RuntimeTag.objects.filter(path="FluxLiveDemo/DemoTank_01_LEVEL").exists())
