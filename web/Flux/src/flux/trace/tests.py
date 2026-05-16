from django.contrib.staticfiles import finders
from pathlib import Path
from django.test import TestCase
from django.utils import timezone

from flux.base.runtime import RuntimeTag, TagSample, TagSchedule

from .selectors import trace_sample_series


class TraceSmokeTests(TestCase):
    def test_trace_index_loads(self):
        response = self.client.get("/trace/")
        self.assertEqual(response.status_code, 200)

    def test_trace_index_renders_uplot_payload_for_numeric_samples(self):
        tag = self._tag("Motor Amps")
        now = timezone.now()
        TagSample.objects.create(tag=tag, value=10.5, quality_code="Good", value_timestamp=now, read_at=now)

        response = self.client.get("/trace/")

        self.assertContains(response, "trace-data")
        self.assertContains(response, "/static/flux/vendor/uplot/uPlot.iife.min.js")
        self.assertContains(response, "flux/trace/historical-page.js")
        self.assertContains(response, "Motor Amps")
        self.assertContains(response, "Live Trace")
        self.assertNotContains(response, "cdn.plot.ly")

    def test_live_trace_index_renders_right_edge_follow_chart(self):
        tag = self._tag("Motor Amps")
        now = timezone.now()
        TagSample.objects.create(tag=tag, value=10.5, quality_code="Good", value_timestamp=now, read_at=now)

        response = self.client.get("/trace/live/")

        self.assertContains(response, "trace-live-data")
        self.assertContains(response, "/static/flux/vendor/uplot/uPlot.iife.min.js")
        self.assertContains(response, "flux/trace/live-page.js")
        self.assertContains(response, "right-edge follow")
        self.assertContains(response, "data-samples-url")
        self.assertContains(response, "data-window-minutes")
        self.assertContains(response, "data-live-trace-toggle")

    def test_live_trace_samples_returns_new_numeric_samples(self):
        tag = self._tag("Motor Amps")
        now = timezone.now()
        older = now - timezone.timedelta(seconds=10)
        TagSample.objects.create(tag=tag, value=10.5, quality_code="Good", value_timestamp=older, read_at=older)
        TagSample.objects.create(tag=tag, value=11.5, quality_code="Good", value_timestamp=now, read_at=now)

        response = self.client.get("/trace/live/samples/", {"since": older.isoformat()})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["series"][0]["name"], "Motor Amps")
        self.assertEqual(payload["series"][0]["y"], [11.5])
        self.assertEqual(payload["series"][0]["tagId"], tag.id)
        self.assertIsNotNone(payload["latestReadAt"])

    def test_trace_index_omits_manual_trace_and_annotation_forms(self):
        response = self.client.get("/trace/")

        self.assertNotContains(response, "Add traces")
        self.assertNotContains(response, "Add Annotation")
        self.assertNotContains(response, "data-trace-annotation-form")

    def test_trace_index_enables_uplot_trace_cursor_and_annotations(self):
        tag = self._tag("Motor Amps")
        now = timezone.now()
        TagSample.objects.create(tag=tag, value=10.5, quality_code="Good", value_timestamp=now, read_at=now)

        response = self.client.get("/trace/")

        self.assertContains(response, "data-trace-chart")
        self.assertContains(response, "flux/trace/historical-page.js")
        self.assertContains(response, "Wheel zooms; side-scroll pans; drag pans")

    def test_trace_index_can_pin_multiple_clicked_traces(self):
        tag = self._tag("Motor Amps")
        now = timezone.now()
        TagSample.objects.create(tag=tag, value=10.5, quality_code="Good", value_timestamp=now, read_at=now)

        response = self.client.get("/trace/")

        self.assertContains(response, "Pinned Trace Values")
        self.assertContains(response, "data-pinned-trace-table")
        self.assertContains(response, "data-copy-pinned-traces")
        self.assertContains(response, "Click inside the chart")
        self.assertContains(response, "data-clear-pinned-traces")

    def test_trace_sample_series_skips_boolean_samples(self):
        tag = self._tag("Running")
        now = timezone.now()
        TagSample.objects.create(tag=tag, value=True, quality_code="Good", value_timestamp=now, read_at=now)

        self.assertEqual(trace_sample_series(), {"series": [], "latestReadAt": None})

    def test_trace_clone_routes_redirect_to_trace(self):
        self.assertRedirects(self.client.get("/trace-clone/"), "/trace/", fetch_redirect_response=False)
        self.assertRedirects(self.client.get("/trace-clone/live/"), "/trace/live/", fetch_redirect_response=False)

    def test_trace_static_assets_are_local(self):
        expected_assets = [
            "flux/vendor/uplot/uPlot.min.css",
            "flux/vendor/uplot/uPlot.iife.min.js",
            "flux/trace/data.js",
            "flux/trace/chart.js",
            "flux/trace/interactions.js",
            "flux/trace/markers.js",
            "flux/trace/historical-page.js",
            "flux/trace/live-page.js",
        ]

        for asset in expected_assets:
            with self.subTest(asset=asset):
                self.assertIsNotNone(finders.find(asset))

    def test_trace_modules_keep_performance_interaction_contracts(self):
        static_root = Path(__file__).resolve().parents[2] / "static" / "flux" / "trace"
        interactions = (static_root / "interactions.js").read_text(encoding="utf-8")
        live_page = (static_root / "live-page.js").read_text(encoding="utf-8")
        historical_page = (static_root / "historical-page.js").read_text(encoding="utf-8")
        data = (static_root / "data.js").read_text(encoding="utf-8")

        self.assertIn("Math.abs(event.deltaX) > Math.abs(event.deltaY)", interactions)
        self.assertIn("const shift = event.deltaX * secondsPerPixel", interactions)
        self.assertIn("function closestTraceIndex", interactions)
        self.assertIn("mergeLiveSeries", live_page)
        self.assertIn("followRightEdge", live_page)
        self.assertIn("pinTraceMarker", historical_page)
        self.assertIn("navigator.clipboard.writeText", historical_page)
        self.assertIn("function mergeLiveSeries", data)
        self.assertNotIn("unpkg.com", historical_page + live_page)
        self.assertNotIn("cdn.plot", historical_page + live_page)

    def _tag(self, display_name: str) -> RuntimeTag:
        schedule = TagSchedule.objects.create(name=f"{display_name} schedule", interval_seconds=30)
        return RuntimeTag.objects.create(
            provider="default",
            path=f"FluxSim/{display_name}",
            display_name=display_name,
            asset_name="Trace Trial",
            schedule=schedule,
        )
