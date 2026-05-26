from __future__ import annotations

import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from flux.e2e import FluxStaticLiveServerTestCase
from flux.mine.models import MineRun


pytestmark = pytest.mark.e2e


class MinePlaywrightTests(FluxStaticLiveServerTestCase):
    playwright_skip_message = "Set FLUX_PLAYWRIGHT=1 to run Playwright mine tests"

    def setUp(self):
        self._temp_dir = TemporaryDirectory()
        root = Path(self._temp_dir.name)
        self.factorytalk_zip = root / "factorytalk.zip"
        with zipfile.ZipFile(self.factorytalk_zip, "w") as archive:
            archive.writestr(
                "Displays/Overview.xml",
                """
                <gfx>
                  <displaySettings width="800" height="600" />
                  <numericDisplay name="Pressure" left="10" top="20" tag="{[PLC]Pressure}" />
                </gfx>
                """.strip(),
            )
            archive.writestr("Parameters/Overview.par", "#1=[PLC]Pressure\n")

    def tearDown(self):
        self._temp_dir.cleanup()

    def test_mine_page_uploads_factorytalk_zip_and_renders_hmi_count(self):
        page = self._browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            page.goto(f"{self.live_server_url}/mine/", wait_until="networkidle")
            page.locator("#mine-source-label").fill("Browser HMI")
            page.locator("#mine-source-type").select_option("factorytalk")
            page.locator("#mine-source-file").set_input_files(str(self.factorytalk_zip))
            page.get_by_role("button", name="Import Source").click()
            page.wait_for_url("**/mine/")

            page.get_by_role("heading", name="Flux.mine").wait_for(state="visible")
            page.get_by_text("Imported mine run").wait_for(state="visible")
            page.get_by_text("Complete").wait_for(state="visible")
            page.get_by_text("0 PLCs mined · 1 HMIs mined").wait_for(state="visible")
            page.get_by_text("Recover Tags and HMI Primitives").wait_for(state="visible")
            self.assertEqual(MineRun.objects.filter(status=MineRun.Status.COMPLETE).count(), 1)
        finally:
            page.close()
