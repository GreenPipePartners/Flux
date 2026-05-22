from __future__ import annotations

import os
import unittest

import pytest
from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.utils import timezone

from flux.base.models import FieldAgentHeartbeat, FieldDevice, FieldEndpoint, FieldTag
from flux.base.runtime import RuntimeTag, TagSchedule

from .models import IgnitionBridgeConfig


pytestmark = pytest.mark.e2e


class DashboardSimServerPlaywrightTests(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        if os.getenv("FLUX_PLAYWRIGHT") != "1":
            raise unittest.SkipTest("Set FLUX_PLAYWRIGHT=1 to run Playwright dashboard tests")
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
        get_user_model().objects.create_user(username="existing", password="test-pass")
        self.endpoint = FieldEndpoint.objects.create(
            name="sir-fluxolot-fishtank",
            endpoint_url="opc.tcp://localhost:4840/flux/fluxolot/sir",
            application_uri="urn:flux:fluxolot-fishtank:sir",
            product_uri="urn:flux:fluxolot-fishtank",
            namespace_uri="urn:flux:fluxolot-fishtank:sir",
            enabled=True,
            status=FieldEndpoint.Status.RUNNING,
            last_seen_at=timezone.now(),
        )
        self.device = FieldDevice.objects.create(
            endpoint=self.endpoint,
            name="Sir-Fluxolot-Fishtank",
            device_type="Simulator",
        )
        FieldTag.objects.create(device=self.device, name="Pressure", data_type=FieldTag.DataType.FLOAT)
        FieldAgentHeartbeat.objects.create(endpoint=self.endpoint, instance_id="sir-fluxolot-fishtank")
        IgnitionBridgeConfig.objects.create(
            name="default",
            role=IgnitionBridgeConfig.Role.SIMULATOR,
            base_url="http://localhost:8088/system/webdev/flux",
            token="secret-token",
            last_test_ok=True,
            last_test_at=timezone.now(),
            last_test_message="Connected to Ignition 8.3.6 (b2026042713).",
        )
        schedule = TagSchedule.objects.create(name="dashboard e2e", interval_seconds=30)
        RuntimeTag.objects.create(
            provider="default",
            path="DashboardE2E/StalePressure",
            display_name="Stale Pressure",
            asset_name="Dashboard E2E",
            schedule=schedule,
        )

    def test_fluxolot_button_updates_on_stop_and_start(self):
        page = self._browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            page.goto(f"{self.live_server_url}/", wait_until="networkidle")
            page.wait_for_function("window.htmx !== undefined")

            self.click_comp_card_mode(page, "sim-config", "configure")
            row = page.locator("#sim-config-comp-focus .stale-row").filter(has_text="sir-fluxolot-fishtank")
            row.get_by_role("button", name="■ Stop").click()
            row = page.locator("#sim-config-comp-focus .stale-row").filter(has_text="sir-fluxolot-fishtank")
            row.get_by_role("button", name="▶ Start").wait_for(state="visible")
            page.wait_for_function(
                """
                () => [...document.querySelectorAll('#sim-config-comp-focus .stale-row')]
                    .find((row) => row.textContent.includes('sir-fluxolot-fishtank'))
                    ?.textContent.includes('disabled')
                """
            )

            row = page.locator("#sim-config-comp-focus .stale-row").filter(has_text="sir-fluxolot-fishtank")
            row.get_by_role("button", name="▶ Start").click()
            row.get_by_role("button", name="Starting...").wait_for(state="visible")

            self.endpoint.refresh_from_db()
            self.endpoint.status = FieldEndpoint.Status.RUNNING
            self.endpoint.last_seen_at = timezone.now()
            self.endpoint.save(update_fields=["status", "last_seen_at", "updated_at"])

            row.get_by_role("button", name="■ Stop").wait_for(state="visible", timeout=5000)
            page.wait_for_function(
                """
                () => [...document.querySelectorAll('#sim-config-comp-focus .stale-row')]
                    .find((row) => row.textContent.includes('sir-fluxolot-fishtank'))
                    ?.textContent.includes('running')
                """
            )
        finally:
            page.close()

    def test_dashboard_comp_card_mode_controls_swap_expected_views(self):
        page = self._browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            page.goto(f"{self.live_server_url}/", wait_until="networkidle")
            page.wait_for_function("window.htmx !== undefined")

            self.assert_no_comp_focus(page)
            self.assert_comp_card_mode(page, "bridges", "summary")
            self.assert_card_contains(page, "bridges", "Flux.bridge")
            self.assert_card_contains(page, "bridges", "1 Simulated")
            self.click_comp_card_mode(page, "bridges", "detail")
            self.assert_comp_focus(page, "bridges", "detail")
            self.assert_active_element(page, "bridges-comp-focus")
            self.assert_focus_contains(page, "bridges", "default / Simulator")
            self.assert_focus_contains(page, "bridges", "Connected to Ignition 8.3.6")
            self.assert_card_is_anchor(page, "bridges")
            self.click_comp_card_mode(page, "bridges", "configure")
            self.assert_comp_focus(page, "bridges", "configure")
            self.assert_active_element(page, "bridges-comp-focus")
            self.assert_focus_contains(page, "bridges", "Save bridge")
            self.assert_focus_contains(page, "bridges", "Test")
            self.assert_focus_contains(page, "bridges", "Delete")
            self.click_comp_card_mode(page, "bridges", "summary")
            self.assert_no_comp_focus(page)
            self.assert_active_element(page, "bridges-comp-card")
            self.assert_card_not_contains(page, "bridges", "default / Simulator")

            self.assert_comp_card_mode(page, "sim-config", "summary")
            self.assert_card_contains(page, "sim-config", "Flux.sim")
            self.assert_card_contains(page, "sim-config", "1 OPC Servers")
            self.assert_card_contains(page, "sim-config", "1 Tags")
            self.click_comp_card_mode(page, "sim-config", "detail")
            self.assert_comp_focus(page, "sim-config", "detail")
            self.assert_focus_contains(page, "sim-config", "Runtime Connection")
            self.assert_focus_contains(page, "sim-config", "sir-fluxolot-fishtank")
            self.assert_card_is_anchor(page, "sim-config")
            self.click_comp_card_mode(page, "sim-config", "configure")
            self.assert_comp_focus(page, "sim-config", "configure")
            self.assert_focus_contains(page, "sim-config", "OPC server runtime")

            self.assert_comp_card_mode(page, "serve", "summary")
            self.assert_card_not_contains(page, "serve", "Serve Logs")
            self.click_comp_card_mode(page, "serve", "detail")
            self.assert_comp_focus(page, "serve", "detail")
            self.assert_focus_contains(page, "serve", "Serve Logs")

            self.assert_comp_card_mode(page, "live", "summary")
            self.assert_card_not_contains(page, "live", "Refresh stale reads now")
            self.click_comp_card_mode(page, "live", "configure")
            self.assert_comp_focus(page, "live", "configure")
            self.assert_focus_contains(page, "live", "Refresh stale reads now")
            self.assert_focus_contains(page, "live", "Stale Pressure")
            self.click_comp_card_mode(page, "live", "summary")
            self.assert_no_comp_focus(page)
            self.assert_card_not_contains(page, "live", "Refresh stale reads now")
        finally:
            page.close()

    def click_comp_card_mode(self, page, card_id: str, mode: str) -> None:
        labels = {
            "summary": "Show summary view",
            "detail": "Show detail view",
            "configure": "Show configure view",
        }
        page.locator(f"#{card_id}-comp-card").get_by_role("button", name=labels[mode]).click()
        self.assert_comp_card_mode(page, card_id, mode)

    def assert_comp_card_mode(self, page, card_id: str, mode: str) -> None:
        page.wait_for_function(
            """
            ({ selector, mode }) => document.querySelector(selector)?.dataset.compCardMode === mode
            """,
            arg={"selector": f"#{card_id}-comp-card", "mode": mode},
        )
        assert page.locator(f"#{card_id}-comp-card [aria-pressed='true']").count() == 1

    def assert_no_comp_focus(self, page) -> None:
        page.wait_for_function("() => document.querySelector('#dashboard-comp-focus') === null")

    def assert_comp_focus(self, page, card_id: str, mode: str) -> None:
        page.wait_for_function(
            """
            ({ selector, mode }) => document.querySelector(selector)?.dataset.compMode === mode
            """,
            arg={"selector": f"#{card_id}-comp-focus", "mode": mode},
        )

    def assert_card_is_anchor(self, page, card_id: str) -> None:
        page.wait_for_function(
            """
            selector => document.querySelector(selector)?.classList.contains('comp-card-anchor')
            """,
            arg=f"#{card_id}-comp-card",
        )

    def assert_active_element(self, page, element_id: str) -> None:
        page.wait_for_function(
            """
            elementId => document.activeElement?.id === elementId
            """,
            arg=element_id,
        )

    def assert_card_contains(self, page, card_id: str, text: str) -> None:
        page.wait_for_function(
            """
            ({ selector, text }) => document.querySelector(selector)?.textContent.includes(text)
            """,
            arg={"selector": f"#{card_id}-comp-card", "text": text},
        )

    def assert_card_not_contains(self, page, card_id: str, text: str) -> None:
        page.wait_for_function(
            """
            ({ selector, text }) => !document.querySelector(selector)?.textContent.includes(text)
            """,
            arg={"selector": f"#{card_id}-comp-card", "text": text},
        )

    def assert_focus_contains(self, page, card_id: str, text: str) -> None:
        page.wait_for_function(
            """
            ({ selector, text }) => document.querySelector(selector)?.textContent.includes(text)
            """,
            arg={"selector": f"#{card_id}-comp-focus", "text": text},
        )
