from __future__ import annotations

import os
import unittest

import pytest
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.utils import timezone

from flux.base.runtime import RuntimeTag, TagSample, TagSchedule


pytestmark = pytest.mark.e2e


class TracePlaywrightTests(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        if os.getenv("FLUX_PLAYWRIGHT") != "1":
            raise unittest.SkipTest("Set FLUX_PLAYWRIGHT=1 to run Playwright trace tests")
        os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "1")
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise unittest.SkipTest("Install Playwright to run browser tests") from exc

        super().setUpClass()
        cls._playwright = sync_playwright().start()
        cls._browser = cls._playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        browser = getattr(cls, "_browser", None)
        if browser is not None:
            browser.close()
        playwright = getattr(cls, "_playwright", None)
        if playwright is not None:
            playwright.stop()
        super().tearDownClass()

    def setUp(self):
        schedule = TagSchedule.objects.create(name=f"trace e2e {self._testMethodName}", interval_seconds=30)
        tag = RuntimeTag.objects.create(
            provider="default",
            path=f"FluxTraceE2E/{self._testMethodName}/Pressure",
            display_name="Pressure",
            asset_name="Trace E2E",
            schedule=schedule,
        )
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

    def test_historical_trace_click_pins_marker(self):
        page = self._browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            page.goto(f"{self.live_server_url}/trace/", wait_until="networkidle")
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
            page.goto(f"{self.live_server_url}/trace/", wait_until="networkidle")
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
