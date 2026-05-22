from __future__ import annotations

import os
import unittest

import pytest
from django.contrib.staticfiles.testing import StaticLiveServerTestCase

from flux.sim.fluxolot_fishtank import ensure_fluxolot_fishtank, ensure_fluxolot_live_scope


pytestmark = pytest.mark.e2e


class FluxolotLiveResponsivePlaywrightTests(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        if os.getenv("FLUX_PLAYWRIGHT") != "1":
            raise unittest.SkipTest("Set FLUX_PLAYWRIGHT=1 to run Playwright live tests")
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
        result = ensure_fluxolot_fishtank(history_days=1, history_interval_minutes=1440)
        ensure_fluxolot_live_scope(result.runtime_tags)

    def test_fluxolot_tank_cards_do_not_overlap_at_half_width(self):
        page = self._browser.new_page(viewport={"width": 620, "height": 900})
        try:
            page.goto(f"{self.live_server_url}/live/fluxolot/?group=tank", wait_until="networkidle")
            page.get_by_text("Sir Fluxolot Fish Tank").wait_for(state="visible")
            page.get_by_text("Missus Fluxolot Fish Tank").wait_for(state="visible")

            boxes = page.locator(".live-equipment-card").evaluate_all(
                """
                cards => cards.map((card) => {
                  const rect = card.getBoundingClientRect();
                  return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom };
                })
                """
            )

            self.assertGreaterEqual(len(boxes), 2)
            for index, first in enumerate(boxes):
                for second in boxes[index + 1 :]:
                    horizontal_overlap = first["left"] < second["right"] and second["left"] < first["right"]
                    vertical_overlap = first["top"] < second["bottom"] and second["top"] < first["bottom"]
                    self.assertFalse(horizontal_overlap and vertical_overlap, (first, second))
        finally:
            page.close()
