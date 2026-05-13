from django.test import TestCase
from django.utils import timezone

from .models import LatestTagValue, RuntimeSchedulerConfig, RuntimeTag, TagSchedule
from .scheduler import assign_balancer_codes


class LatestTagValueTests(TestCase):
    def test_value_is_stale_after_threshold(self):
        schedule = TagSchedule.objects.create(name="default", interval_seconds=30)
        tag = RuntimeTag.objects.create(
            provider="default",
            path="Devices/Well_001/Pressure",
            display_name="Casing Pressure",
            asset_name="Well 001",
            schedule=schedule,
        )
        value = LatestTagValue.objects.create(
            tag=tag,
            value=123.4,
            value_timestamp=timezone.now(),
            read_at=timezone.now() - timezone.timedelta(seconds=121),
        )

        self.assertTrue(value.is_stale(stale_after_seconds=120))


class RuntimeSchedulerConfigTests(TestCase):
    def test_balancer_code_advances_with_configured_increment(self):
        config = RuntimeSchedulerConfig.objects.create(
            name="test",
            cold_bucket_count=60,
            current_balancer_code=59,
            balancer_increment=3,
        )

        self.assertEqual(config.advance_balancer_code(save=False), 2)

    def test_balancer_code_assignment_uses_configured_bucket_count(self):
        schedule = TagSchedule.objects.create(name="default", interval_seconds=30)
        config = RuntimeSchedulerConfig.objects.create(name="test", cold_bucket_count=3)
        tags = [
            RuntimeTag.objects.create(
                provider="default",
                path=f"Devices/Tag_{index}",
                display_name=f"Tag {index}",
                schedule=schedule,
            )
            for index in range(5)
        ]

        assign_balancer_codes(tags, config=config)

        self.assertEqual([tag.balancer_code for tag in tags], [1, 2, 3, 1, 2])
