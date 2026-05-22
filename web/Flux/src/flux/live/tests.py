from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from flux.base.runtime import DailyTagExtreme, LatestTagValue, RuntimeTag, TagSample, TagSchedule
from flux.opt.models import OptimizationLease
from flux.opt.services import active_demand_full_paths
from flux.sim.fluxolot_fishtank import ensure_fluxolot_fishtank, ensure_fluxolot_live_scope

from .copy_context import render_card_copy_markdown, render_card_table_markdown
from .models import LiveCardDefinition, LiveCardPointDefinition, LiveScope
from .selectors import pad_overview_cards, scope_cards
from .views import refresh_timer


class LiveSmokeTests(TestCase):
    def test_live_index_loads(self):
        response = self.client.get("/live/")
        self.assertEqual(response.status_code, 200)

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

        response = self.client.get("/live/")

        self.assertEqual(response.context["online_count"], 0)
        self.assertEqual(response.context["stale_count"], 1)
        self.assertEqual(response.context["bad_quality_count"], 1)
        self.assertContains(response, "Bad_NotFound")
        self.assertContains(response, "status-failed")

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
        self.assertEqual(cards[0].kind, "Well")
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
            page_url="http://testserver/live/field/",
        )

        self.assertIn("| Tubing Pressure | 412.123 | psi | Good | false | [default]Sites/A/Well_01/TubingPressure |", table)
        self.assertIn("docs/live-card-context.md", llm_export)
        self.assertIn('"type": "flux.live.card.context"', llm_export)
        self.assertIn('"full_path": "[default]Sites/A/Well_01/TubingPressure"', llm_export)

    def test_live_scope_routes_filter_by_group(self):
        scope = LiveScope.objects.create(slug="pad-a", name="Pad A")
        well = LiveCardDefinition.objects.create(scope=scope, title="Well 01", group="Well", kind="Producer")
        tank = LiveCardDefinition.objects.create(scope=scope, title="Tank 01", group="Tank", kind="Oil Tank")
        LiveCardPointDefinition.objects.create(card=well, label="Pressure", full_path="[default]well/pressure")
        LiveCardPointDefinition.objects.create(card=tank, label="Level", full_path="[default]tank/level")

        response = self.client.get("/live/pad-a/?group=tank")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tank 01")
        self.assertNotContains(response, "Well 01")
        self.assertContains(response, "group=tank")
        self.assertContains(response, 'hx-get="/live/pad-a/panel/?group=tank"')
        self.assertContains(response, 'hx-get="/live/pad-a/cards/?group=tank"')

    def test_live_scope_cards_partial_loads(self):
        scope = LiveScope.objects.create(slug="pad-a", name="Pad A")
        card = LiveCardDefinition.objects.create(scope=scope, title="Well 01", group="Pad A", kind="Well")
        LiveCardPointDefinition.objects.create(card=card, label="Pressure", full_path="[default]well/pressure")

        response = self.client.get("/live/pad-a/cards/?group=pad+a")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Well 01")
        self.assertContains(response, "data-live-card-copy")
        self.assertContains(response, "live-card-copy-corner")
        self.assertContains(response, "data-live-card-copy-table")
        self.assertContains(response, "data-live-card-copy-llm")
        self.assertContains(response, 'id="live-scope-refresh-panel"')
        self.assertContains(response, 'hx-swap="outerHTML"')
        self.assertContains(response, 'hx-get="/live/pad-a/cards/?group=pad%20a"')

    def test_live_scope_cards_partial_preserves_selected_group_polling_url(self):
        scope = LiveScope.objects.create(slug="pad-a", name="Pad A")
        feeder = LiveCardDefinition.objects.create(scope=scope, title="Feeder 01", group="Feeder", kind="Treat Feeder")
        light = LiveCardDefinition.objects.create(scope=scope, title="UV Light 01", group="Light", kind="UV Light")
        LiveCardPointDefinition.objects.create(card=feeder, label="Level", full_path="[default]feeder/level")
        LiveCardPointDefinition.objects.create(card=light, label="Runtime Remaining", full_path="[default]light/runtime")

        response = self.client.get("/live/pad-a/cards/", {"group": "light"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="live-scope-refresh-panel"')
        self.assertContains(response, 'hx-get="/live/pad-a/cards/?group=light"')
        self.assertContains(response, "UV Light 01")
        self.assertNotContains(response, "Feeder 01")

    def test_live_scope_panel_partial_updates_active_tab_and_polling_url(self):
        scope = LiveScope.objects.create(slug="pad-a", name="Pad A")
        feeder = LiveCardDefinition.objects.create(scope=scope, title="Feeder 01", group="Feeder", kind="Treat Feeder")
        pump = LiveCardDefinition.objects.create(scope=scope, title="Pump 01", group="Pump", kind="Recirculation Pump")
        LiveCardPointDefinition.objects.create(card=feeder, label="Level", full_path="[default]feeder/level")
        LiveCardPointDefinition.objects.create(card=pump, label="Pressure", full_path="[default]pump/pressure")

        response = self.client.get("/live/pad-a/panel/", {"group": "pump"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="live-scope-panel"')
        self.assertContains(response, 'hx-get="/live/pad-a/cards/?group=pump"')
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

        response = self.client.get("/live/pad-a/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(active_demand_full_paths(), {"[default]well/pressure", "[default]well/temperature"})

    def test_fluxolot_live_scope_renders_sir_and_missus_fishtanks(self):
        result = ensure_fluxolot_fishtank(history_days=1, history_interval_minutes=1440)
        ensure_fluxolot_live_scope(result.runtime_tags)

        response = self.client.get("/live/fluxolot/", {"group": "tank"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sir Fluxolot Fish Tank")
        self.assertContains(response, "Missus Fluxolot Fish Tank")
        self.assertContains(response, "Temperature")
        self.assertContains(response, "degF")
        self.assertContains(response, "O2 Percent")
        self.assertNotContains(response, "Sir Fluxolot Recirculation Pump")
        self.assertContains(response, 'hx-get="/live/fluxolot/cards/?group=tank"')

    def test_fluxolot_live_cards_partial_leases_tank_tags(self):
        result = ensure_fluxolot_fishtank(history_days=1, history_interval_minutes=1440)
        ensure_fluxolot_live_scope(result.runtime_tags)

        response = self.client.get("/live/fluxolot/cards/", {"group": "tank"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sir Fluxolot Fish Tank")
        self.assertContains(response, "Missus Fluxolot Fish Tank")
        self.assertContains(response, 'hx-get="/live/fluxolot/cards/?group=tank"')
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

        self.assertEqual(refresh_timer(fresh_cards), {"label": "10s", "seconds": 10, "percent": 100})
        self.assertEqual(refresh_timer(later_cards), {"label": "7s", "seconds": 7, "percent": 70})

    def test_live_scope_cards_partial_leases_selected_card_runtime_tags_hot(self):
        schedule = TagSchedule.objects.create(name="fast", interval_seconds=10)
        RuntimeTag.objects.create(provider="default", path="well/pressure", display_name="Pressure", schedule=schedule)
        RuntimeTag.objects.create(provider="default", path="well/temperature", display_name="Temperature", schedule=schedule)
        scope = LiveScope.objects.create(slug="pad-a", name="Pad A")
        card = LiveCardDefinition.objects.create(scope=scope, title="Well 01", group="Well", kind="Well")
        LiveCardPointDefinition.objects.create(card=card, label="Pressure", full_path="[default]well/pressure")
        LiveCardPointDefinition.objects.create(card=card, label="Temperature", full_path="[default]well/temperature")
        OptimizationLease.objects.all().delete()

        response = self.client.get("/live/pad-a/cards/", {"group": "well"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(active_demand_full_paths(), {"[default]well/pressure", "[default]well/temperature"})

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
                "Live Scope,ID (optional),Name,group,kind,Tag 1,Tag 2,display order (optional)\n"
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
