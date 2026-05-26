from __future__ import annotations

import json

import pytest

from flux.sim.models import TagSelection
from flux.base.services import import_provider_json_bytes
from flux.e2e import FluxStaticLiveServerTestCase
from flux.sim.jobs import run_next_sim_job
from flux.sim.models import TagConfig
from flux.sim.provider_tree import selected_source_paths
from flux.sim.tests import provider_export_fixture


pytestmark = pytest.mark.e2e


class SimProviderTreePlaywrightTests(FluxStaticLiveServerTestCase):
    playwright_skip_message = "Set FLUX_PLAYWRIGHT=1 to run Playwright sim tests"

    def setUp(self):
        import_provider_json_bytes(
            json.dumps(provider_export_fixture()).encode("utf-8"),
            provider_name="ACM02",
            source_name="playwright-provider.json",
        )

    def test_lazy_provider_tree_selects_scope_and_starts_simulation(self):
        page = self._browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            page.goto(
                f"{self.live_server_url}/sim/?card=sim-output&mode=detail&provider=ACM02",
                wait_until="networkidle",
            )
            page.locator('[aria-label="Toggle Area"]').click()
            page.locator("text=Device01").wait_for(state="visible")
            page.locator('[aria-label="Toggle Device01"]').click()
            page.locator("text=PV").wait_for(state="visible")

            device_row = page.locator('label[title="Area/Device01"]')
            device_row.locator('[data-sim-tree-checkbox]').check()
            page.get_by_role("button", name="Start Simulation").click()
            page.wait_for_url("**/sim/?card=sim-output&mode=detail&provider=ACM02")
            run_next_sim_job()

            self.assertTrue(TagSelection.objects.filter(provider__name="ACM02", path="Area/Device01", enabled=True).exists())
            self.assertEqual(TagSelection.objects.get(provider__name="ACM02", path="Area/Device01").config, {})
            self.assertEqual(selected_source_paths("ACM02"), ["Area/Device01/PV"])
            self.assertFalse(TagConfig.objects.filter(source_path="Area/Device01/PV", materialized=True).exists())
        finally:
            page.close()
