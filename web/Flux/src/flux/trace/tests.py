from django.test import TestCase
from django.utils import timezone

from runtime.models import RuntimeTag, TagSample, TagSchedule

from .selectors import plotly_sample_series


class TraceSmokeTests(TestCase):
    def test_trace_index_loads(self):
        response = self.client.get("/trace/")
        self.assertEqual(response.status_code, 200)

    def test_trace_index_renders_plotly_payload_for_numeric_samples(self):
        tag = self._tag("Motor Amps")
        now = timezone.now()
        TagSample.objects.create(tag=tag, value=10.5, quality_code="Good", value_timestamp=now, read_at=now)

        response = self.client.get("/trace/")

        self.assertContains(response, "trace-plotly-data")
        self.assertContains(response, "Motor Amps")
        self.assertContains(response, "Live Trace")

    def test_live_trace_index_renders_right_edge_follow_chart(self):
        tag = self._tag("Motor Amps")
        now = timezone.now()
        TagSample.objects.create(tag=tag, value=10.5, quality_code="Good", value_timestamp=now, read_at=now)

        response = self.client.get("/trace/live/")

        self.assertContains(response, "trace-live-data")
        self.assertContains(response, "right-edge follow")
        self.assertContains(response, "function isAtRightEdge()")
        self.assertContains(response, "function pollLiveTrace()")
        self.assertContains(response, "preservedRange")
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

    def test_trace_index_enables_plotly_spike_cursor_and_annotations(self):
        tag = self._tag("Motor Amps")
        now = timezone.now()
        TagSample.objects.create(tag=tag, value=10.5, quality_code="Good", value_timestamp=now, read_at=now)

        response = self.client.get("/trace/")

        self.assertContains(response, 'hovermode: "x unified"')
        self.assertContains(response, "annotations: [...traceAnnotations]")
        self.assertContains(response, 'spikemode: "across"')
        self.assertContains(response, 'spikesnap: "cursor"')

    def test_trace_index_can_pin_multiple_clicked_traces(self):
        tag = self._tag("Motor Amps")
        now = timezone.now()
        TagSample.objects.create(tag=tag, value=10.5, quality_code="Good", value_timestamp=now, read_at=now)

        response = self.client.get("/trace/")

        self.assertContains(response, "const pinnedTraceShapes = []")
        self.assertContains(response, "const pinnedTraceMarkers = []")
        self.assertContains(response, 'type: "line"')
        self.assertContains(response, "plotly_click")
        self.assertContains(response, "clickedPoint.x")
        self.assertContains(response, "Pinned Trace Values")
        self.assertContains(response, "data-pinned-trace-table")
        self.assertContains(response, "data-copy-pinned-traces")
        self.assertContains(response, "function pinnedTraceValues(clickedPoints)")
        self.assertContains(response, "function renderPinnedTraceMarkers()")
        self.assertContains(response, "function pinnedTraceMarkdown()")
        self.assertContains(response, "function eventPointValue(series, clickedPoints)")
        self.assertContains(response, "function middleEllipsis(value, limit = 15)")
        self.assertContains(response, "header.title = headingText")
        self.assertContains(response, '["Marker", "Time", "Annotate", ...traceData.map(traceHeader)]')
        self.assertContains(response, "trace-marker-table")
        self.assertContains(response, "navigator.clipboard.writeText")
        self.assertContains(response, "function addMarkerAnnotation(marker)")
        self.assertContains(response, "window.prompt")
        self.assertContains(response, "Add annotation for marker")
        self.assertContains(response, "const pinnedAt = new Date(clickedPoint.x).toISOString()")
        self.assertContains(response, "const plotPinnedAt = clickedPoint.x")
        self.assertContains(response, "x0: plotPinnedAt")
        self.assertContains(response, "text: `(${markerId})`")
        self.assertContains(response, "event.stopPropagation()")
        self.assertContains(response, "Plotly.react")
        self.assertContains(response, "Click inside the chart")
        self.assertContains(response, "data-clear-pinned-traces")

    def test_plotly_sample_series_skips_boolean_samples(self):
        tag = self._tag("Running")
        now = timezone.now()
        TagSample.objects.create(tag=tag, value=True, quality_code="Good", value_timestamp=now, read_at=now)

        self.assertEqual(plotly_sample_series(), {"series": [], "latestReadAt": None})

    def _tag(self, display_name: str) -> RuntimeTag:
        schedule = TagSchedule.objects.create(name=f"{display_name} schedule", interval_seconds=30)
        return RuntimeTag.objects.create(
            provider="default",
            path=f"FluxSim/{display_name}",
            display_name=display_name,
            asset_name="Trace Trial",
            schedule=schedule,
        )
