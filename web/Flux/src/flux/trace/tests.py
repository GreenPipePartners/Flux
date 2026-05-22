import json
from io import StringIO
from django.contrib.staticfiles import finders
from pathlib import Path
from unittest.mock import patch
from django.test import TestCase
from django.utils import timezone

from flux.base.runtime import RuntimeTag, TagSample, TagSchedule
from flux.opt.models import OptimizationLease
from flux.opt.services import active_demand_full_paths
from flux.plane import seed_trace_cache_from_runtime_history
from flux.sim.fluxolot_fishtank import ensure_fluxolot_fishtank, ensure_fluxolot_trace_profiles

from .selectors import axis_key_for_tag, trace_sample_series
from flux.trace.models import TraceAnnotation, TraceAnnotationTarget, TraceCacheCursor, TraceCachePoint, TraceProfile, TraceSignal
from trace.cache import sync_trace_cache, trace_cache_payload
from trace.importer import import_trace_scopes_csv
from trace.providers.nav_wells import WELL_TRACE_TAGS, seed_nav_well_trace_config


def has_adjacent_numeric(values):
    return any(
        left is not None and right is not None
        for left, right in zip(values, values[1:], strict=False)
    )


class FakeHistorian:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def query_raw_points(self, paths, start_ms, end_ms, return_size):
        self.calls.append((paths, start_ms, end_ms, return_size))
        return self.rows


class FakeFluxy:
    def __init__(self, rows):
        self.historian = FakeHistorian(rows)


class FakeAnnotationHistorian:
    def __init__(self):
        self.calls = []

    def store_annotations(self, paths, start_times, end_times=None, types=None, data=None, storage_ids=None, deleted=None):
        self.calls.append(
            {
                "paths": paths,
                "start_times": start_times,
                "end_times": end_times,
                "types": types,
                "data": data,
                "storage_ids": storage_ids,
            }
        )
        return ["Good"] * len(paths)


class FakeAnnotationFluxy:
    historian = FakeAnnotationHistorian()


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
        self.assertContains(response, "/static/flux/vendor/uplot/uPlot.iife.min.js?v=trace-shared-x-2")
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
        self.assertContains(response, "/static/flux/vendor/uplot/uPlot.iife.min.js?v=trace-shared-x-2")
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
        self.assertEqual(payload["x"], [int(now.timestamp())])
        self.assertEqual(payload["series"][0]["x"], [])
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
        self.assertContains(response, "Drag selects an x-range to zoom")
        self.assertContains(response, "Shift-drag pans")

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

        payload = trace_sample_series()
        self.assertEqual(payload["series"], [])
        self.assertIsNone(payload["latestReadAt"])

    def test_trace_sample_series_defaults_to_latest_four_days_and_axis_groups(self):
        fresh = self._tag("Tubing Pressure", engineering_units="psi")
        old = self._tag("Old Pressure", engineering_units="psi")
        now = timezone.now()
        TagSample.objects.create(tag=fresh, value=620.0, quality_code="Good", value_timestamp=now, read_at=now)
        old_read = now - timezone.timedelta(days=5)
        TagSample.objects.create(tag=old, value=610.0, quality_code="Good", value_timestamp=old_read, read_at=old_read)

        payload = trace_sample_series()

        self.assertEqual(len(payload["series"]), 1)
        self.assertEqual(payload["series"][0]["name"], "Tubing Pressure")
        self.assertEqual(payload["series"][0]["axisKey"], "pressure")
        self.assertEqual(payload["windowDays"], 4)
        self.assertIn({"key": "pressure", "label": "Pressure", "unit": "psi", "range": [0, 1200], "side": 1}, payload["axisGroups"])

    def test_trace_sample_series_can_filter_to_asset_name(self):
        trial = self._tag("Tank % Full", asset_name="Trace Trial Asset", engineering_units="%")
        other = self._tag("Other Rate", asset_name="Other", engineering_units="bbl/d")
        now = timezone.now()
        TagSample.objects.create(tag=trial, value=55.0, quality_code="Good", value_timestamp=now, read_at=now)
        TagSample.objects.create(tag=other, value=200.0, quality_code="Good", value_timestamp=now, read_at=now)

        payload = trace_sample_series(asset_name="Trace Trial Asset")

        self.assertEqual([series["name"] for series in payload["series"]], ["Tank % Full"])
        self.assertEqual(payload["series"][0]["axisKey"], "percent")

    def test_trace_sample_series_can_decimate_display_points(self):
        tag = self._tag("Tubing Pressure", engineering_units="psi")
        now = timezone.now()
        for index in range(10):
            read_at = now - timezone.timedelta(minutes=10 - index)
            TagSample.objects.create(tag=tag, value=index, quality_code="Good", value_timestamp=read_at, read_at=read_at)

        payload = trace_sample_series(samples_per_tag=10, display_points_per_tag=4)

        self.assertEqual(payload["series"][0]["rawCount"], 10)
        self.assertEqual(len(payload["x"]), 4)
        self.assertEqual(len(payload["series"][0]["y"]), 4)
        self.assertEqual(payload["displayPointsPerTag"], 4)

    def test_axis_key_for_tag_groups_process_ranges(self):
        self.assertEqual(axis_key_for_tag("Tubing Pressure", "psi"), "pressure")
        self.assertEqual(axis_key_for_tag("Tank % Full", "%"), "percent")
        self.assertEqual(axis_key_for_tag("Oil Rate", "bbl/d"), "process")

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
        self.assertIn("installTraceLiveRefresh", historical_page)
        self.assertIn("refreshActiveTraceSet: () => refreshActiveTraceSet", historical_page)
        self.assertIn("clearMarkers: false", historical_page)
        self.assertIn("pollLiveTrace", live_page)
        self.assertIn("navigator.clipboard.writeText", historical_page)
        self.assertIn("hoverBoldLinePlugin", historical_page)
        annotations = (static_root / "annotations.js").read_text(encoding="utf-8")
        self.assertIn("saveMarkerAnnotation", annotations)
        self.assertIn("sendPendingAnnotations", annotations)
        self.assertIn("submitMarkerAnnotation", annotations)
        markers = (static_root / "markers.js").read_text(encoding="utf-8")
        self.assertIn("trace-annotation-row", markers)
        self.assertIn("trace-annotation-draft-row", markers)
        self.assertIn("annotationCell.textContent = annotation.saved ? annotation.text", markers)
        self.assertNotIn("annotationCell.textContent = `(${marker.id})", markers)
        self.assertNotIn("ctx.fillText(`(${annotation.markerId})", markers)
        self.assertIn("function mergeLiveSeries", data)
        self.assertIn("function mergeSharedXSeries", data)
        self.assertIn("const incomingTimes = incoming.x.length ? incoming.x : incomingSharedX", data)
        self.assertIn("points: { show: false", (static_root / "chart.js").read_text(encoding="utf-8"))
        self.assertIn("function nearestSeriesIndexAtCursor", (static_root / "chart.js").read_text(encoding="utf-8"))
        self.assertNotIn("unpkg.com", historical_page + live_page)
        self.assertNotIn("cdn.plot", historical_page + live_page)

    def test_trace_signal_wraps_runtime_tag_with_display_significance(self):
        tag = self._tag("Process PV", engineering_units="psi")
        profile = TraceProfile.objects.create(key="process", label="Process")
        signal = TraceSignal.objects.create(
            profile=profile,
            tag=tag,
            axis_key="pressure",
            axis_label="Pressure",
            axis_unit="psi",
            range_min=0,
            range_max=1200,
        )

        self.assertEqual(signal.display_label, "Process PV")
        self.assertEqual(signal.display_unit, "psi")
        self.assertEqual(
            signal.historian_path,
            "histprov:Core Historian:/sys:gateway:/prov:default:/tag:FluxSim/Process PV",
        )

    def test_trace_cache_sync_bulk_queries_historian_and_upserts_points(self):
        tag = self._tag("Process PV", engineering_units="psi")
        profile = TraceProfile.objects.create(key="process", label="Process", cache_window_minutes=60)
        signal = TraceSignal.objects.create(profile=profile, tag=tag, axis_key="pressure")
        timestamp = timezone.now().replace(second=0, microsecond=0) - timezone.timedelta(minutes=1)
        rows = [
            {"path": "value_0", "timestamp": int(timestamp.timestamp() * 1000), "value": 10.5, "quality": 192},
            {"path": "value_0", "timestamp": int(timestamp.timestamp() * 1000), "value": 11.5, "quality": 192},
        ]

        result = sync_trace_cache(FakeFluxy(rows), profile_key="process", now=timestamp + timezone.timedelta(minutes=1))

        self.assertEqual(result.profile_count, 1)
        self.assertEqual(result.signal_count, 1)
        self.assertEqual(result.point_count, 1)
        self.assertEqual(TraceCachePoint.objects.get(signal=signal, timestamp=timestamp).value_float, 11.5)
        self.assertEqual(TraceCacheCursor.objects.get(signal=signal).last_timestamp, timestamp)

    def test_plane_seeds_trace_cache_from_runtime_history(self):
        tag = self._tag("Process PV", engineering_units="psi")
        profile = TraceProfile.objects.create(key="process", label="Process", cache_window_minutes=60)
        signal = TraceSignal.objects.create(profile=profile, tag=tag, axis_key="pressure")
        timestamp = timezone.now().replace(second=30, microsecond=123456)
        rounded = timestamp.replace(second=0, microsecond=0)
        TagSample.objects.create(tag=tag, value=True, quality_code="Good", value_timestamp=timestamp, read_at=timestamp)
        TagSample.objects.create(tag=tag, value="bad", quality_code="Good", value_timestamp=timestamp, read_at=timestamp)
        TagSample.objects.create(tag=tag, value=10.5, quality_code="Good", value_timestamp=timestamp, read_at=timestamp)

        point_count = seed_trace_cache_from_runtime_history(profile)

        self.assertEqual(point_count, 1)
        point = TraceCachePoint.objects.get(signal=signal, timestamp=rounded)
        self.assertEqual(point.value_float, 10.5)
        self.assertEqual(point.quality_code, "Good")

        TagSample.objects.create(
            tag=tag,
            value=11.5,
            quality_code="Stale",
            value_timestamp=timestamp,
            read_at=timestamp + timezone.timedelta(seconds=1),
        )

        point_count = seed_trace_cache_from_runtime_history(profile)

        self.assertEqual(point_count, 1)
        point.refresh_from_db()
        self.assertEqual(point.value_float, 11.5)
        self.assertEqual(point.quality_code, "Stale")

    def test_trace_cache_payload_reads_local_cache_with_signal_significance(self):
        tag = self._tag("Process PV", engineering_units="psi")
        profile = TraceProfile.objects.create(key="process", label="Process", cache_window_minutes=2)
        signal = TraceSignal.objects.create(
            profile=profile,
            tag=tag,
            label="Primary PV",
            axis_key="pressure",
            axis_label="Pressure",
            axis_unit="psi",
            range_min=0,
            range_max=1200,
        )
        start = timezone.now().replace(second=0, microsecond=0) - timezone.timedelta(minutes=1)
        TraceCachePoint.objects.create(signal=signal, timestamp=start, value_float=10.5, quality_code="Good")
        TraceCachePoint.objects.create(signal=signal, timestamp=start + timezone.timedelta(minutes=1), value_float=11.5, quality_code="Good")

        payload = trace_cache_payload(profile, window_minutes=2)

        self.assertEqual(payload["source"], "trace-cache")
        self.assertEqual(payload["profileKey"], "process")
        self.assertEqual(payload["series"][0]["name"], "Primary PV")
        self.assertEqual(payload["series"][0]["y"], [10.5, 11.5])
        self.assertEqual(payload["axisGroups"][0]["key"], "pressure")
        self.assertEqual(payload["axisGroups"][0]["range"], [0, 1200])

    def test_trace_cache_payload_step_uses_actual_sample_times_for_visible_lines(self):
        tag = self._tag("Process PV", engineering_units="psi")
        profile = TraceProfile.objects.create(key="process", label="Process", cache_window_minutes=240)
        signal = TraceSignal.objects.create(profile=profile, tag=tag, label="Primary PV", axis_key="pressure")
        start = timezone.now().replace(second=0, microsecond=0) - timezone.timedelta(hours=2)
        for index in range(3):
            TraceCachePoint.objects.create(
                signal=signal,
                timestamp=start + timezone.timedelta(hours=index),
                value_float=10.0 + index,
                quality_code="Good",
            )

        payload = trace_cache_payload(profile, window_minutes=240, step_minutes=7)

        self.assertEqual(len(payload["x"]), 3)
        self.assertEqual(payload["series"][0]["y"], [10.0, 11.0, 12.0])
        self.assertTrue(has_adjacent_numeric(payload["series"][0]["y"]))

    def test_trace_cache_profile_route_renders_from_local_cache(self):
        profile = TraceProfile.objects.create(key="process", label="Process Cache", cache_window_minutes=2)
        signal = TraceSignal.objects.create(profile=profile, tag=self._tag("Process PV"), label="Primary PV")
        now = timezone.now().replace(second=0, microsecond=0)
        TraceCachePoint.objects.create(signal=signal, timestamp=now, value_float=10.5, quality_code="Good")

        response = self.client.get("/trace/cache/process/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Process Cache")
        self.assertContains(response, "trace cache")
        self.assertContains(response, "Primary PV")
        self.assertContains(response, "This page reads local TraceCachePoint rows only")

    def test_trace_cache_profile_payload_returns_trace_cache_source(self):
        profile = TraceProfile.objects.create(key="process", label="Process Cache", cache_window_minutes=1)
        signal = TraceSignal.objects.create(profile=profile, tag=self._tag("Process PV"), label="Primary PV")
        now = timezone.now().replace(second=0, microsecond=0)
        TraceCachePoint.objects.create(signal=signal, timestamp=now, value_float=10.5, quality_code="Good")

        response = self.client.get("/trace/cache/process/payload/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()["traceChart"]
        self.assertEqual(payload["source"], "trace-cache")
        self.assertEqual(payload["profileKey"], "process")
        self.assertEqual(payload["series"][0]["name"], "Primary PV")

    def test_trace_scope_csv_import_creates_profile_tags_and_ordered_signals(self):
        csv_data = StringIO(
            "Chart Scope,ID,Name,Tag 1,Tag 2,display order\n"
            "test,T-1,Test Trace,[default]Flux/Test/PV,[edge]Flux/Test/SP,1\n"
        )

        result = import_trace_scopes_csv(csv_data)

        self.assertEqual(result.profiles, 1)
        self.assertEqual(result.tags, 2)
        self.assertEqual(result.signals, 2)
        profile = TraceProfile.objects.get(key="test")
        self.assertEqual(profile.label, "Test Trace")
        signals = list(profile.signals.select_related("tag").order_by("sort_order"))
        self.assertEqual([signal.tag.full_path for signal in signals], ["[default]Flux/Test/PV", "[edge]Flux/Test/SP"])
        self.assertEqual([signal.sort_order for signal in signals], [1, 2])

    def test_generic_trace_scope_routes_use_selected_profile_payload(self):
        csv_data = StringIO(
            "Chart Scope,ID,Name,Tag 1,display order\n"
            "test,T-1,Test Trace,[default]Flux/Test/PV,1\n"
        )
        import_trace_scopes_csv(csv_data)
        profile = TraceProfile.objects.get(key="test")
        signal = profile.signals.get()
        now = timezone.now().replace(second=0, microsecond=0)
        TraceCachePoint.objects.create(signal=signal, timestamp=now, value_float=10.5, quality_code="Good")

        page = self.client.get("/trace/test/")
        payload_response = self.client.get("/trace/test/payload/")

        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Test Trace")
        self.assertContains(page, "CSV-defined Flux.trace scope")
        self.assertEqual(payload_response.status_code, 200)
        payload = payload_response.json()["traceChart"]
        self.assertEqual(payload["profileKey"], "test")
        self.assertEqual(payload["series"][0]["fullPath"], "[default]Flux/Test/PV")

    def test_trace_scope_route_leases_scope_runtime_tags_hot(self):
        csv_data = StringIO(
            "Chart Scope,ID,Name,Tag 1,Tag 2,display order\n"
            "test,T-1,Test Trace,[default]Flux/Test/PV,[default]Flux/Test/SP,1\n"
        )
        import_trace_scopes_csv(csv_data)

        response = self.client.get("/trace/test/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(active_demand_full_paths(), {"[default]Flux/Test/PV", "[default]Flux/Test/SP"})

    def test_trace_scope_payload_leases_scope_runtime_tags_hot(self):
        csv_data = StringIO(
            "Chart Scope,ID,Name,Tag 1,Tag 2,display order\n"
            "test,T-1,Test Trace,[default]Flux/Test/PV,[default]Flux/Test/SP,1\n"
        )
        import_trace_scopes_csv(csv_data)
        OptimizationLease.objects.all().delete()

        response = self.client.get("/trace/test/payload/", {"window_minutes": "120"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(active_demand_full_paths(), {"[default]Flux/Test/PV", "[default]Flux/Test/SP"})

    def test_fluxolot_trace_scope_cycles_sir_and_missus_profiles(self):
        result = ensure_fluxolot_fishtank(history_days=1, history_interval_minutes=720)
        profiles = ensure_fluxolot_trace_profiles(result.runtime_tags)
        for profile in profiles:
            seed_trace_cache_from_runtime_history(profile)

        page = self.client.get("/trace/fluxolot/")
        sir_response = self.client.get("/trace/fluxolot/payload/", {"set": "1"})
        missus_response = self.client.get("/trace/fluxolot/payload/", {"set": "2"})

        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Fluxolot Fishtank Trace")
        self.assertContains(page, "Previous Tank")
        self.assertContains(page, "Next Tank")
        self.assertContains(page, "Trace source")
        self.assertContains(page, 'data-trace-live-refresh-seconds="15"')
        self.assertEqual(sir_response.status_code, 200)
        self.assertEqual(missus_response.status_code, 200)
        sir = sir_response.json()["traceChart"]
        missus = missus_response.json()["traceChart"]
        self.assertEqual(sir["profileKey"], "fluxolot-sir")
        self.assertEqual(missus["profileKey"], "fluxolot-missus")
        self.assertEqual(sir["setIndex"], 1)
        self.assertEqual(missus["setIndex"], 2)
        self.assertEqual(len(sir["series"]), 8)
        self.assertEqual(len(missus["series"]), 8)
        self.assertTrue(all("/Sir-Fluxolot-Fishtank_" in series["fullPath"] for series in sir["series"]))
        self.assertTrue(all("/Missus-Fluxolot-Fishtank_" in series["fullPath"] for series in missus["series"]))
        self.assertIn("Sir Fluxolot Temperature", {series["name"] for series in sir["series"]})
        self.assertIn("Missus Fluxolot Temperature", {series["name"] for series in missus["series"]})

    def test_fluxolot_trace_payload_contains_visible_line_segments(self):
        result = ensure_fluxolot_fishtank(history_days=1, history_interval_minutes=60)
        profiles = ensure_fluxolot_trace_profiles(result.runtime_tags)
        for profile in profiles:
            seed_trace_cache_from_runtime_history(profile)

        payload = self.client.get("/trace/fluxolot/payload/", {"set": "1"}).json()["traceChart"]

        self.assertGreaterEqual(len(payload["x"]), 2)
        self.assertTrue(all(has_adjacent_numeric(series["y"]) for series in payload["series"]))

    def test_fluxolot_trace_live_refresh_payload_includes_new_cache_point(self):
        result = ensure_fluxolot_fishtank(history_days=1, history_interval_minutes=60)
        profiles = ensure_fluxolot_trace_profiles(result.runtime_tags)
        for profile in profiles:
            seed_trace_cache_from_runtime_history(profile)
        profile = TraceProfile.objects.get(key="fluxolot-sir")
        signal = profile.signals.select_related("tag").order_by("sort_order", "id").first()
        latest = (
            TraceCachePoint.objects.filter(signal__profile=profile)
            .order_by("-timestamp")
            .values_list("timestamp", flat=True)
            .first()
        )
        new_timestamp = latest + timezone.timedelta(minutes=5)
        TraceCachePoint.objects.create(
            signal=signal,
            timestamp=new_timestamp,
            value_float=123.456,
            quality_code="Good",
        )

        payload = self.client.get("/trace/fluxolot/payload/", {"set": "1"}).json()["traceChart"]
        refreshed_series = next(series for series in payload["series"] if series["signalId"] == signal.id)

        self.assertEqual(payload["x"][-1], int(new_timestamp.timestamp()))
        self.assertEqual(refreshed_series["y"][-1], 123.456)

    def test_nav_well_trace_seed_creates_eight_signals_per_well(self):
        result = seed_nav_well_trace_config(limit=2)

        self.assertEqual(result["wells"], 2)
        self.assertEqual(result["signals"], 16)
        for profile in TraceProfile.objects.filter(key__startswith="nav-well-"):
            self.assertEqual(profile.signals.count(), len(WELL_TRACE_TAGS))

    def test_nav_well_trace_single_page_cycles_chart_sources(self):
        seed_nav_well_trace_config(limit=2)

        first = self.client.get("/trace/wells/payload/", {"set": "1"}).json()["traceChart"]
        second = self.client.get("/trace/wells/payload/", {"set": "2"}).json()["traceChart"]
        page = self.client.get("/trace/wells/")

        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Navigation Well Trace")
        self.assertContains(page, "Previous Well")
        self.assertContains(page, "Next Well")
        self.assertContains(page, "Trace source")
        self.assertContains(page, "Compression")
        self.assertContains(page, "Send Annotations")
        self.assertContains(page, 'data-trace-live-refresh-seconds="60"')
        self.assertContains(page, 'data-trace-annotation-url="/trace/annotations/"')
        self.assertEqual(len(first["series"]), 8)
        self.assertEqual(len(second["series"]), 8)
        self.assertNotEqual(first["profileKey"], second["profileKey"])
        self.assertNotEqual(first["series"][0]["fullPath"], second["series"][0]["fullPath"])

    def test_nav_well_trace_payload_accepts_stable_source_without_breaking_set_index(self):
        seed_nav_well_trace_config(limit=2)
        second = self.client.get("/trace/wells/payload/", {"set": "2"}).json()["traceChart"]

        by_source = self.client.get(
            "/trace/wells/payload/",
            {"source": second["wellId"], "set": "1"},
        ).json()["traceChart"]

        self.assertEqual(by_source["wellId"], second["wellId"])
        self.assertEqual(by_source["profileKey"], second["profileKey"])
        self.assertEqual(by_source["setIndex"], 2)

    def test_nav_well_trace_embed_mode_uses_same_chart_without_page_chrome(self):
        seed_nav_well_trace_config(limit=1)

        route_response = self.client.get("/trace/wells/embed/")
        query_response = self.client.get("/trace/wells/", {"embed": "1"})

        self.assertEqual(route_response.status_code, 200)
        self.assertContains(route_response, "trace-data")
        self.assertContains(route_response, "Sample Tag Trend")
        self.assertNotContains(route_response, "Ignition Companion")
        self.assertNotContains(route_response, "No historical samples recorded yet")
        self.assertEqual(query_response.status_code, 200)
        self.assertNotContains(query_response, "Ignition Companion")

    def test_trace_annotation_endpoint_stores_ignition_historian_annotation(self):
        fake = FakeAnnotationFluxy()
        tag = self._tag("Pressure A", asset_name="Trace Well")
        tag.path = "FluxTraceNavWells/1/PressureA"
        tag.save(update_fields=["path"])
        profile = TraceProfile.objects.create(key="nav-well-test", label="Test Well")
        signal = TraceSignal.objects.create(profile=profile, tag=tag, label="Pressure A")
        with patch("fluxy.Fluxy", return_value=fake):
            response = self.client.post(
                "/trace/annotations/",
                data=json.dumps(
                    {
                        "markerId": 1,
                        "pinnedAt": "2026-05-17T01:00:00+00:00",
                        "profileKey": "nav-well-test",
                        "text": "Pump check",
                        "paths": ["[default]FluxTraceNavWells/1/PressureA"],
                    }
                ),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["annotation"]["text"], "Pump check")
        annotation = TraceAnnotation.objects.get(id=payload["annotation"]["localId"])
        self.assertEqual(annotation.profile, profile)
        self.assertEqual(annotation.marker_id, 1)
        target = TraceAnnotationTarget.objects.get(annotation=annotation)
        self.assertEqual(target.signal, signal)
        self.assertEqual(str(target.ignition_storage_id), payload["annotation"]["storageIds"][0])
        call = fake.historian.calls[-1]
        self.assertEqual(call["paths"], ["[default]FluxTraceNavWells/1/PressureA"])
        self.assertEqual(call["end_times"], call["start_times"])
        self.assertEqual(call["types"], ["flux.trace.annotation"])
        self.assertEqual(len(call["storage_ids"]), 1)

    def _tag(self, display_name: str, *, asset_name: str = "Trace Trial", engineering_units: str = "") -> RuntimeTag:
        schedule = TagSchedule.objects.create(name=f"{display_name} schedule", interval_seconds=30)
        return RuntimeTag.objects.create(
            provider="default",
            path=f"FluxSim/{display_name}",
            display_name=display_name,
            asset_name=asset_name,
            engineering_units=engineering_units,
            schedule=schedule,
        )
