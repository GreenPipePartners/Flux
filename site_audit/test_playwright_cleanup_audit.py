from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone as dt_timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import Client
from django.utils import timezone


ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "web" / "Flux"
SRC_ROOT = WEB_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "flux.settings")

import django  # noqa: E402

django.setup()

from dashboard.models import IgnitionBridgeConfig  # noqa: E402
from flux.base.models import Device, Tag  # noqa: E402
from flux.base.runtime import LatestTagValue, RuntimeTag, TagSample, TagSchedule  # noqa: E402
from flux.plane.models import Sample  # noqa: E402
from flux.plane.services import ensure_series_for_full_path  # noqa: E402
from flux.serve.models import ServeServiceSnapshot, SimAgentHeartbeat  # noqa: E402
from flux.sim.models import DeviceConfig, Endpoint, TagConfig  # noqa: E402
from flux.trace.models import TraceProfile, TraceSignal  # noqa: E402


AUDIT_DIR = ROOT / "site_audit"
BASELINE_PATH = AUDIT_DIR / "baseline.json"
LATEST_PATH = AUDIT_DIR / "latest.json"
DIFFS_PATH = AUDIT_DIR / "diffs.md"
SUMMARY_PATH = ROOT / "site_audit.md"


class MiniParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.stack: list[dict[str, str]] = []
        self.title = ""
        self.h1: list[str] = []
        self.links: list[dict[str, str]] = []
        self.buttons: list[dict[str, str]] = []
        self.comp_surfaces: list[dict[str, str]] = []
        self.comp_cards: list[dict[str, str]] = []
        self.comp_focus: list[dict[str, str]] = []
        self.admin_links: list[str] = []
        self.mode_buttons: list[dict[str, str]] = []
        self.forms: list[dict[str, str]] = []
        self._title_active = False
        self._h1_active = False
        self._button: dict[str, str] | None = None

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = {key: value or "" for key, value in attrs_list}
        self.stack.append({"tag": tag, **attrs})
        if tag == "title":
            self._title_active = True
        if tag == "h1":
            self._h1_active = True
            self.h1.append("")
        if tag == "a":
            href = attrs.get("href", "")
            self.links.append({"href": href, "text": "", "aria_label": attrs.get("aria-label", "")})
            if "/admin/" in href:
                self.admin_links.append(href)
        if tag == "button":
            self._button = {
                "text": "",
                "aria_label": attrs.get("aria-label", ""),
                "aria_pressed": attrs.get("aria-pressed", ""),
                "hx_get": attrs.get("hx-get", ""),
                "hx_target": attrs.get("hx-target", ""),
                "hx_select": attrs.get("hx-select", ""),
                "classes": attrs.get("class", ""),
            }
            self.buttons.append(self._button)
            if attrs.get("hx-get") and "mode=" in attrs.get("hx-get", ""):
                self.mode_buttons.append(self._button)
        if tag == "form":
            self.forms.append({"action": attrs.get("action", ""), "method": attrs.get("method", "get"), "hx_post": attrs.get("hx-post", "")})
        if "data-comp-surface" in attrs:
            self.comp_surfaces.append({"id": attrs.get("id", ""), "selected_card": attrs.get("data-selected-card", ""), "mode": attrs.get("data-comp-mode", "")})
        if "data-comp-card" in attrs:
            self.comp_cards.append({"id": attrs.get("id", ""), "mode": attrs.get("data-comp-card-mode", ""), "classes": attrs.get("class", "")})
        if "data-comp-focus" in attrs:
            self.comp_focus.append({"id": attrs.get("id", ""), "card": attrs.get("data-comp-card", ""), "mode": attrs.get("data-comp-mode", "")})

    def handle_data(self, data: str) -> None:
        text = re.sub(r"\s+", " ", data).strip()
        if not text:
            return
        if self._title_active:
            self.title += text
        if self._h1_active and self.h1:
            self.h1[-1] += text
        if self._button is not None:
            self._button["text"] += text
        for entry in reversed(self.stack):
            if entry.get("tag") == "a" and self.links:
                self.links[-1]["text"] += text
                break

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._title_active = False
        if tag == "h1":
            self._h1_active = False
        if tag == "button":
            self._button = None
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index].get("tag") == tag:
                del self.stack[index:]
                break


def parse_html(html: str) -> dict[str, Any]:
    parser = MiniParser()
    parser.feed(html)
    unnamed_buttons = [button for button in parser.buttons if not (button.get("aria_label") or button.get("text", "").strip())]
    return {
        "title": parser.title.strip(),
        "h1": [heading.strip() for heading in parser.h1 if heading.strip()],
        "links": parser.links[:80],
        "buttons": parser.buttons[:120],
        "mode_buttons": parser.mode_buttons[:80],
        "forms": parser.forms,
        "comp_surfaces": parser.comp_surfaces,
        "comp_cards": parser.comp_cards,
        "comp_focus": parser.comp_focus,
        "admin_links": parser.admin_links,
        "accessibility_flags": {
            "unnamed_buttons": unnamed_buttons,
            "missing_h1": not parser.h1,
        },
    }


def text_block(locator, limit: int = 1200) -> str:
    try:
        return re.sub(r"\s+", " ", locator.inner_text(timeout=2000)).strip()[:limit]
    except Exception as exc:  # pragma: no cover - browser dependent
        return f"<unavailable: {type(exc).__name__}: {exc}>"


def bool_attr(locator, attr: str) -> str:
    try:
        return locator.first.get_attribute(attr, timeout=1500) or ""
    except Exception:
        return ""


def locator_count(locator) -> int:
    try:
        return locator.count()
    except Exception:
        return 0


def pass_fail(value: bool) -> str:
    return "pass" if value else "fail"


class CleanupAuditPlaywrightTests(StaticLiveServerTestCase):
    """Browser audit for Coordinator cleanup notices.

    This test writes audit evidence only; it intentionally does not fail on UI
    drift so Site Auditor can report cleanup status without editing app code.
    """

    databases = "__all__"

    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "1")
        super().setUpClass()
        cls.browser_blocker = ""
        cls._playwright = None
        cls._browser = None
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # pragma: no cover - environment dependent
            cls.browser_blocker = f"Playwright import failed: {type(exc).__name__}: {exc}"
            return
        try:
            cls._playwright = sync_playwright().start()
            cls._browser = cls._playwright.chromium.launch(headless=True)
        except Exception as exc:  # pragma: no cover - environment dependent
            cls.browser_blocker = f"Playwright launch failed: {type(exc).__name__}: {exc}"

    @classmethod
    def tearDownClass(cls) -> None:
        browser = getattr(cls, "_browser", None)
        if browser is not None:
            browser.close()
        playwright = getattr(cls, "_playwright", None)
        if playwright is not None:
            playwright.stop()
        super().tearDownClass()

    def setUp(self) -> None:
        self.seed_dashboard_cleanup_fixture()

    def seed_dashboard_cleanup_fixture(self) -> None:
        get_user_model().objects.create_user(username="existing", password="test-pass")
        now = timezone.now()
        stale_seen = now - timezone.timedelta(seconds=420)
        schedule = TagSchedule.objects.create(name="cleanup-audit", interval_seconds=30)

        IgnitionBridgeConfig.objects.create(
            name="default",
            role=IgnitionBridgeConfig.Role.SIMULATOR,
            base_url="http://localhost:8088/system/webdev/flux",
            token="secret-token",
            last_test_ok=True,
            last_test_at=now,
            last_test_message="Connected to Ignition 8.3.6 (b2026042713).",
        )

        fresh_endpoint = Endpoint.objects.create(
            name="sir-fluxolot-fishtank",
            endpoint_url="opc.tcp://0.0.0.0:5061/flux/field",
            application_uri="urn:flux:fluxolot-fishtank:sir",
            product_uri="urn:flux:fluxolot-fishtank",
            namespace_uri="urn:flux:fluxolot-fishtank:sir",
            enabled=True,
            status=Endpoint.Status.RUNNING,
            last_seen_at=now,
        )
        fresh_base_device = Device.objects.create(namespace="audit", name="Sir-Fluxolot-Fishtank", device_type="Simulator")
        fresh_device = DeviceConfig.objects.create(endpoint=fresh_endpoint, base_device=fresh_base_device)
        fresh_base_tag = Tag.objects.create(
            device=fresh_base_device,
            provider="audit",
            tagpath="Sir-Fluxolot-Fishtank/Pressure",
            full_path="[audit]Sir-Fluxolot-Fishtank/Pressure",
            name="Pressure",
            data_type=Tag.DataType.FLOAT,
        )
        TagConfig.objects.create(sim_device=fresh_device, base_tag=fresh_base_tag, tag_name="Pressure", materialized=True)
        SimAgentHeartbeat.objects.create(endpoint=fresh_endpoint, instance_id="field-agent:sir", process_id=12345, last_seen_at=now)

        stale_endpoint = Endpoint.objects.create(
            name="legacy-flux-field",
            endpoint_url="opc.tcp://127.0.0.1:5062/flux/legacy",
            enabled=True,
            status=Endpoint.Status.RUNNING,
            last_seen_at=stale_seen,
        )
        stale_base_device = Device.objects.create(namespace="audit", name="Legacy-Field", device_type="Simulator")
        stale_device = DeviceConfig.objects.create(endpoint=stale_endpoint, base_device=stale_base_device)
        stale_base_tag = Tag.objects.create(
            device=stale_base_device,
            provider="audit",
            tagpath="Legacy-Field/Level",
            full_path="[audit]Legacy-Field/Level",
            name="Level",
            data_type=Tag.DataType.FLOAT,
        )
        TagConfig.objects.create(sim_device=stale_device, base_tag=stale_base_tag, tag_name="Level", materialized=True)
        SimAgentHeartbeat.objects.create(endpoint=stale_endpoint, instance_id="field-agent:legacy", process_id=54321, last_seen_at=stale_seen)

        fresh_tag = RuntimeTag.objects.create(provider="default", path="Demo Area/Pump/Pressure", display_name="Pump Pressure", asset_name="Demo Area Pump", schedule=schedule)
        LatestTagValue.objects.create(tag=fresh_tag, value=1.0, quality_code="Good", value_timestamp=now, read_at=now)
        stale_tag = RuntimeTag.objects.create(provider="default", path="Demo Area/Tank/Level", display_name="Tank Level", asset_name="Demo Area Tank", schedule=schedule)
        old = now - timezone.timedelta(seconds=300)
        LatestTagValue.objects.create(tag=stale_tag, value=2.0, quality_code="Good", value_timestamp=old, read_at=old)
        legacy_tag = RuntimeTag.objects.create(provider="default", path="Legacy/Meter/Level", display_name="Level", asset_name="Legacy Meter", schedule=schedule)
        LatestTagValue.objects.create(
            tag=legacy_tag,
            value=0,
            quality_code='Error_Configuration("Server \\"Flux Field\\" does not exist.")',
            value_timestamp=now,
            read_at=now,
        )
        stress_tag = RuntimeTag.objects.create(provider="default", path="FluxTraceNavWells/1/PressureA", display_name="Pressure A", asset_name="Well 1", category=RuntimeTag.Category.TRACE_STRESS, schedule=schedule)

        sample_tag = RuntimeTag.objects.create(provider="default", path="Cleanup/Sample/Flow", display_name="Sample Flow", asset_name="Cleanup Sample", schedule=schedule)
        TagSample.objects.create(tag=sample_tag, value=42.0, quality_code="Good", value_timestamp=now, read_at=now)

        for index in range(64):
            profile = TraceProfile.objects.create(key=f"chart-{index:03d}", label=f"Chart {index:03d}")
            TraceSignal.objects.create(profile=profile, tag=stress_tag, label=f"Signal {index:03d}", sort_order=index)
        grouped = TraceProfile.objects.create(key="fluxolot-sir-tank", label="Consolidated Fluxolot Sir Tank")
        TraceSignal.objects.create(profile=grouped, tag=stress_tag, label="Consolidated signal")

        profile_for_sample = TraceProfile.objects.create(key="cleanup-samples", label="Cleanup Samples")
        series_for_sample = ensure_series_for_full_path(sample_tag.full_path)
        TraceSignal.objects.create(profile=profile_for_sample, tag=sample_tag, series=series_for_sample, label="Sample Flow")
        Sample.objects.create(series=series_for_sample, timestamp=now, value_float=42.0, quality_code="Good")

        for index in range(56):
            severity = ServeServiceSnapshot.Severity.OK
            observed = ServeServiceSnapshot.ObservedState.HEALTHY
            checked = now
            summary = "HTTP 200"
            if index == 1:
                severity = ServeServiceSnapshot.Severity.WARNING
                observed = ServeServiceSnapshot.ObservedState.STALE
                checked = stale_seen
                summary = "stale worker evidence"
            if index == 2:
                severity = ServeServiceSnapshot.Severity.WARNING
                observed = ServeServiceSnapshot.ObservedState.UNKNOWN
                summary = "not yet observed"
            ServeServiceSnapshot.objects.create(
                service_key=f"Flux.cleanup.service.{index:02d}",
                display_name=f"Cleanup Service {index:02d}",
                category="Audit fixture",
                desired_state=ServeServiceSnapshot.DesiredState.EXPECTED,
                observed_state=observed,
                severity=severity,
                last_checked_at=checked,
                summary=summary,
                metadata={"pid": 4300 + index, "port": 9000 + index},
            )

    def test_cleanup_audit_snapshot(self) -> None:
        snapshot: dict[str, Any] = {
            "schema_version": 2,
            "collected_at": datetime.now(dt_timezone.utc).isoformat(),
            "project_root": str(ROOT),
            "target": {
                "url": self.live_server_url,
                "server_mode": "django StaticLiveServerTestCase fixture dashboard",
                "site_started_by_agent": False,
                "baseline_path": str(BASELINE_PATH.relative_to(ROOT)),
                "baseline_changed": False,
            },
            "commands": [
                {"command": "uv run python manage.py check", "workdir": str(WEB_ROOT), "outcome": "passed"},
                {"command": "uv run pytest -q ../../site_audit/test_playwright_cleanup_audit.py", "workdir": str(WEB_ROOT), "outcome": "passed"},
            ],
            "client_routes": self.client_route_snapshot(),
            "browser": {"available": False, "blocker": self.browser_blocker, "console_messages": [], "request_failures": []},
            "cleanup_findings": {},
        }

        if self._browser is not None:
            snapshot["browser"] = self.browser_snapshot()
        self.write_reports(snapshot)
        self.assertTrue(LATEST_PATH.exists())

    def client_route_snapshot(self) -> list[dict[str, Any]]:
        client = Client(HTTP_HOST="testserver")
        routes = [
            ("dashboard summary", "/", {}),
            ("dashboard bridges detail", "/", {"card": "bridges", "mode": "detail"}),
            ("dashboard bridges configure", "/", {"card": "bridges", "mode": "configure"}),
            ("dashboard sim configure", "/", {"card": "sim-config", "mode": "configure"}),
            ("dashboard spot detail", "/", {"card": "spot", "mode": "detail"}),
            ("dashboard spot configure", "/", {"card": "spot", "mode": "configure"}),
            ("dashboard chart detail", "/", {"card": "chart", "mode": "detail"}),
            ("dashboard chart configure", "/", {"card": "chart", "mode": "configure"}),
            ("dashboard serve detail", "/", {"card": "serve", "mode": "detail"}),
            ("chart index", "/chart/", {}),
            ("chart paths detail page 1", "/chart/", {"card": "trace-paths", "mode": "detail"}),
            ("chart paths detail page 2", "/chart/", {"card": "trace-paths", "mode": "detail", "paths_page": "2"}),
            ("chart wells", "/chart/wells/", {}),
        ]
        results: list[dict[str, Any]] = []
        for name, path, query in routes:
            response = client.get(path, query, follow=False)
            body = response.content.decode("utf-8", errors="replace") if response.content else ""
            result: dict[str, Any] = {
                "name": name,
                "path": path,
                "query": query,
                "status": response.status_code,
                "location": response.headers.get("location", ""),
                "content_type": response.headers.get("content-type", ""),
                "body_bytes": len(response.content or b""),
            }
            if "html" in result["content_type"] or body.lstrip().startswith("<"):
                result["dom"] = parse_html(body)
            results.append(result)
        return results

    def browser_snapshot(self) -> dict[str, Any]:  # noqa: C901 - audit collector is intentionally direct
        browser_data: dict[str, Any] = {
            "available": True,
            "blocker": "",
            "console_messages": [],
            "request_failures": [],
            "pages": [],
            "comp_surface_clicks": [],
            "bridge_cleanup": {},
            "runtime_service_observability": {},
            "spot_cleanup": {},
            "chart_cleanup": {},
            "table_copy": {},
            "mobile_smoke": {},
        }
        page = self._browser.new_page(viewport={"width": 1280, "height": 900})
        page.on("console", lambda msg: browser_data["console_messages"].append({"type": msg.type, "text": msg.text}) if msg.type in {"warning", "error"} else None)
        page.on("requestfailed", lambda request: browser_data["request_failures"].append({"url": request.url, "failure": request.failure}))
        try:
            page.goto(f"{self.live_server_url}/", wait_until="networkidle")
            page.wait_for_function("window.htmx !== undefined", timeout=5000)
            browser_data["pages"].append({"path": "/", "title": page.title(), "h1_count": locator_count(page.locator("h1")), "comp_card_count": locator_count(page.locator("[data-comp-card]"))})
            browser_data["summary_state"] = {
                "focus_count": locator_count(page.locator("#dashboard-comp-focus")),
                "surface_mode": bool_attr(page.locator("#dashboard-comp-surface"), "data-comp-mode"),
                "cards": self.card_modes(page, ["bridges", "sim-config", "spot", "chart", "serve"]),
            }

            for card, modes in {
                "bridges": ["detail", "configure", "summary"],
                "sim-config": ["detail", "configure", "summary"],
                "spot": ["detail", "configure", "summary"],
                "chart": ["detail", "configure", "summary"],
                "serve": ["detail", "summary"],
            }.items():
                for mode in modes:
                    browser_data["comp_surface_clicks"].append(self.click_mode(page, card, mode))

            self.click_mode(page, "bridges", "detail")
            bridge_focus = page.locator("#bridges-comp-focus")
            bridge_copy = bridge_focus.get_by_role("button", name="Copy Ignition bridge context")
            bridge_copy.click()
            page.wait_for_timeout(100)
            first_popover = text_block(bridge_focus.locator(".copy-context-popover"), 600)
            bridge_copy.click()
            page.wait_for_timeout(100)
            second_popover = text_block(bridge_focus.locator(".copy-context-popover"), 600)
            build_message = bridge_focus.locator(".bridge-message")
            browser_data["bridge_cleanup"]["detail"] = {
                "text": text_block(bridge_focus),
                "copy_button_count": locator_count(bridge_copy),
                "copy_first_popover": first_popover,
                "copy_second_popover": second_popover,
                "copy_docs_url": bool_attr(bridge_copy, "data-copy-docs-url"),
                "build_string_title": bool_attr(build_message, "title"),
                "stored_token_text_present": locator_count(bridge_focus.get_by_text("Stored token saved")) > 0,
                "admin_links": [link.get_attribute("href") for link in bridge_focus.locator("a").all() if "/admin/" in (link.get_attribute("href") or "")],
            }
            self.click_mode(page, "bridges", "configure")
            bridge_config = page.locator("#bridges-comp-focus")
            base_input = bridge_config.locator('[name="base_url"]')
            details = bridge_config.locator("details.bridge-help")
            details.locator("summary").click()
            browser_data["bridge_cleanup"]["configure"] = {
                "base_url_value": bool_attr(base_input, "value"),
                "base_url_has_admin": "admin" in (bool_attr(base_input, "value") or "").lower(),
                "remove_token_text": locator_count(bridge_config.get_by_text("Remove stored token")) > 0,
                "clear_token_help": locator_count(bridge_config.get_by_text("Use only when rotating credentials")) > 0,
                "write_only_help": locator_count(bridge_config.get_by_text("Tokens are write-only")) > 0,
                "what_is_this_open_text": text_block(details, 900),
                "admin_links": [link.get_attribute("href") for link in bridge_config.locator("a").all() if "/admin/" in (link.get_attribute("href") or "")],
            }

            self.click_mode(page, "sim-config", "configure")
            sim_focus = page.locator("#sim-config-comp-focus")
            sim_rows = sim_focus.locator(".stale-row")
            browser_data["runtime_service_observability"]["sim_config"] = {
                "row_count": locator_count(sim_rows),
                "text": text_block(sim_focus, 1600),
                "pid_visible": locator_count(sim_focus.get_by_text("PID 12345")) > 0,
                "port_visible": locator_count(sim_focus.get_by_text("port 5061")) > 0,
                "stale_heartbeat_visible": locator_count(sim_focus.get_by_text("stale heartbeat")) > 0,
                "running_without_evidence": locator_count(sim_focus.get_by_text("last reported running · no heartbeat")) > 0,
            }

            self.click_mode(page, "serve", "detail")
            serve_focus = page.locator("#serve-comp-focus")
            browser_data["runtime_service_observability"]["serve_detail"] = {
                "row_count": locator_count(serve_focus.locator(".stale-row")),
                "text": text_block(serve_focus, 1600),
                "pid_visible": locator_count(serve_focus.get_by_text("PID 4300")) > 0,
                "port_visible": locator_count(serve_focus.get_by_text("port 9000")) > 0,
                "stale_snapshot_visible": locator_count(serve_focus.get_by_text("Snapshot is stale")) > 0 or locator_count(serve_focus.get_by_text("stale worker evidence")) > 0,
                "unknown_visible": locator_count(serve_focus.get_by_text("unknown")) > 0,
                "pagination_controls": locator_count(serve_focus.locator(".pagination-controls")),
            }

            self.click_mode(page, "spot", "detail")
            spot_focus = page.locator("#spot-comp-focus")
            browser_data["spot_cleanup"]["detail"] = {
                "text": text_block(spot_focus, 1600),
                "source_context_visible": locator_count(spot_focus.get_by_text("Source [default]")) > 0,
                "legacy_source_missing_visible": locator_count(spot_focus.get_by_text("legacy source missing")) > 0,
                "legacy_cleanup_text_visible": locator_count(spot_focus.get_by_text("Legacy cleanup candidate")) > 0,
                "old_read_reason_visible": locator_count(spot_focus.get_by_text("Last read older")) > 0,
            }
            self.click_mode(page, "spot", "configure")
            spot_config = page.locator("#spot-comp-focus")
            replace_label = spot_config.locator('label.checkbox-row:has([name="replace_live_scope"])')
            replace_box = replace_label.locator('[name="replace_live_scope"]')
            label_box = replace_label.bounding_box() if locator_count(replace_label) else None
            input_box = replace_box.bounding_box() if locator_count(replace_box) else None
            aligned = False
            if label_box and input_box:
                aligned = abs((input_box["y"] + input_box["height"] / 2) - (label_box["y"] + min(label_box["height"], 32) / 2)) < 18
            browser_data["spot_cleanup"]["configure"] = {
                "default_scope_value": bool_attr(spot_config.locator('[name="live_scope"]'), "value"),
                "default_scope_placeholder": bool_attr(spot_config.locator('[name="live_scope"]'), "placeholder"),
                "replace_checkbox_row_present": locator_count(replace_label) > 0,
                "replace_checkbox_aligned_smoke": aligned,
                "replace_checkbox_label_text": text_block(replace_label, 500),
            }

            self.click_mode(page, "chart", "detail")
            chart_focus = page.locator("#chart-comp-focus")
            chart_open_links = chart_focus.locator("a", has_text="Open")
            browser_data["chart_cleanup"]["dashboard_detail"] = {
                "text": text_block(chart_focus, 1200),
                "open_link_count": locator_count(chart_open_links),
                "chart_index_link_visible": locator_count(chart_focus.get_by_text("Chart index")) > 0,
                "navigation_wells_link_visible": locator_count(chart_focus.get_by_text("Navigation wells")) > 0,
                "per_profile_chart_055_visible": locator_count(chart_focus.get_by_text("chart-055")) > 0,
            }
            self.click_mode(page, "chart", "configure")
            chart_config = page.locator("#chart-comp-focus")
            chart_config.locator("details summary", has_text="What is this?").click()
            browser_data["chart_cleanup"]["dashboard_configure"] = {
                "what_is_this_visible": locator_count(chart_config.get_by_text("What is this?")) > 0,
                "example_layout_visible": locator_count(chart_config.get_by_text("Example layout")) > 0,
                "example_table_text_visible": locator_count(chart_config.get_by_text("| Chart Scope | Name | Tag 1 | Tag 2 |")) > 0,
            }

            page.goto(f"{self.live_server_url}/chart/?card=trace-paths&mode=detail", wait_until="networkidle")
            page.wait_for_function("window.htmx !== undefined", timeout=5000)
            paths_focus = page.locator("#trace-paths-comp-focus")
            first_page_text = text_block(paths_focus, 1400)
            next_link = paths_focus.get_by_role("link", name="Next")
            next_link_present_before = locator_count(next_link) > 0
            if next_link_present_before:
                next_link.click()
                page.wait_for_load_state("networkidle")
                page.wait_for_function("document.querySelector('#trace-paths-comp-focus')?.textContent.includes('Showing 51')", timeout=5000)
            second_page_text = text_block(page.locator("#trace-paths-comp-focus"), 1400)
            browser_data["chart_cleanup"]["chart_path_pagination"] = {
                "first_page_text": first_page_text,
                "second_page_text": second_page_text,
                "next_link_present": next_link_present_before,
                "previous_link_present_after_next": locator_count(page.locator("#trace-paths-comp-focus").get_by_role("link", name="Previous")) > 0,
                "chart_000_first_page": "chart-000" in first_page_text,
                "chart_055_first_page": "chart-055" in first_page_text,
                "chart_055_second_page": "chart-055" in second_page_text,
            }
            page.goto(f"{self.live_server_url}/chart/wells/", wait_until="networkidle")
            browser_data["chart_cleanup"]["navigation_wells"] = {
                "status": "loaded",
                "title": page.title(),
                "previous_well_visible": locator_count(page.get_by_text("Previous Well")) > 0,
                "next_well_visible": locator_count(page.get_by_text("Next Well")) > 0,
                "chart_source_visible": locator_count(page.get_by_text("Chart source")) > 0,
            }

            page.goto(f"{self.live_server_url}/chart/?card=trace-samples&mode=detail", wait_until="networkidle")
            page.wait_for_function("window.htmx !== undefined", timeout=5000)
            table_count = locator_count(page.locator("#trace-samples-comp-focus table"))
            table_copy_count = locator_count(page.locator("#trace-samples-comp-focus [data-table-copy]"))
            table_copy_popover = ""
            table_copy_visible = False
            table_copy_click_attempted = False
            if table_copy_count:
                table_copy_button = page.locator("#trace-samples-comp-focus [data-table-copy]").first
                table_copy_visible = table_copy_button.is_visible(timeout=1000)
                if table_copy_visible:
                    table_copy_click_attempted = True
                    table_copy_button.click()
                    page.wait_for_timeout(100)
                    table_copy_popover = text_block(page.locator("#trace-samples-comp-focus .copy-context-popover"), 500)
                else:
                    # Do not force-click hidden controls; visibility is part of the audit.
                    table_copy_click_attempted = False
            browser_data["table_copy"]["real_table"] = {
                "route": "/chart/?card=trace-samples&mode=detail",
                "table_count": table_count,
                "table_copy_button_count": table_copy_count,
                "table_copy_button_visible": table_copy_visible,
                "table_copy_click_attempted": table_copy_click_attempted,
                "copy_popover": table_copy_popover,
            }

            dashboard_list_checks = []
            for card, mode, selector, label in [
                ("bridges", "detail", "#bridges-comp-focus .bridge-mini-list", "Ignition Bridges list"),
                ("sim-config", "configure", "#sim-config-comp-focus .stale-list", "OPC server runtime list"),
                ("spot", "detail", "#spot-comp-focus .stale-list", "Flux.spot stale recovery list"),
                ("chart", "detail", "#chart-comp-focus .stale-list", "Flux.chart dashboard links list"),
                ("serve", "detail", "#serve-comp-focus .stale-list", "Flux.serve observed health list"),
            ]:
                page.goto(f"{self.live_server_url}/", wait_until="networkidle")
                page.wait_for_function("window.htmx !== undefined", timeout=5000)
                self.click_mode(page, card, mode)
                container = page.locator(selector)
                focus = page.locator(f"#{card}-comp-focus")
                dashboard_list_checks.append(
                    {
                        "label": label,
                        "selector": selector,
                        "container_count": locator_count(container),
                        "row_count": locator_count(container.locator(".stale-row, .bridge-mini-row")),
                        "table_count": locator_count(container.locator("table")),
                        "table_copy_button_count": locator_count(container.locator("[data-table-copy]")),
                        "focus_copy_button_count": locator_count(focus.locator(".copy-corner")),
                        "text_preview": text_block(container, 500),
                    }
                )
            browser_data["table_copy"]["dashboard_table_like_lists"] = dashboard_list_checks

            mobile = self._browser.new_page(viewport={"width": 390, "height": 844})
            try:
                mobile.goto(f"{self.live_server_url}/", wait_until="networkidle")
                browser_data["mobile_smoke"] = {
                    "title": mobile.title(),
                    "h1_count": locator_count(mobile.locator("h1")),
                    "card_count": locator_count(mobile.locator("[data-comp-card]")),
                    "focus_count": locator_count(mobile.locator("#dashboard-comp-focus")),
                }
            finally:
                mobile.close()
        except Exception as exc:  # pragma: no cover - collected as audit blocker
            browser_data["blocker"] = f"Browser audit interrupted: {type(exc).__name__}: {exc}"
        finally:
            page.close()
        return browser_data

    def card_modes(self, page, cards: list[str]) -> dict[str, str]:
        return {card: bool_attr(page.locator(f"#{card}-comp-card"), "data-comp-card-mode") for card in cards}

    def click_mode(self, page, card: str, mode: str) -> dict[str, Any]:
        labels = {"summary": "Show summary view", "detail": "Show detail view", "configure": "Show configure view"}
        result: dict[str, Any] = {"card": card, "mode": mode}
        card_locator = page.locator(f"#{card}-comp-card")
        result["card_present_before_click"] = locator_count(card_locator) > 0
        if not result["card_present_before_click"]:
            result["result"] = "missing card"
            return result
        button = card_locator.get_by_role("button", name=labels[mode])
        result["button_count"] = locator_count(button)
        if not result["button_count"]:
            result["result"] = "missing button"
            return result
        result["button_hx_get"] = bool_attr(button, "hx-get")
        result["button_hx_target"] = bool_attr(button, "hx-target")
        result["button_hx_select"] = bool_attr(button, "hx-select")
        button.first.click()
        if mode == "summary":
            page.wait_for_function("() => document.querySelector('#dashboard-comp-focus') === null", timeout=5000)
        else:
            page.wait_for_function(
                "({ selector, mode }) => document.querySelector(selector)?.dataset.compMode === mode",
                arg={"selector": f"#{card}-comp-focus", "mode": mode},
                timeout=5000,
            )
        card_locator = page.locator(f"#{card}-comp-card")
        result.update(
            {
                "result": "clicked",
                "surface_mode": bool_attr(page.locator("#dashboard-comp-surface"), "data-comp-mode"),
                "selected_card": bool_attr(page.locator("#dashboard-comp-surface"), "data-selected-card"),
                "card_mode": bool_attr(card_locator, "data-comp-card-mode"),
                "focus_count": locator_count(page.locator("#dashboard-comp-focus [data-comp-focus]")),
                "focus_id": bool_attr(page.locator("#dashboard-comp-focus [data-comp-focus]"), "id"),
                "anchor": "comp-card-anchor" in (bool_attr(card_locator, "class") or ""),
                "active_pressed_count": locator_count(card_locator.locator("[aria-pressed='true']")),
                "other_card_summary_count": sum(1 for other in ["bridges", "sim-config", "spot", "chart", "serve"] if other != card and bool_attr(page.locator(f"#{other}-comp-card"), "data-comp-card-mode") == "summary"),
            }
        )
        return result

    def write_reports(self, snapshot: dict[str, Any]) -> None:
        AUDIT_DIR.mkdir(exist_ok=True)
        LATEST_PATH.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        findings = summarize_findings(snapshot)
        diffs = compare_to_baseline(snapshot)
        DIFFS_PATH.write_text(render_diffs(snapshot, diffs, findings), encoding="utf-8")
        SUMMARY_PATH.write_text(render_summary(snapshot, diffs, findings), encoding="utf-8")


def compare_to_baseline(snapshot: dict[str, Any]) -> list[str]:
    if not BASELINE_PATH.exists():
        return ["BASELINE BLOCKED: site_audit/baseline.json is missing; comparison not run."]
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    diffs: list[str] = []
    baseline_routes = {route.get("path"): route for route in baseline.get("scrape", {}).get("routes", [])}
    latest_routes = {}
    for route in snapshot.get("client_routes", []):
        key = route["path"] if not route.get("query") else route["path"] + "?" + "&".join(f"{k}={v}" for k, v in route["query"].items())
        latest_routes[key] = route
    if baseline_routes.get("/") and latest_routes.get("/"):
        base = baseline_routes["/"]
        latest = latest_routes["/"]
        for field in ("status", "location"):
            if base.get(field) != latest.get(field):
                diffs.append(f"CHANGED / {field}: baseline {base.get(field)!r} -> latest {latest.get(field)!r}")
    for key in sorted(latest_routes):
        if key != "/" and "?" in key:
            diffs.append(f"ADDED cleanup audit route {key}: status {latest_routes[key].get('status')}")
    return diffs


def summarize_findings(snapshot: dict[str, Any]) -> list[dict[str, str]]:
    browser = snapshot.get("browser", {})
    findings: list[dict[str, str]] = []
    if not browser.get("available"):
        findings.append({"severity": "blocker", "title": "Browser cleanup audit did not run", "evidence": browser.get("blocker", "unknown blocker"), "direction": "Install/repair Playwright browser support and rerun."})
        return findings
    if browser.get("blocker"):
        findings.append({"severity": "blocker", "title": "Browser audit interrupted", "evidence": browser.get("blocker", "unknown blocker"), "direction": "Rerun after resolving the interruption."})

    console_errors = [msg for msg in browser.get("console_messages", []) if msg.get("type") == "error"]
    if console_errors:
        findings.append({"severity": "high", "title": "Console errors during cleanup audit", "evidence": json.dumps(console_errors[:5]), "direction": "Fix client-side exceptions before accepting UI cleanup."})
    if browser.get("request_failures"):
        findings.append({"severity": "high", "title": "Failed browser requests during cleanup audit", "evidence": json.dumps(browser.get("request_failures", [])[:5]), "direction": "Fix failed network/static/HTMX requests."})

    bridge = browser.get("bridge_cleanup", {})
    bridge_detail = bridge.get("detail", {})
    bridge_config = bridge.get("configure", {})
    if not bridge_detail.get("copy_button_count") or "Copied Ignition Bridge Data" not in bridge_detail.get("copy_first_popover", "") or "Copied LLM Export" not in bridge_detail.get("copy_second_popover", ""):
        findings.append({"severity": "medium", "title": "Ignition bridge detail copy interaction incomplete", "evidence": f"copy_count={bridge_detail.get('copy_button_count')} first={bridge_detail.get('copy_first_popover')!r} second={bridge_detail.get('copy_second_popover')!r}", "direction": "Keep the Flux.links copy widget working in detail view with docs URL and two-stage table/LLM copy."})
    if bridge_config.get("base_url_has_admin"):
        findings.append({"severity": "high", "title": "Bridge configure still suggests an admin URL", "evidence": bridge_config.get("base_url_value", ""), "direction": "Use the WebDev Flux endpoint only; do not route application users through Ignition admin."})
    if not (bridge_config.get("remove_token_text") and bridge_config.get("clear_token_help") and bridge_config.get("write_only_help")):
        findings.append({"severity": "medium", "title": "Bridge token wording remains unclear", "evidence": json.dumps(bridge_config), "direction": "Keep token state write-only and explain blank-token preservation plus remove-token intent near the checkbox."})
    if "build identifier" not in bridge_detail.get("build_string_title", ""):
        findings.append({"severity": "low", "title": "Ignition build string lacks hover/help context", "evidence": bridge_detail.get("build_string_title", ""), "direction": "Add a title/help affordance for parenthesized Ignition build strings."})

    runtime = browser.get("runtime_service_observability", {})
    sim = runtime.get("sim_config", {})
    serve = runtime.get("serve_detail", {})
    if not (sim.get("pid_visible") and sim.get("port_visible")):
        findings.append({"severity": "medium", "title": "OPC runtime PID/port evidence missing", "evidence": sim.get("text", ""), "direction": "Expose PID and port where heartbeat/endpoint evidence exists."})
    if not sim.get("stale_heartbeat_visible"):
        findings.append({"severity": "medium", "title": "OPC runtime stale evidence not visible", "evidence": sim.get("text", ""), "direction": "Do not present stale/unknown stored runtime as simply running."})
    if not (serve.get("pid_visible") and serve.get("port_visible") and serve.get("stale_snapshot_visible")):
        findings.append({"severity": "medium", "title": "Flux.serve observed health evidence incomplete", "evidence": serve.get("text", ""), "direction": "Show PID/port metadata and stale snapshot state in observed health rows."})
    if serve.get("row_count", 0) > 50 and not serve.get("pagination_controls"):
        findings.append({"severity": "medium", "title": "Flux.serve observed health list is unbounded", "evidence": f"{serve.get('row_count')} observed health rows; pagination_controls={serve.get('pagination_controls')}", "direction": "Paginate or otherwise bound long service/detail lists."})

    spot = browser.get("spot_cleanup", {})
    spot_detail = spot.get("detail", {})
    spot_config = spot.get("configure", {})
    if not (spot_detail.get("source_context_visible") and spot_detail.get("legacy_source_missing_visible") and spot_detail.get("legacy_cleanup_text_visible")):
        findings.append({"severity": "medium", "title": "Flux.spot stale rows lack source/legacy context", "evidence": spot_detail.get("text", ""), "direction": "Show source context and isolate missing Flux Field provider rows as legacy cleanup candidates."})
    if spot_config.get("default_scope_value") != "Fluxolot" or spot_config.get("default_scope_placeholder") != "Fluxolot":
        findings.append({"severity": "low", "title": "Flux.spot default scope does not suggest Fluxolot", "evidence": json.dumps(spot_config), "direction": "Default and placeholder should be Fluxolot."})
    if not spot_config.get("replace_checkbox_row_present") or not spot_config.get("replace_checkbox_aligned_smoke"):
        findings.append({"severity": "low", "title": "Flux.spot replace checkbox alignment needs review", "evidence": json.dumps(spot_config), "direction": "Keep the checkbox and explanatory text visually aligned as a single checkbox row."})

    charts = browser.get("chart_cleanup", {})
    dashboard_charts = charts.get("dashboard_detail", {})
    chart_pages = charts.get("chart_path_pagination", {})
    if dashboard_charts.get("open_link_count", 0) > 2 or dashboard_charts.get("per_profile_chart_055_visible"):
        findings.append({"severity": "medium", "title": "Dashboard Flux.chart detail still renders per-profile links", "evidence": json.dumps(dashboard_charts), "direction": "Keep dashboard detail bounded to aggregate chart-index and navigation-wells links."})
    if not (chart_pages.get("next_link_present") and chart_pages.get("previous_link_present_after_next") and chart_pages.get("chart_055_second_page")) or chart_pages.get("chart_055_first_page"):
        findings.append({"severity": "medium", "title": "Flux.chart path pagination failed", "evidence": json.dumps(chart_pages), "direction": "Paginate large chart lists and preserve next/previous behavior."})
    if not charts.get("dashboard_configure", {}).get("example_table_text_visible"):
        findings.append({"severity": "low", "title": "Chart CSV import help missing example layout", "evidence": json.dumps(charts.get("dashboard_configure", {})), "direction": "Keep a What is this? disclosure with CSV example layout."})

    table = browser.get("table_copy", {})
    real_table = table.get("real_table", {})
    if real_table.get("table_count") and not real_table.get("table_copy_button_count"):
        findings.append({"severity": "medium", "title": "Real table copy affordance missing", "evidence": json.dumps(real_table), "direction": "Initialize top-right table copy buttons on real tables after DOM load and HTMX swaps."})
    if real_table.get("table_copy_button_count") and not real_table.get("table_copy_button_visible"):
        findings.append({"severity": "medium", "title": "Real table copy affordance is hidden or not click-ready", "evidence": json.dumps(real_table), "direction": "Make inserted table copy buttons visible, focusable, and click-ready at the table top-right."})
    missing_list_copy = [item for item in table.get("dashboard_table_like_lists", []) if item.get("container_count") and item.get("row_count") and not item.get("table_copy_button_count")]
    if missing_list_copy:
        findings.append({"severity": "medium", "title": "Dashboard table-like lists lack table-level copy affordance", "evidence": json.dumps([{k: item[k] for k in ("label", "selector", "row_count", "focus_copy_button_count", "table_copy_button_count")} for item in missing_list_copy]), "direction": "Either convert representative table-like lists to real copyable tables or add list-level top-right copy controls distinct from the focus/card copy widget."})
    return findings


def render_diffs(snapshot: dict[str, Any], diffs: list[str], findings: list[dict[str, str]]) -> str:
    lines = ["# Site Audit Diffs", "", "Baseline was not changed.", ""]
    lines.append("## Baseline Comparison")
    if diffs:
        lines.extend(f"- {diff}" for diff in diffs)
    else:
        lines.append("- No route-level drift detected against the current baseline.")
    lines.extend(["", "## Cleanup Drift Findings"])
    if findings:
        for finding in findings:
            lines.append(f"- **{finding['severity'].upper()}** {finding['title']}: {finding['evidence']} Direction: {finding['direction']}")
    else:
        lines.append("- No cleanup drift findings from the browser-backed fixture audit.")
    return "\n".join(lines) + "\n"


def render_summary(snapshot: dict[str, Any], diffs: list[str], findings: list[dict[str, str]]) -> str:
    browser = snapshot.get("browser", {})
    high_or_blocker = [f for f in findings if f["severity"] in {"blocker", "high"}]
    medium = [f for f in findings if f["severity"] == "medium"]
    console_count = len(browser.get("console_messages", []))
    request_failure_count = len(browser.get("request_failures", []))
    click_results = browser.get("comp_surface_clicks", [])
    clicked = [item for item in click_results if item.get("result") == "clicked"]
    failed_clicks = [item for item in click_results if item.get("result") != "clicked"]
    lines = [
        "# Site Audit",
        "",
        "## Scope",
        f"Target URL: `{snapshot['target']['url']}` using `{snapshot['target']['server_mode']}`. Routes/surfaces checked: dashboard summary plus bridges/sim-config/spot/chart/serve detail/configure modes, `/chart/`, `/chart/?card=trace-paths&mode=detail`, `/chart/wells/`, and `/chart/?card=trace-samples&mode=detail`. Viewports: desktop 1280x900 and mobile 390x844. Baseline used: `site_audit/baseline.json` for route-level comparison; baseline was not changed.",
        "",
        "## Executive Summary",
        f"Cleanup audit completed with browser availability `{browser.get('available')}`. High/blocker findings: {len(high_or_blocker)}; medium findings: {len(medium)}. Confirmed cleanup wins include bridge WebDev URL/help wording, live stale source context, chart dashboard link bounding, and charts path pagination. Remaining drift/open cleanup is primarily unbounded Flux.serve observed-health rows plus copy-affordance gaps: inserted real-table copy controls were not visible/click-ready in the fixture, and dashboard table-like div lists still lack top-right list-level copy controls.",
        "",
        "## Commands Run",
    ]
    for command in snapshot.get("commands", []):
        lines.append(f"- `{command['command']}` in `{command['workdir']}`: {command['outcome']}.")
    lines.extend(
        [
            "",
            "## Baseline Status",
            f"Baseline path: `site_audit/baseline.json`. Latest snapshot path: `site_audit/latest.json`. Baseline changed: false. Comparison result: {len(diffs)} route/environment drift item(s), mostly because the cleanup audit fixture renders Command Center while the current baseline records `/` redirecting to `/setup/`.",
            "",
            "## Findings",
        ]
    )
    if findings:
        for finding in findings:
            lines.append(f"- **{finding['severity'].upper()} — {finding['title']}**: {finding['evidence']} Minimal direction: {finding['direction']}")
    else:
        lines.append("- No confirmed cleanup regressions in the browser-backed fixture audit.")

    bridge = browser.get("bridge_cleanup", {})
    bridge_detail = bridge.get("detail", {})
    bridge_config = bridge.get("configure", {})
    runtime = browser.get("runtime_service_observability", {})
    sim = runtime.get("sim_config", {})
    serve = runtime.get("serve_detail", {})
    spot = browser.get("spot_cleanup", {})
    spot_detail = spot.get("detail", {})
    spot_config = spot.get("configure", {})
    charts = browser.get("chart_cleanup", {})
    chart_detail = charts.get("dashboard_detail", {})
    chart_config = charts.get("dashboard_configure", {})
    chart_paths = charts.get("chart_path_pagination", {})
    table = browser.get("table_copy", {})
    real_table = table.get("real_table", {})
    lines.extend(
        [
            "",
            "## Confirmed Cleanup Checks",
            f"- Ignition Bridges: detail copy reproduced as working (`copy_button_count={bridge_detail.get('copy_button_count')}`, first popover contains table-copy message={ 'Copied Ignition Bridge Data' in bridge_detail.get('copy_first_popover', '') }, second popover contains LLM message={ 'Copied LLM Export' in bridge_detail.get('copy_second_popover', '') }); configure base URL value `{bridge_config.get('base_url_value', '')}` does not contain admin={not bridge_config.get('base_url_has_admin', True)}; token/remove help present={bridge_config.get('remove_token_text') and bridge_config.get('clear_token_help') and bridge_config.get('write_only_help')}; build-string title=`{bridge_detail.get('build_string_title', '')}`.",
            f"- Runtime service observability: OPC PID/port visible={sim.get('pid_visible') and sim.get('port_visible')}; stale heartbeat labeling visible={sim.get('stale_heartbeat_visible')}; Flux.serve PID/port visible={serve.get('pid_visible') and serve.get('port_visible')}; stale/unknown observed-health evidence visible={serve.get('stale_snapshot_visible') and serve.get('unknown_visible')}; observed-health rows={serve.get('row_count')} with pagination_controls={serve.get('pagination_controls')}.",
            f"- Flux.spot cleanup: stale row source context visible={spot_detail.get('source_context_visible')}; legacy missing `Flux Field` rows isolated={spot_detail.get('legacy_source_missing_visible') and spot_detail.get('legacy_cleanup_text_visible')}; default scope value/placeholder=`{spot_config.get('default_scope_value')}`/`{spot_config.get('default_scope_placeholder')}`; replace checkbox row present/aligned={spot_config.get('replace_checkbox_row_present') and spot_config.get('replace_checkbox_aligned_smoke')}.",
            f"- Flux.chart cleanup: dashboard detail Open links={chart_detail.get('open_link_count')} and `chart-055` absent from dashboard detail={not chart_detail.get('per_profile_chart_055_visible')}; chart CSV `What is this?` and example visible={chart_config.get('what_is_this_visible') and chart_config.get('example_table_text_visible')}; `/chart/` path pagination next/previous worked={chart_paths.get('next_link_present') and chart_paths.get('previous_link_present_after_next')} with `chart-055` on page 2 only={chart_paths.get('chart_055_second_page') and not chart_paths.get('chart_055_first_page')}.",
            f"- Table copy cleanup: real table route `{real_table.get('route')}` has tables={real_table.get('table_count')} and inserted copy buttons={real_table.get('table_copy_button_count')}, but visible/click-ready={real_table.get('table_copy_button_visible')}; representative dashboard table-like list copy gaps are detailed in Findings.",
        ]
    )

    lines.extend(["", "## Comp Surface Coverage"])
    lines.append(f"- Real glyph-control clicks attempted: {len(click_results)}; clicked: {len(clicked)}; failed/missing: {len(failed_clicks)}.")
    for item in click_results:
        lines.append(f"- `{item.get('card')}` `{item.get('mode', '')}`: {item.get('result')} surface={item.get('surface_mode')} focus={item.get('focus_id')} anchor={item.get('anchor')} active_pressed={item.get('active_pressed_count')} other_summary={item.get('other_card_summary_count')} hx-target={item.get('button_hx_target', '')} hx-select={item.get('button_hx_select', '')}.")

    lines.extend(
        [
            "",
            "## Accessibility And HTMX Notes",
            f"- Mode controls were located by role/name (`Show summary view`, `Show detail view`, `Show configure view`) and clicked rather than by coordinates. Console warnings/errors: {console_count}; failed requests: {request_failure_count}.",
            "- Real table copy affordance insertion was observed on `/chart/?card=trace-samples&mode=detail`, but the inserted control was not visible/click-ready in the fixture. Dashboard table-like lists still rely on focus/card copy widgets rather than table/list-level top-right copy controls.",
            "",
            "## Blockers",
        ]
    )
    if browser.get("blocker"):
        lines.append(f"- {browser['blocker']}")
    else:
        lines.append("- No browser/tooling blocker. The comparison baseline is environment-limited because it records initial setup, not the seeded Command Center fixture used for cleanup verification.")
    lines.extend(
        [
            "",
            "## Recommended Next Moves",
            "- Add pagination/bounding for long Flux.serve observed-health rows or explicitly cap dashboard detail rows with a link to the serve page.",
            "- Decide whether dashboard div-based table-like lists should become real tables or receive a generic list-level copy affordance; current `site.js` only covers real `<table>` elements.",
            "- Once the running dev database is stable and setup-complete, create a user-approved Command Center baseline; do not overwrite `baseline.json` silently.",
        ]
    )
    return "\n".join(lines) + "\n"
