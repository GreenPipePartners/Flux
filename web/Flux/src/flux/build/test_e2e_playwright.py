from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from django.core.management import call_command

from flux.build.models import BuildRun
from flux.cell.models import Cell, Point, Source, Visual
from flux.e2e import FluxStaticLiveServerTestCase
from flux.mine.models import MineRun


pytestmark = pytest.mark.e2e


class BuildPlaywrightTests(FluxStaticLiveServerTestCase):
    playwright_skip_message = "Set FLUX_PLAYWRIGHT=1 to run Playwright build tests"

    def setUp(self):
        self._temp_dir = TemporaryDirectory()
        root = Path(self._temp_dir.name)
        source = root / "PLC_01.L5X"
        self.output = root / "artifacts" / "provider.json"
        source.write_text(
            """
            <RSLogix5000Content>
              <Controller Name="PLC_01" ProcessorType="1756-L83E" MajorRev="35">
                <Tags>
                  <Tag Name="Pressure" TagType="Base" DataType="REAL" />
                </Tags>
              </Controller>
            </RSLogix5000Content>
            """.strip(),
            encoding="utf-8",
        )
        call_command("flux_mine_source", str(source), "--label", "Browser PLC")
        call_command(
            "flux_build_ignition_tags", MineRun.objects.get().id, "--output", str(self.output)
        )

    def tearDown(self):
        self._temp_dir.cleanup()

    def test_build_page_renders_completed_artifact_workflow(self):
        page = self._browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            page.goto(f"{self.live_server_url}/build/", wait_until="networkidle")

            page.get_by_role("heading", name="Flux.build").wait_for(state="visible")
            page.get_by_text("Complete").wait_for(state="visible")
            page.get_by_text("1 cells built").wait_for(state="visible")
            page.get_by_text("Design Flux.cells").wait_for(state="visible")
            payload = json.loads(self.output.read_text(encoding="utf-8"))
            self.assertEqual(payload["tagType"], "Provider")
            self.assertEqual(BuildRun.objects.filter(status=BuildRun.Status.COMPLETE).count(), 1)
        finally:
            page.close()

    def test_build_page_creates_cell_draft_from_hmi_selection(self):
        root = Path(self._temp_dir.name)
        hmi_root = root / "FactoryTalk"
        (hmi_root / "Screens").mkdir(parents=True)
        (hmi_root / "Screens" / "Overview.xml").write_text(
            """
            <gfx>
              <displaySettings width="800" height="600" />
              <numericDisplay name="Pressure" left="10" top="20" width="100" height="30" tag="{[PLC]PT001}" />
              <button name="Start" left="30" top="70" width="80" height="24">
                <action type="setToOne" tag="{[PLC]StartCmd}" />
              </button>
            </gfx>
            """.strip(),
            encoding="utf-8",
        )
        call_command(
            "flux_mine_source",
            str(hmi_root),
            "--source-type",
            "factorytalk",
            "--label",
            "Browser HMI",
        )
        page = self._browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            page.goto(f"{self.live_server_url}/build/", wait_until="networkidle")
            page.locator('input[name="cell_bundle_key"]').fill("browser-hmi")
            page.locator('input[name="cell_bundle_name"]').fill("Browser HMI")
            page.locator('input[name="cell_slug"]').fill("pump-01")
            page.locator('input[name="cell_name"]').fill("Pump 01")
            page.locator('input[name="cell_group"]').fill("Pad A")
            page.locator('input[name="cell_kind"]').fill("Pump")
            first_node = page.locator("[data-build-map-node]").first
            first_checkbox = page.locator("[data-build-component-checkbox]").first
            self.assertTrue(first_checkbox.is_checked())
            first_node.click()
            self.assertFalse(first_checkbox.is_checked())
            first_node.click()
            self.assertTrue(first_checkbox.is_checked())
            page.get_by_role("button", name="Create Cell Draft").click()
            page.wait_for_url("**/build/")
            page.get_by_text("Created cell draft Pump 01").wait_for(state="visible")

            page.goto(f"{self.live_server_url}/cell/", wait_until="networkidle")
            page.get_by_role("heading", name="Flux.cell").wait_for(state="visible")
            page.get_by_text("Browser HMI").wait_for(state="visible")
            self.assertEqual(Cell.objects.get(slug="pump-01").kind, "Pump")
            self.assertEqual(Source.objects.count(), 2)
            self.assertEqual(Visual.objects.count(), 2)
            self.assertTrue(Point.objects.get(full_path="[PLC]PT001").include_live)
            self.assertFalse(Point.objects.get(full_path="[PLC]StartCmd").include_live)
        finally:
            page.close()
