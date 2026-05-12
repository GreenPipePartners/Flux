from django.test import TestCase
from django.utils import timezone

from .models import LatestTagValue, RuntimeTag, TagSchedule


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
