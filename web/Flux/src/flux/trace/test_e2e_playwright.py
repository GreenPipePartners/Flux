from __future__ import annotations

import pytest
from django.utils import timezone

from flux.base.runtime import RuntimeTag, TagSample, TagSchedule
from flux.e2e import FluxStaticLiveServerTestCase
from flux.plane import seed_plane_samples_from_runtime_history
from flux.plane.models import Sample
from flux.sim.fluxolot_fishtank import ensure_fluxolot_fishtank, ensure_fluxolot_trace_profiles
from flux.trace.models import TraceProfile, TraceSignal


pytestmark = pytest.mark.e2e


class TracePlaywrightTests(FluxStaticLiveServerTestCase):
    playwright_skip_message = "Set FLUX_PLAYWRIGHT=1 to run Playwright trace tests"

    def setUp(self):
        schedule = TagSchedule.objects.create(name=f"trace e2e {self._testMethodName}", interval_seconds=30)
        tag = RuntimeTag.objects.create(
            provider="default",
            path=f"FluxTraceE2E/{self._testMethodName}/Pressure",
            display_name="Pressure",
            asset_name="Trace E2E",
            schedule=schedule,
        )
        self.tag = tag
        self.profile = TraceProfile.objects.create(key=f"trace-e2e-{self._testMethodName}", label="Trace E2E")
        self.signal = TraceSignal.objects.create(profile=self.profile, tag=tag, label="Pressure")
        base = timezone.now() - timezone.timedelta(minutes=5)
        for index in range(8):
            read_at = base + timezone.timedelta(seconds=index * 30)
            TagSample.objects.create(
                tag=tag,
                value=100 + index,
                quality_code="Good",
                value_timestamp=read_at,
                read_at=read_at,
            )
        seed_plane_samples_from_runtime_history(self.profile, sample_limit=None)
        self.signal.refresh_from_db()

    def test_historical_trace_click_pins_marker(self):
        page = self._browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            page.goto(f"{self.live_server_url}/chart/?card=trace-chart&mode=detail", wait_until="networkidle")
            chart = page.locator("[data-trace-chart]")
            chart.wait_for(state="visible")
            box = chart.bounding_box()
            assert box is not None

            page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)

            page.locator(".trace-marker-table").wait_for(state="visible")
            assert page.locator(".trace-marker-table tbody tr").count() == 1
            assert page.evaluate("window.__fluxTraceDebug.pinnedTraceMarkers.length") == 1
        finally:
            page.close()

    def test_historical_trace_side_scroll_pans_x_axis(self):
        page = self._browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            page.goto(f"{self.live_server_url}/chart/?card=trace-chart&mode=detail", wait_until="networkidle")
            chart = page.locator("[data-trace-chart]")
            chart.wait_for(state="visible")
            box = chart.bounding_box()
            assert box is not None

            before = page.evaluate("window.__fluxTraceDebug.plot.scales.x.min")
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            page.mouse.wheel(240, 0)
            page.wait_for_function("initial => window.__fluxTraceDebug.plot.scales.x.min !== initial", arg=before)
            after = page.evaluate("window.__fluxTraceDebug.plot.scales.x.min")

            assert after != before
        finally:
            page.close()

    def test_live_trace_debug_poll_appends_new_samples(self):
        page = self._browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            page.goto(f"{self.live_server_url}/chart/stream/", wait_until="networkidle")
            page.locator("[data-trace-live-chart]").wait_for(state="visible")
            initial_count = page.evaluate("window.__fluxLiveTraceDebug.aligned.data[0].length")
            read_at = timezone.now()
            Sample.objects.create(series=self.signal.series, timestamp=read_at, value_float=222.0, quality_code="Good")

            page.evaluate("() => window.__fluxLiveTraceDebug.pollLiveTrace()")
            page.wait_for_function(
                "initial => window.__fluxLiveTraceDebug.aligned.data[0].length > initial",
                arg=initial_count,
            )

            values = page.evaluate("window.__fluxLiveTraceDebug.liveTraceData[0].y")
            assert 222 in values
        finally:
            page.close()

    def test_fluxolot_trace_debug_live_refresh_loads_new_cache_point(self):
        result = ensure_fluxolot_fishtank(history_days=1, history_interval_minutes=60)
        profiles = ensure_fluxolot_trace_profiles(result.runtime_tags)
        for profile in profiles:
            seed_plane_samples_from_runtime_history(profile)
        profile = TraceProfile.objects.get(key="fluxolot-sir")
        signal = profile.signals.order_by("sort_order", "id").first()

        page = self._browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            page.goto(f"{self.live_server_url}/chart/fluxolot/", wait_until="networkidle")
            page.locator("[data-trace-chart]").wait_for(state="visible")
            latest = Sample.objects.filter(series__chart_signals__profile=profile).order_by("-timestamp").values_list("timestamp", flat=True).first()
            new_timestamp = latest + timezone.timedelta(minutes=5)
            Sample.objects.create(
                series=signal.series,
                timestamp=new_timestamp,
                value_float=321.0,
                quality_code="Good",
            )

            page.evaluate("() => window.__fluxTraceDebug.refreshActiveTraceSet()")
            page.wait_for_function("() => window.__fluxTraceDebug.traceSeries[0].y.includes(321)")
        finally:
            page.close()
