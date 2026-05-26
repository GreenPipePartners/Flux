from __future__ import annotations

import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from flux.cell.models import Bundle, Cell, Point, Relationship
from flux.cell.services import seed_demo_cell_bundle
from flux.e2e import FluxStaticLiveServerTestCase


pytestmark = pytest.mark.e2e


class CellPlaywrightTests(FluxStaticLiveServerTestCase):
    playwright_skip_message = "Set FLUX_PLAYWRIGHT=1 to run Playwright cell tests"

    def setUp(self):
        self._temp_dir = TemporaryDirectory()
        self.bundle_zip = Path(self._temp_dir.name) / "cell-bundle.zip"
        with zipfile.ZipFile(self.bundle_zip, "w") as archive:
            archive.writestr(
                "cells.csv",
                "bundle,bundle_name,cell_slug,name,group,kind,description,sort_order,enabled\n"
                "browser-pad,Browser Pad,pump-01,Pump 01,Pad A,Pump,Browser imported cell,1,true\n"
                "browser-pad,Browser Pad,tank-01,Tank 01,Pad A,Tank,Browser imported cell,2,true\n",
            )
            archive.writestr(
                "points.csv",
                "bundle,cell_slug,key,label,full_path,role,engineering_units,include_live,include_trace,live_order,trace_order,axis_key,range_min,range_max,color,enabled\n"
                "browser-pad,pump-01,pressure,Pressure,[default]Pump01/Pressure,pv,psi,true,true,1,1,pressure,0,150,#35a7ff,true\n",
            )
            archive.writestr(
                "relationships.csv",
                "bundle,from_cell_slug,relationship,to_cell_slug,label,sort_order,enabled\n"
                "browser-pad,pump-01,next_area,tank-01,Next Area,1,true\n",
            )

    def tearDown(self):
        self._temp_dir.cleanup()

    def test_cell_page_imports_csv_zip_and_exposes_downloads(self):
        page = self._browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            page.goto(f"{self.live_server_url}/cell/", wait_until="networkidle")
            page.locator("#cell-bundle-zip").set_input_files(str(self.bundle_zip))
            page.get_by_role("button", name="Import Cell Bundle").click()
            page.wait_for_url("**/cell/")

            page.get_by_text("Imported 2 cells and 1 points").wait_for(state="visible")
            page.get_by_text("Browser Pad").wait_for(state="visible")
            page.locator("#cell-browser-pad-pump-01").get_by_role(
                "heading", name="Pump 01"
            ).wait_for(state="visible")
            page.locator("#cell-browser-pad-pump-01 .flux-cell-signals").get_by_text(
                "Pressure", exact=False
            ).first.wait_for(state="visible")
            page.locator("#cell-browser-pad-pump-01 input[name='body']").fill(
                "Checked from phone card"
            )
            page.locator(
                "#cell-browser-pad-pump-01 button[aria-label='Add comment to Pump 01']"
            ).click()
            page.wait_for_url("**/cell/")
            page.get_by_text("Checked from phone card").wait_for(state="visible")
            self.assertEqual(Bundle.objects.get().key, "browser-pad")
            self.assertEqual(Cell.objects.count(), 2)
            self.assertEqual(Point.objects.count(), 1)
            self.assertEqual(Relationship.objects.get().relationship_type, "next_area")

            with page.expect_download() as download_info:
                page.get_by_role("link", name="Relationships").click()
            download = download_info.value
            self.assertIn("relationships", download.suggested_filename)
            self.assertIn("next_area", Path(download.path()).read_text(encoding="utf-8"))
        finally:
            page.close()

    def test_phone_simulator_swipes_right_next_and_left_previous(self):
        seed_demo_cell_bundle()
        page = self._browser.new_page(viewport={"width": 390, "height": 844}, has_touch=True)
        try:
            page.goto(f"{self.live_server_url}/cell/phone-demo/", wait_until="networkidle")
            simulator = page.locator("[data-cell-phone-simulator]")
            frame = simulator.locator("[data-cell-phone-frame]")
            pump_card = simulator.locator("[data-cell-phone-card][data-cell-name='Pump 101']")
            tank_card = simulator.locator("[data-cell-phone-card][data-cell-name='Tank 101']")

            self.assertEqual(page.locator("header.site-header").count(), 0)
            page.get_by_role("link", name="Return to Flux home").wait_for(state="visible")
            self.assertEqual(simulator.locator("[data-cell-phone-counter]").count(), 0)
            pump_card.wait_for(state="visible")
            simulator.locator("[data-cell-phone-chart]").first.wait_for(state="visible")
            self.assertGreater(simulator.locator(".cell-phone-chart-series").count(), 0)
            self.assertTrue(pump_card.is_visible())

            frame.dispatch_event(
                "pointerdown",
                {
                    "pointerId": 1,
                    "pointerType": "touch",
                    "clientX": 80,
                    "clientY": 360,
                    "button": 0,
                    "isPrimary": True,
                },
            )
            frame.dispatch_event(
                "pointerup",
                {
                    "pointerId": 1,
                    "pointerType": "touch",
                    "clientX": 265,
                    "clientY": 362,
                    "button": 0,
                    "isPrimary": True,
                },
            )

            tank_card.wait_for(state="visible")
            self.assertTrue(tank_card.is_visible())

            frame.dispatch_event(
                "pointerdown",
                {
                    "pointerId": 2,
                    "pointerType": "touch",
                    "clientX": 265,
                    "clientY": 360,
                    "button": 0,
                    "isPrimary": True,
                },
            )
            frame.dispatch_event(
                "pointerup",
                {
                    "pointerId": 2,
                    "pointerType": "touch",
                    "clientX": 80,
                    "clientY": 362,
                    "button": 0,
                    "isPrimary": True,
                },
            )

            pump_card.wait_for(state="visible")
            self.assertTrue(pump_card.is_visible())
        finally:
            page.close()
