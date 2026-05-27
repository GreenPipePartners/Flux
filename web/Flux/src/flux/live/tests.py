from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from flux.base.runtime import DailyTagExtreme, LatestTagValue, RuntimeTag, TagSample, TagSchedule
from flux.opt.models import OptimizationLease, RuntimeDemand
from flux.opt.services import active_demand_full_paths
from flux.plane.models import Latest
from flux.plane.questdb_samples import QuestDBWindowStat
from flux.plane.services import ensure_series_for_full_path
from flux.sim.fluxolot_fishtank import ensure_fluxolot_fishtank, ensure_fluxolot_live_scope

from .models import LiveCardDefinition, LiveCardPointDefinition, LiveScope
from flux.spot.copy_context import render_card_copy_markdown, render_card_table_markdown
from flux.spot.selectors import pad_overview_cards, scope_cards
from flux.spot.views import refresh_timer


class LiveSmokeTests(TestCase):
    def test_live_index_loads(self):
        response = self.client.get("/spot/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-flux-web-pulse")
        self.assertContains(response, "Next display refresh")
        self.assertContains(response, "flux-web-pulse-timer")

    def test_live_url_redirects_to_spot_index(self):
        response = self.client.get("/live/", {"card": "live-paths", "mode": "detail"})

        self.assertRedirects(
            response,
            "/spot/?card=live-paths&mode=detail",
            status_code=301,
            fetch_redirect_response=False,
        )

    def test_live_index_lists_current_paths(self):
        scope = LiveScope.objects.create(slug="pad-a", name="Pad A", description="North pad")
        card = LiveCardDefinition.objects.create(scope=scope, title="Well 01", group="Well", kind="Well")
        LiveCardPointDefinition.objects.create(card=card, label="Pressure", full_path="[default]well/pressure")

        response = self.client.get(reverse("spot:index"), {"card": "live-paths", "mode": "detail"})

        self.assertContains(response, "Flux.spot")
        self.assertContains(response, "Platform")
        self.assertContains(response, 'class="feature-hero"')
        self.assertContains(response, 'id="spot-comp-surface"')
        self.assertContains(response, 'data-comp-mode="detail"')
        self.assertContains(response, 'id="live-paths-comp-focus"')
        self.assertContains(response, "comp-card-anchor")
        self.assertContains(response, "Available Flux.spot Paths")
        self.assertContains(response, reverse("spot:index"))
        self.assertContains(response, reverse("spot:pad_overview"))
        self.assertContains(response, reverse("spot:scope_detail", args=[scope.slug]))
        self.assertContains(response, "Pad A")
        self.assertContains(response, "1 cards / 1 points")

    def test_live_index_defaults_to_summary_comp_surface(self):
        response = self.client.get(reverse("spot:index"))

        self.assertContains(response, 'id="spot-comp-surface"')
        self.assertContains(response, 'data-comp-mode="summary"')
        self.assertContains(response, 'id="live-platform-comp-card"')
        self.assertContains(response, 'id="live-paths-comp-card"')
        self.assertContains(response, 'id="live-table-comp-card"')
        self.assertNotContains(response, 'id="spot-comp-focus-region"')
        self.assertContains(response, "↘")

    def test_live_index_table_hides_trace_and_unlisted_runtime_tags(self):
        schedule = TagSchedule.objects.create(name="demo", interval_seconds=1)
        live_tag = RuntimeTag.objects.create(
            provider="default",
            path="LiveScope/Pressure",
            display_name="Connected Live Pressure",
            schedule=schedule,
        )
        RuntimeTag.objects.create(
            provider="default",
            path="FluxLiveDemo/DemoWell_01_TUBING_PRESSURE",
            display_name="Pad Demo Tubing Pressure",
            schedule=schedule,
        )
        RuntimeTag.objects.create(
            provider="default",
            path="FluxTraceStress/1/PressureA",
            display_name="Trace Backing Pressure",
            category=RuntimeTag.Category.TRACE_STRESS,
            schedule=schedule,
        )
        RuntimeTag.objects.create(
            provider="default",
            path="DeadFixture/OldTag",
            display_name="Unlisted Old Tag",
            category=RuntimeTag.Category.SIMULATION,
            schedule=schedule,
        )
        scope = LiveScope.objects.create(slug="pad-a", name="Pad A")
        card = LiveCardDefinition.objects.create(scope=scope, title="Well 01", group="Well", kind="Well")
        LiveCardPointDefinition.objects.create(card=card, label="Pressure", full_path=live_tag.full_path)

        response = self.client.get(reverse("spot:index"), {"card": "live-table", "mode": "detail"})

        self.assertContains(response, 'id="live-table-comp-focus"')
        self.assertContains(response, 'hx-push-url="true"')
        self.assertContains(response, "Connected Live Pressure")
        self.assertContains(response, "Pad Demo Tubing Pressure")
        self.assertNotContains(response, "Trace Backing Pressure")
        self.assertNotContains(response, "Unlisted Old Tag")
        self.assertContains(response, "Hidden from this current-state table: 1 trace backing tags")
        self.assertContains(response, "unlisted runtime tags")

    def test_live_table_uses_ten_row_server_side_htmx_pagination(self):
        schedule = TagSchedule.objects.create(name="demo", interval_seconds=1)
        for index in range(12):
            RuntimeTag.objects.create(
                provider="default",
                path=f"FluxLiveDemo/DemoTag_{index:02d}",
                display_name=f"Demo Tag {index:02d}",
                schedule=schedule,
            )

        first_page = self.client.get(reverse("spot:index"), {"card": "live-table", "mode": "detail"})
        second_page = self.client.get(
            reverse("spot:index"),
            {"card": "live-table", "mode": "detail", "live_table_page": "2"},
        )

        self.assertContains(first_page, "Showing 1-10 of 12 tags")
        self.assertContains(first_page, 'hx-target="#spot-comp-surface"')
        self.assertContains(first_page, 'hx-push-url="true"')
        self.assertContains(first_page, "live_table_page=2")
        self.assertContains(first_page, "Demo Tag 09")
        self.assertNotContains(first_page, "Demo Tag 10")
        self.assertContains(second_page, "Showing 11-12 of 12 tags")
        self.assertContains(second_page, "live_table_page=1")
        self.assertContains(second_page, "Demo Tag 10")
        self.assertNotContains(second_page, "Demo Tag 09")

    def test_live_index_treats_bad_notfound_as_error_not_online(self):
        schedule = TagSchedule.objects.create(name="demo", interval_seconds=1)
        now = timezone.now()
        tag = RuntimeTag.objects.create(
            provider="default",
            path="FluxLiveDemo/DemoWell_01_TUBING_PRESSURE",
            display_name="Tubing Pressure",
            asset_name="Well: DemoWell_01",
            schedule=schedule,
        )
        LatestTagValue.objects.create(
            tag=tag,
            value=None,
            quality_code="Bad_NotFound",
            value_timestamp=now,
            read_at=now,
        )

        response = self.client.get("/spot/", {"card": "live-table", "mode": "detail"})

        self.assertEqual(response.context["online_count"], 0)
        self.assertEqual(response.context["stale_count"], 1)
        self.assertEqual(response.context["bad_quality_count"], 1)
        self.assertContains(response, "Bad_NotFound")
        self.assertContains(response, "status-failed")

    def test_pad_overview_loads(self):
        response = self.client.get("/spot/pad-overview/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Next display refresh")
        self.assertContains(response, "flux-web-pulse-timer")
        self.assertContains(response, 'hx-trigger="every 5s [fluxDisplayPulseCanRun()]"')
        self.assertContains(response, 'hx-push-url="true"')
        self.assertNotContains(response, "live-refresh-timer")

    def test_live_pad_overview_redirects_to_spot(self):
        response = self.client.get("/live/pad-overview/", {"equipment": "tank"})

        self.assertRedirects(
            response,
            "/spot/pad-overview/?equipment=tank",
            status_code=301,
            fetch_redirect_response=False,
        )

    def test_pad_overview_cards_partial_loads(self):
        response = self.client.get("/spot/pad-overview/cards/")

        self.assertEqual(response.status_code, 200)

    def test_pad_overview_panel_filters_by_equipment_tab(self):
        response = self.client.get("/spot/pad-overview/panel/?equipment=tank")

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
        self.assertEqual(cards[0].kind, "Well")
        self.assertEqual(cards[0].points[0].label, "Tubing Pressure")
        self.assertEqual(cards[0].points[0].value, 525.0)
        self.assertEqual(cards[0].points[0].display_value, "525.000")
        self.assertEqual(cards[0].points[0].next_read_seconds, 1)
        self.assertEqual(cards[0].points[0].next_read_centiseconds, 100)
        self.assertEqual(cards[0].points[0].next_read_label, "100cs")
        self.assertEqual(cards[0].points[0].history[0].label, "24h")
        self.assertEqual(cards[0].points[0].history[0].max_value, "525.123")
        self.assertEqual(cards[0].points[0].history[0].marker_percent, 50)
        self.assertEqual(cards[0].points[0].history[1].label, "7d")
        self.assertEqual(cards[0].points[0].history[1].min_value, "500.123")
        self.assertEqual(cards[0].points[0].history[1].marker_percent, 25)

    def test_pad_overview_marks_bad_notfound_as_stale_error(self):
        schedule = TagSchedule.objects.create(name="demo", interval_seconds=1)
        now = timezone.now()
        tag = RuntimeTag.objects.create(
            provider="default",
            path="FluxLiveDemo/DemoWell_01_TUBING_PRESSURE",
            display_name="Tubing Pressure",
            asset_name="Well: DemoWell_01",
            schedule=schedule,
        )
        LatestTagValue.objects.create(
            tag=tag,
            value=None,
            quality_code="Bad_NotFound",
            value_timestamp=now,
            read_at=now,
        )

        point = pad_overview_cards(now=now)[0].points[0]

        self.assertEqual(point.quality, "Bad_NotFound")
        self.assertTrue(point.stale)
        self.assertTrue(point.error)

    def test_scope_cards_return_live_card_shapes_from_canonical_tag_refs(self):
        schedule = TagSchedule.objects.create(name="demo", interval_seconds=2)
        now = timezone.now()
        tag = RuntimeTag.objects.create(
            provider="default",
            path="Sites/A/Well_01/TubingPressure",
            display_name="Runtime display",
            asset_name="Well: Well_01",
            engineering_units="psi",
            schedule=schedule,
        )
        LatestTagValue.objects.create(
            tag=tag,
            value=412.1239,
            quality_code="Good",
            value_timestamp=now,
            read_at=now,
        )
        scope = LiveScope.objects.create(slug="field", name="Field")
        card = LiveCardDefinition.objects.create(scope=scope, title="Well 01", group="Pad A", kind="Well")
        LiveCardPointDefinition.objects.create(
            card=card,
            label="Tubing Pressure",
            full_path="[default]Sites/A/Well_01/TubingPressure",
        )

        cards = scope_cards("field", now=now)

        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0].title, "Well 01")
        self.assertEqual(cards[0].group, "Pad A")
        self.assertEqual(cards[0].kind, "Well")
        self.assertEqual(cards[0].points[0].label, "Tubing Pressure")
        self.assertEqual(cards[0].points[0].full_path, "[default]Sites/A/Well_01/TubingPressure")
        self.assertEqual(cards[0].points[0].display_value, "412.123")
        self.assertEqual(cards[0].points[0].units, "psi")

    def test_scope_cards_use_questdb_plane_sample_ranges_for_spot_markers(self):
        now = timezone.now()
        series = ensure_series_for_full_path("[default]well/pressure")
        Latest.objects.create(series=series, value=80.0, quality_code="Good", value_timestamp=now, read_at=now)
        scope = LiveScope.objects.create(slug="pad-a", name="Pad A")
        card = LiveCardDefinition.objects.create(scope=scope, title="Well 01", group="Well", kind="Well")
        LiveCardPointDefinition.objects.create(
            card=card,
            label="Pressure",
            full_path="[default]well/pressure",
            series=series,
        )

        with patch(
            "flux.spot.selectors.questdb_window_stats_by_series",
            return_value={
                series.id: {
                    "today": QuestDBWindowStat("today", min_value=20.0, max_value=100.0, sample_count=4),
                    "rolling_7d": QuestDBWindowStat("rolling_7d", min_value=0.0, max_value=100.0, sample_count=7),
                    "rolling_30d": QuestDBWindowStat("rolling_30d", min_value=60.0, max_value=100.0, sample_count=30),
                }
            },
        ) as questdb_stats:
            cards = scope_cards("pad-a", now=now)

        questdb_stats.assert_called_once_with([series.id], now=now)
        history = cards[0].points[0].history
        self.assertEqual([extreme.label for extreme in history], ["24h", "7d", "30d"])
        self.assertEqual(history[0].marker_percent, 75)
        self.assertEqual(history[1].marker_percent, 80)
        self.assertEqual(history[2].marker_percent, 50)

    def test_card_copy_context_has_table_and_llm_export(self):
        schedule = TagSchedule.objects.create(name="demo", interval_seconds=2)
        now = timezone.now()
        tag = RuntimeTag.objects.create(
            provider="default",
            path="Sites/A/Well_01/TubingPressure",
            display_name="Runtime display",
            asset_name="Well: Well_01",
            engineering_units="psi",
            schedule=schedule,
        )
        LatestTagValue.objects.create(tag=tag, value=412.1239, quality_code="Good", value_timestamp=now, read_at=now)
        scope = LiveScope.objects.create(slug="field", name="Field")
        card = LiveCardDefinition.objects.create(scope=scope, title="Well 01", group="Pad A", kind="Well")
        LiveCardPointDefinition.objects.create(
            card=card,
            label="Tubing Pressure",
            full_path="[default]Sites/A/Well_01/TubingPressure",
        )
        live_card = scope_cards("field", now=now)[0]

        table = render_card_table_markdown(live_card)
        llm_export = render_card_copy_markdown(
            live_card,
            scope_slug="field",
            scope_name="Field",
            page_url="http://testserver/spot/field/",
        )

        self.assertIn("| Tubing Pressure | 412.123 | psi | Good | false | [default]Sites/A/Well_01/TubingPressure |", table)
        self.assertIn("docs/spot-card-context.md", llm_export)
        self.assertIn('"type": "flux.spot.card.context"', llm_export)
        self.assertIn('"full_path": "[default]Sites/A/Well_01/TubingPressure"', llm_export)

    def test_live_scope_routes_filter_by_group(self):
        scope = LiveScope.objects.create(slug="pad-a", name="Pad A")
        well = LiveCardDefinition.objects.create(scope=scope, title="Well 01", group="Well", kind="Producer")
        tank = LiveCardDefinition.objects.create(scope=scope, title="Tank 01", group="Tank", kind="Oil Tank")
        LiveCardPointDefinition.objects.create(card=well, label="Pressure", full_path="[default]well/pressure")
        LiveCardPointDefinition.objects.create(card=tank, label="Level", full_path="[default]tank/level")

        response = self.client.get("/spot/pad-a/?group=tank")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tank 01")
        self.assertNotContains(response, "Well 01")
        self.assertContains(response, "group=tank")
        self.assertContains(response, 'hx-get="/spot/pad-a/panel/?group=tank"')
        self.assertNotContains(response, 'hx-get="/spot/pad-a/cards/?group=tank"')

    def test_live_scope_route_redirects_to_spot(self):
        scope = LiveScope.objects.create(slug="pad-a", name="Pad A")
        tank = LiveCardDefinition.objects.create(scope=scope, title="Tank 01", group="Tank", kind="Oil Tank")
        LiveCardPointDefinition.objects.create(card=tank, label="Level", full_path="[default]tank/level")

        response = self.client.get("/live/pad-a/", {"group": "tank"})

        self.assertRedirects(
            response,
            "/spot/pad-a/?group=tank",
            status_code=301,
            fetch_redirect_response=False,
        )

    def test_live_scope_cards_partial_loads(self):
        scope = LiveScope.objects.create(slug="pad-a", name="Pad A")
        card = LiveCardDefinition.objects.create(scope=scope, title="Well 01", group="Pad A", kind="Well")
        LiveCardPointDefinition.objects.create(card=card, label="Pressure", full_path="[default]well/pressure")

        response = self.client.get("/spot/pad-a/cards/?group=pad+a")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Well 01")
        self.assertContains(response, "data-live-card-copy")
        self.assertContains(response, "live-card-copy-corner")
        self.assertContains(response, "data-live-card-copy-table")
        self.assertContains(response, "data-live-card-copy-llm")
        self.assertContains(response, 'id="live-scope-refresh-panel"')
        self.assertNotContains(response, 'hx-swap="outerHTML"')
        self.assertNotContains(response, 'hx-get="/spot/pad-a/cards/?group=pad%20a"')

    def test_live_scope_cards_partial_uses_selected_group_without_polling(self):
        scope = LiveScope.objects.create(slug="pad-a", name="Pad A")
        feeder = LiveCardDefinition.objects.create(scope=scope, title="Feeder 01", group="Feeder", kind="Treat Feeder")
        light = LiveCardDefinition.objects.create(scope=scope, title="UV Light 01", group="Light", kind="UV Light")
        LiveCardPointDefinition.objects.create(card=feeder, label="Level", full_path="[default]feeder/level")
        LiveCardPointDefinition.objects.create(card=light, label="Runtime Remaining", full_path="[default]light/runtime")

        response = self.client.get("/spot/pad-a/cards/", {"group": "light"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="live-scope-refresh-panel"')
        self.assertNotContains(response, 'hx-get="/spot/pad-a/cards/?group=light"')
        self.assertContains(response, "UV Light 01")
        self.assertNotContains(response, "Feeder 01")

    def test_live_scope_panel_partial_updates_active_tab_without_card_polling(self):
        scope = LiveScope.objects.create(slug="pad-a", name="Pad A")
        feeder = LiveCardDefinition.objects.create(scope=scope, title="Feeder 01", group="Feeder", kind="Treat Feeder")
        pump = LiveCardDefinition.objects.create(scope=scope, title="Pump 01", group="Pump", kind="Recirculation Pump")
        LiveCardPointDefinition.objects.create(card=feeder, label="Level", full_path="[default]feeder/level")
        LiveCardPointDefinition.objects.create(card=pump, label="Pressure", full_path="[default]pump/pressure")

        response = self.client.get("/spot/pad-a/panel/", {"group": "pump"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="live-scope-panel"')
        self.assertContains(response, 'hx-push-url="/spot/pad-a/?group=pump"')
        self.assertNotContains(response, 'hx-get="/spot/pad-a/cards/?group=pump"')
        self.assertContains(response, 'aria-selected="true"')
        self.assertContains(response, "Pump 01")
        self.assertNotContains(response, "Feeder 01")

    def test_live_scope_route_leases_scope_runtime_tags_hot(self):
        schedule = TagSchedule.objects.create(name="fast", interval_seconds=10)
        RuntimeTag.objects.create(provider="default", path="well/pressure", display_name="Pressure", schedule=schedule)
        RuntimeTag.objects.create(provider="default", path="well/temperature", display_name="Temperature", schedule=schedule)
        scope = LiveScope.objects.create(slug="pad-a", name="Pad A")
        card = LiveCardDefinition.objects.create(scope=scope, title="Well 01", group="Well", kind="Well")
        LiveCardPointDefinition.objects.create(card=card, label="Pressure", full_path="[default]well/pressure")
        LiveCardPointDefinition.objects.create(card=card, label="Temperature", full_path="[default]well/temperature")

        response = self.client.get("/spot/pad-a/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(active_demand_full_paths(), {"[default]well/pressure", "[default]well/temperature"})
        self.assertEqual(OptimizationLease.objects.count(), 0)
        self.assertEqual(RuntimeDemand.objects.count(), 2)

    def test_fluxolot_live_scope_renders_sir_and_missus_fishtanks(self):
        result = ensure_fluxolot_fishtank(history_days=1, history_interval_minutes=1440)
        ensure_fluxolot_live_scope(result.runtime_tags)

        response = self.client.get("/spot/fluxolot/", {"group": "tank"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sir Fluxolot Fish Tank")
        self.assertContains(response, "Missus Fluxolot Fish Tank")
        self.assertContains(response, "Temperature")
        self.assertContains(response, "degF")
        self.assertContains(response, "O2 Percent")
        self.assertNotContains(response, "Sir Fluxolot Recirculation Pump")
        self.assertContains(response, "flux-web-pulse-timer")
        self.assertContains(response, 'hx-trigger="every 5s [fluxDisplayPulseCanRun()]"')
        self.assertNotContains(response, 'hx-get="/spot/fluxolot/cards/?group=tank"')

    def test_fluxolot_live_cards_partial_leases_tank_tags(self):
        result = ensure_fluxolot_fishtank(history_days=1, history_interval_minutes=1440)
        ensure_fluxolot_live_scope(result.runtime_tags)

        response = self.client.get("/spot/fluxolot/cards/", {"group": "tank"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sir Fluxolot Fish Tank")
        self.assertContains(response, "Missus Fluxolot Fish Tank")
        self.assertNotContains(response, 'hx-get="/spot/fluxolot/cards/?group=tank"')
        self.assertContains(response, "data-live-card-copy")
        demand_paths = active_demand_full_paths()
        self.assertIn("[default]FluxolotFishtank/Sir-Fluxolot-Fishtank_TANK_TEMPERATURE", demand_paths)
        self.assertIn("[default]FluxolotFishtank/Missus-Fluxolot-Fishtank_TANK_TEMPERATURE", demand_paths)
        self.assertNotIn("[default]FluxolotFishtank/Sir-Fluxolot-Fishtank_PUMP_HEAD_PRESSURE", demand_paths)

    def test_live_refresh_timer_counts_down_from_latest_value_read_time(self):
        schedule = TagSchedule.objects.create(name="fast", interval_seconds=10)
        now = timezone.now()
        tag = RuntimeTag.objects.create(
            provider="default",
            path="well/pressure",
            display_name="Pressure",
            engineering_units="psi",
            schedule=schedule,
        )
        LatestTagValue.objects.create(tag=tag, value=10.0, quality_code="Good", value_timestamp=now, read_at=now)
        scope = LiveScope.objects.create(slug="pad-a", name="Pad A")
        card = LiveCardDefinition.objects.create(scope=scope, title="Well 01", group="Well", kind="Well")
        LiveCardPointDefinition.objects.create(card=card, label="Pressure", full_path="[default]well/pressure")

        fresh_cards = scope_cards("pad-a", now=now)
        later_cards = scope_cards("pad-a", now=now + timedelta(seconds=3))

        self.assertEqual(
            refresh_timer(fresh_cards),
            {
                "label": "10s",
                "seconds": 10,
                "centiseconds": 1000,
                "interval_centiseconds": 1000,
                "percent": 100,
                "precision": "second",
            },
        )
        self.assertEqual(
            refresh_timer(later_cards),
            {
                "label": "7s",
                "seconds": 7,
                "centiseconds": 700,
                "interval_centiseconds": 1000,
                "percent": 70,
                "precision": "second",
            },
        )

    def test_live_refresh_timer_computes_centiseconds_without_rendered_card_timer(self):
        schedule = TagSchedule.objects.create(name="fast", interval_seconds=1)
        now = timezone.now()
        tag = RuntimeTag.objects.create(
            provider="default",
            path="well/pressure",
            display_name="Pressure",
            engineering_units="psi",
            schedule=schedule,
        )
        LatestTagValue.objects.create(tag=tag, value=10.0, quality_code="Good", value_timestamp=now, read_at=now)
        scope = LiveScope.objects.create(slug="pad-a", name="Pad A")
        card = LiveCardDefinition.objects.create(scope=scope, title="Well 01", group="Well", kind="Well")
        LiveCardPointDefinition.objects.create(card=card, label="Pressure", full_path="[default]well/pressure")

        fresh_timer = refresh_timer(scope_cards("pad-a", now=now))
        later_timer = refresh_timer(scope_cards("pad-a", now=now + timedelta(milliseconds=370)))
        response = self.client.get("/spot/pad-a/cards/", {"group": "well"})

        self.assertEqual(fresh_timer["label"], "100cs")
        self.assertEqual(fresh_timer["centiseconds"], 100)
        self.assertEqual(fresh_timer["precision"], "centisecond")
        self.assertEqual(later_timer["label"], "63cs")
        self.assertEqual(later_timer["centiseconds"], 63)
        self.assertNotContains(response, 'data-countdown-precision="centisecond"')
        self.assertNotContains(response, "data-next-read-centiseconds=")

    def test_live_scope_cards_partial_leases_selected_card_runtime_tags_hot(self):
        schedule = TagSchedule.objects.create(name="fast", interval_seconds=10)
        RuntimeTag.objects.create(provider="default", path="well/pressure", display_name="Pressure", schedule=schedule)
        RuntimeTag.objects.create(provider="default", path="well/temperature", display_name="Temperature", schedule=schedule)
        scope = LiveScope.objects.create(slug="pad-a", name="Pad A")
        card = LiveCardDefinition.objects.create(scope=scope, title="Well 01", group="Well", kind="Well")
        LiveCardPointDefinition.objects.create(card=card, label="Pressure", full_path="[default]well/pressure")
        LiveCardPointDefinition.objects.create(card=card, label="Temperature", full_path="[default]well/temperature")
        OptimizationLease.objects.all().delete()
        RuntimeDemand.objects.all().delete()

        response = self.client.get("/spot/pad-a/cards/", {"group": "well"})
        second_response = self.client.get("/spot/pad-a/cards/", {"group": "well"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(active_demand_full_paths(), {"[default]well/pressure", "[default]well/temperature"})
        self.assertEqual(OptimizationLease.objects.count(), 0)
        self.assertEqual(RuntimeDemand.objects.count(), 2)
        self.assertEqual(set(RuntimeDemand.objects.values_list("source_key", flat=True)), {"spot:pad-a:well"})

    def test_import_live_scope_csv_uses_group_kind_and_full_paths(self):
        with TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "scope.csv"
            csv_path.write_text(
                "scope,scope_name,group,kind,card,point,full_path,card_order,point_order\n"
                "pad-a,Pad A,North,Well,Well 01,Tubing Pressure,[default]well/pressure,1,2\n",
                encoding="utf-8",
            )
            call_command("import_live_scope_csv", str(csv_path))

        scope = LiveScope.objects.get(slug="pad-a")
        card = LiveCardDefinition.objects.get(scope=scope)
        point = LiveCardPointDefinition.objects.get(card=card)
        self.assertEqual(scope.name, "Pad A")
        self.assertEqual(card.group, "North")
        self.assertEqual(card.kind, "Well")
        self.assertEqual(card.sort_order, 1)
        self.assertEqual(point.full_path, "[default]well/pressure")
        self.assertEqual(point.sort_order, 2)

    def test_import_live_scope_csv_accepts_assignment_wide_shape(self):
        with TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "scope.csv"
            csv_path.write_text(
                "Spot Scope,ID (optional),Name,group,kind,Tag 1,Tag 2,display order (optional)\n"
                "wells,1,Tank_01,Tank,Oil Tank,[default]tank/level,[default]tank/volume,4\n",
                encoding="utf-8",
            )
            call_command("import_live_scope_csv", str(csv_path))

        scope = LiveScope.objects.get(slug="wells")
        card = LiveCardDefinition.objects.get(scope=scope)
        points = list(LiveCardPointDefinition.objects.filter(card=card).order_by("sort_order"))
        self.assertEqual(card.title, "Tank_01")
        self.assertEqual(card.group, "Tank")
        self.assertEqual(card.kind, "Oil Tank")
        self.assertEqual(card.sort_order, 4)
        self.assertEqual([point.full_path for point in points], ["[default]tank/level", "[default]tank/volume"])
        self.assertEqual([point.label for point in points], ["Level", "Volume"])
