from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from .engine import configure_enabled_tags, run_history_backfill, value_for_tag, write_due_tags
from .models import SimHistoryBackfill, SimSchedule, SimTag


class SimModelTests(TestCase):
    def test_sim_index_loads(self):
        response = self.client.get("/sim/")

        self.assertEqual(response.status_code, 200)

    def test_seeded_schedules_exist(self):
        self.assertTrue(SimSchedule.objects.filter(interval_seconds=1).exists())
        self.assertTrue(SimSchedule.objects.filter(interval_seconds=5).exists())
        self.assertTrue(SimSchedule.objects.filter(interval_seconds=10).exists())

    def test_value_generation_for_bool_integer_and_float(self):
        SimTag.objects.update(enabled=False)
        fast = SimSchedule.objects.create(name="fast", interval_seconds=1)
        bool_tag = SimTag.objects.create(
            name="BoolTag",
            folder_path="ValueTest",
            data_type=SimTag.DataType.BOOLEAN,
            pattern=SimTag.Pattern.BOOL_TOGGLE,
            period_samples=2,
            schedule=fast,
        )
        int_tag = SimTag.objects.create(
            name="IntegerTag",
            folder_path="ValueTest",
            data_type=SimTag.DataType.INT4,
            pattern=SimTag.Pattern.INT_RAMP,
            baseline=10,
            step=2,
            schedule=fast,
        )
        float_tag = SimTag.objects.create(
            name="FloatTag",
            folder_path="ValueTest",
            data_type=SimTag.DataType.FLOAT8,
            pattern=SimTag.Pattern.FLOAT_WAVE,
            baseline=50,
            amplitude=10,
            period_samples=4,
            schedule=fast,
        )

        self.assertEqual([value_for_tag(bool_tag, index) for index in range(4)], [False, False, True, True])
        self.assertEqual(value_for_tag(int_tag, 3), 16)
        self.assertAlmostEqual(value_for_tag(float_tag, 1), 60.0)

    def test_write_due_tags_uses_schedules_and_advances_next_write(self):
        SimTag.objects.update(enabled=False)
        fx = FakeFluxy()
        fast = SimSchedule.objects.create(name="fast", interval_seconds=1)
        now = timezone.now()
        tag = SimTag.objects.create(
            name="IntegerTag",
            folder_path="WriteTest",
            data_type=SimTag.DataType.INT4,
            pattern=SimTag.Pattern.INT_RAMP,
            schedule=fast,
            next_write_at=now,
        )

        written = write_due_tags(fx, now=now)
        tag.refresh_from_db()

        self.assertEqual(written, 1)
        self.assertEqual(fx.tag.writes[0]["tag_paths"], ["[default]WriteTest/IntegerTag"])
        self.assertEqual(fx.tag.writes[0]["values"], [0])
        self.assertEqual(tag.sample_index, 1)
        self.assertEqual(tag.last_value, 0)
        self.assertEqual(tag.next_write_at, now + timedelta(seconds=1))

    def test_configure_enabled_tags_groups_by_folder(self):
        SimTag.objects.update(enabled=False)
        fx = FakeFluxy()
        fast = SimSchedule.objects.create(name="fast", interval_seconds=1)
        SimTag.objects.create(
            name="BoolTag",
            folder_path="ConfigTest",
            data_type=SimTag.DataType.BOOLEAN,
            pattern=SimTag.Pattern.BOOL_TOGGLE,
            schedule=fast,
        )

        configure_enabled_tags(fx)

        self.assertEqual(fx.tag.configured[0]["base_path"], "[default]")
        self.assertEqual(fx.tag.configured[0]["tags"][0]["name"], "ConfigTest")

    def test_history_backfill_writes_configured_tags(self):
        SimTag.objects.update(enabled=False)
        fx = FakeFluxy()
        fast = SimSchedule.objects.create(name="fast", interval_seconds=1)
        SimTag.objects.create(
            name="FloatTag",
            folder_path="HistoryTest",
            data_type=SimTag.DataType.FLOAT8,
            pattern=SimTag.Pattern.FLOAT_WAVE,
            schedule=fast,
        )
        backfill = SimHistoryBackfill.objects.create(
            name="one-day",
            history_prefix="histprov:Core Historian:/sys:gateway:/prov:default:/tag:FluxSim",
            start_at=timezone.now(),
            duration_days=1,
            interval_seconds=86_400,
        )

        written = run_history_backfill(fx, backfill)
        backfill.refresh_from_db()

        self.assertEqual(written, 2)
        self.assertEqual(backfill.status, SimHistoryBackfill.Status.COMPLETED)
        self.assertEqual(len(fx.historian.stored), 1)


class FakeFluxy:
    def __init__(self):
        self.tag = FakeTagApi()
        self.historian = FakeHistorianApi()


class FakeTagApi:
    def __init__(self):
        self.writes = []
        self.configured = []

    def write_blocking(self, tag_paths, values):
        self.writes.append({"tag_paths": tag_paths, "values": values})
        return ["Good" for _path in tag_paths]

    def configure(self, tags, *, base_path, collision_policy):
        self.configured.append({"tags": tags, "base_path": base_path, "collision_policy": collision_policy})
        return ["Good"]


class FakeHistorianApi:
    def __init__(self):
        self.stored = []

    def store_data_points(self, paths, values, *, timestamps, qualities):
        self.stored.append({"paths": paths, "values": values, "timestamps": timestamps, "qualities": qualities})
        return ["Good" for _path in paths]
