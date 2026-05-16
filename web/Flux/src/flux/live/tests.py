from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from flux.base.runtime import DailyTagExtreme, LatestTagValue, RuntimeTag, TagSample, TagSchedule

from .selectors import pad_overview_cards


class LiveSmokeTests(TestCase):
    def test_live_index_loads(self):
        response = self.client.get("/live/")
        self.assertEqual(response.status_code, 200)

    def test_pad_overview_loads(self):
        response = self.client.get("/live/pad-overview/")

        self.assertEqual(response.status_code, 200)

    def test_pad_overview_cards_partial_loads(self):
        response = self.client.get("/live/pad-overview/cards/")

        self.assertEqual(response.status_code, 200)

    def test_pad_overview_panel_filters_by_equipment_tab(self):
        response = self.client.get("/live/pad-overview/panel/?equipment=tank")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "equipment=tank")
        self.assertContains(response, 'aria-selected="true"')

    def test_pad_overview_groups_demo_runtime_tags_into_cards(self):
        schedule = TagSchedule.objects.create(name="demo", interval_seconds=1)
        now = timezone.now()
        tag = RuntimeTag.objects.create(
            provider="default",
            path="FluxLiveDemo/DemoWell_01_TUBING_PRESSURE",
            display_name="Tubing Pressure",
            asset_name="Well: DemoWell_01",
            engineering_units="psi",
            schedule=schedule,
        )
        LatestTagValue.objects.create(
            tag=tag,
            value=525.0,
            quality_code="Good",
            value_timestamp=now,
            read_at=now,
        )
        TagSample.objects.create(
            tag=tag,
            value=525.1239,
            quality_code="Good",
            value_timestamp=now,
            read_at=now,
        )
        DailyTagExtreme.objects.create(
            tag=tag,
            date=timezone.localdate(now) - timedelta(days=1),
            min_value=500.1239,
            max_value=600.9876,
            sample_count=10,
        )

        cards = pad_overview_cards(now=now)

        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0].equipment_type, "Well")
        self.assertEqual(cards[0].points[0].label, "Tubing Pressure")
        self.assertEqual(cards[0].points[0].value, 525.0)
        self.assertEqual(cards[0].points[0].display_value, "525.000")
        self.assertEqual(cards[0].points[0].next_read_seconds, 1)
        self.assertEqual(cards[0].points[0].history[0].label, "24h")
        self.assertEqual(cards[0].points[0].history[0].max_value, "525.123")
        self.assertEqual(cards[0].points[0].history[0].marker_percent, 50)
        self.assertEqual(cards[0].points[0].history[1].label, "7d")
        self.assertEqual(cards[0].points[0].history[1].min_value, "500.123")
        self.assertEqual(cards[0].points[0].history[1].marker_percent, 25)
