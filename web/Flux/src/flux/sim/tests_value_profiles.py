import json

from django.test import TestCase
from flux_sim.value_profile import PRODUCTION_PROFILE_CONFIG_KEY, ValueProfile

from flux.base.models import Tag
from flux.sim.fluxolot_fishtank import FLUXOLOT_TAGS, ensure_fluxolot_fishtank
from flux.sim.value_profiles import (
    PROFILE_X_UNIT,
    build_production_profile_map,
    persist_field_tag_production_profile,
)


class SimValueProfileTests(TestCase):
    def test_build_production_profile_map_from_fluxolot_history(self):
        result = ensure_fluxolot_fishtank(history_days=2, history_interval_minutes=360)

        profile_map = build_production_profile_map(result.runtime_tags)

        numeric_tag_count = sum(1 for spec in FLUXOLOT_TAGS if spec.data_type not in (Tag.DataType.STRING, Tag.DataType.BOOL)) * 2
        self.assertEqual(len(profile_map), numeric_tag_count)
        self.assertNotIn("[default]FluxolotFishtank/Sir-Fluxolot-Fishtank_PUMP_START_STOP_COMMAND", profile_map)

        temperature_profile = profile_map["[default]FluxolotFishtank/Sir-Fluxolot-Fishtank_TANK_TEMPERATURE"]
        self.assertIn(temperature_profile["kind"], {"polynomial2", "sine"})
        self.assertEqual(temperature_profile["source"], "fit")
        self.assertEqual(temperature_profile["sample_count"], 9)
        self.assertEqual(temperature_profile["x_unit"], PROFILE_X_UNIT)
        self.assertEqual(temperature_profile["runtime_tag"]["display_name"], "Sir Fluxolot Temperature")
        json.dumps(profile_map)

    def test_persist_field_tag_production_profile_keeps_config_value_profile_compatible(self):
        result = ensure_fluxolot_fishtank(history_days=1, history_interval_minutes=720)
        field_tag = next(tag for tag in result.field_tags if tag.name == "TANK_TEMPERATURE" and tag.device.name == "Sir-Fluxolot-Fishtank")
        runtime_tag = next(tag for tag in result.runtime_tags if tag.path.endswith("Sir-Fluxolot-Fishtank_TANK_TEMPERATURE"))

        metadata = persist_field_tag_production_profile(field_tag, runtime_tag)

        self.assertIsNotNone(metadata)
        field_tag.refresh_from_db()
        self.assertIn(PRODUCTION_PROFILE_CONFIG_KEY, field_tag.config)
        self.assertEqual(field_tag.config[PRODUCTION_PROFILE_CONFIG_KEY]["x_unit"], PROFILE_X_UNIT)
        self.assertEqual(
            field_tag.config[PRODUCTION_PROFILE_CONFIG_KEY]["runtime_tag"]["full_path"],
            "[default]FluxolotFishtank/Sir-Fluxolot-Fishtank_TANK_TEMPERATURE",
        )
        self.assertIsNotNone(ValueProfile.from_metadata(field_tag.config))
        json.dumps(field_tag.config)
