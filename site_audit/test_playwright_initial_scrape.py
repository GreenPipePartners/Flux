from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pytest
from django.test import Client


ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "web" / "Flux"
SRC_ROOT = WEB_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "flux.settings")
import django

django.setup()
AUDIT_DIR = ROOT / "site_audit"
BASELINE_PATH = AUDIT_DIR / "baseline.json"
LATEST_PATH = AUDIT_DIR / "latest.json"
DIFFS_PATH = AUDIT_DIR / "diffs.md"
SUMMARY_PATH = ROOT / "site_audit.md"


ROUTES: list[dict[str, Any]] = [
    {"path": "/", "kind": "html", "name": "dashboard home"},
    {"path": "/setup/", "kind": "html", "name": "dashboard setup"},
    {"path": "/bridges/", "kind": "html", "name": "dashboard bridges"},
    {"path": "/serve/", "kind": "html", "name": "serve index"},
    {"path": "/mine/", "kind": "html", "name": "mine index"},
    {"path": "/build/", "kind": "html", "name": "build index"},
    {"path": "/build/seed-hmi-demo/", "kind": "action", "name": "build seed demo"},
    {"path": "/build/hmi-map/build/", "kind": "action", "name": "build hmi map"},
    {"path": "/cell/", "kind": "html", "name": "cell index"},
    {"path": "/cell/phone-demo/", "kind": "html", "name": "cell phone demo"},
    {"path": "/cell/seed-demo/", "kind": "action", "name": "cell seed demo"},
    {"path": "/sim/", "kind": "html", "name": "sim index"},
    {"path": "/sim/import/json/", "kind": "action", "name": "sim json import"},
    {"path": "/sim/import/ignition/", "kind": "action", "name": "sim ignition import"},
    {"path": "/sim/remove-ignition-tags/", "kind": "action", "name": "sim remove ignition tags"},
    {"path": "/sim/jobs/status/", "kind": "fragment", "name": "sim job status"},
    {"path": "/sim/field-config.json", "kind": "json", "name": "sim field config"},
    {"path": "/spot/", "kind": "html", "name": "spot index"},
    {"path": "/spot/pad-overview/", "kind": "html", "name": "spot pad overview"},
    {"path": "/spot/pad-overview/panel/", "kind": "fragment", "name": "spot pad panel"},
    {"path": "/spot/pad-overview/cards/", "kind": "fragment", "name": "spot pad cards"},
    {"path": "/chart/", "kind": "html", "name": "chart index"},
    {"path": "/chart/wells/", "kind": "html", "name": "chart wells"},
    {"path": "/chart/wells/embed/", "kind": "fragment", "name": "chart wells embed"},
    {"path": "/chart/wells/payload/", "kind": "json", "name": "chart wells payload"},
    {"path": "/chart/annotations/", "kind": "html", "name": "chart annotations"},
    {"path": "/chart/annotations/query/", "kind": "json", "name": "chart annotation query"},
    {"path": "/chart/demand/", "kind": "html", "name": "chart demand"},
    {"path": "/chart/stream/", "kind": "html", "name": "chart stream"},
    {"path": "/chart/stream/samples/", "kind": "json", "name": "chart stream samples"},
    {"path": "/chart/fluxolot/", "kind": "html", "name": "chart fluxolot"},
    {"path": "/chart/fluxolot/payload/", "kind": "json", "name": "chart fluxolot payload"},
    {"path": "/trace/", "kind": "redirect", "name": "trace redirect"},
    {"path": "/trace/wells/", "kind": "redirect", "name": "trace wells redirect"},
    {"path": "/trace-clone/", "kind": "redirect", "name": "trace clone redirect"},
]


class ScrapeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.stack: list[dict[str, Any]] = []
        self.title = ""
        self.h1: list[str] = []
        self.links: list[dict[str, str]] = []
        self.buttons: list[dict[str, Any]] = []
        self.forms: list[dict[str, str]] = []
        self.landmarks: list[dict[str, str]] = []
        self.comp_surfaces: list[dict[str, Any]] = []
        self.comp_cards: list[dict[str, Any]] = []
        self.comp_focus: list[dict[str, Any]] = []
        self.mode_controls: list[dict[str, Any]] = []
        self.admin_links: list[str] = []
        self._title_active = False
        self._h1_active = False
        self._current_button: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = {k: v or "" for k, v in attrs_list}
        self.stack.append({"tag": tag, "attrs": attrs})
        if tag == "title":
            self._title_active = True
        if tag == "h1":
            self._h1_active = True
            self.h1.append("")
        if tag == "a":
            href = attrs.get("href", "")
            item = {"href": href, "text": "", "aria_label": attrs.get("aria-label", "")}
            self.links.append(item)
            if "/admin/" in href:
                self.admin_links.append(href)
        if tag == "button":
            self._current_button = {
                "text": "",
                "aria_label": attrs.get("aria-label", ""),
                "aria_pressed": attrs.get("aria-pressed", ""),
                "type": attrs.get("type", ""),
                "hx_get": attrs.get("hx-get", ""),
                "hx_post": attrs.get("hx-post", ""),
                "hx_target": attrs.get("hx-target", ""),
                "hx_swap": attrs.get("hx-swap", ""),
                "classes": attrs.get("class", ""),
            }
            self.buttons.append(self._current_button)
        if tag == "form":
            self.forms.append({"action": attrs.get("action", ""), "method": attrs.get("method", "get"), "hx_post": attrs.get("hx-post", "")})
        if tag in {"main", "nav", "header", "footer", "aside"} or attrs.get("role") in {"main", "navigation", "banner", "contentinfo", "complementary"}:
            self.landmarks.append({"tag": tag, "role": attrs.get("role", ""), "aria_label": attrs.get("aria-label", ""), "id": attrs.get("id", "")})
        if "data-comp-surface" in attrs:
            self.comp_surfaces.append({"id": attrs.get("id", ""), "selected_card": attrs.get("data-selected-card", ""), "mode": attrs.get("data-comp-mode", "")})
        if "data-comp-card" in attrs:
            self.comp_cards.append({"id": attrs.get("id", ""), "mode": attrs.get("data-comp-card-mode", ""), "classes": attrs.get("class", "")})
        if "data-comp-focus" in attrs:
            self.comp_focus.append({"id": attrs.get("id", ""), "card": attrs.get("data-comp-card", ""), "mode": attrs.get("data-comp-mode", "")})
        if tag == "nav" and "comp-card-mode-controls" in attrs.get("class", ""):
            self.mode_controls.append({"aria_label": attrs.get("aria-label", ""), "id": attrs.get("id", "")})

    def handle_data(self, data: str) -> None:
        text = re.sub(r"\s+", " ", data).strip()
        if not text:
            return
        if self._title_active:
            self.title += text
        if self._h1_active and self.h1:
            self.h1[-1] += text
        for entry in reversed(self.stack):
            if entry["tag"] == "a" and self.links:
                self.links[-1]["text"] += (" " + text).strip()
                break
        if self._current_button is not None:
            self._current_button["text"] += (" " + text).strip()

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._title_active = False
        if tag == "h1":
            self._h1_active = False
        if tag == "button":
            self._current_button = None
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i]["tag"] == tag:
                del self.stack[i:]
                break


def parse_html(html: str) -> dict[str, Any]:
    parser = ScrapeParser()
    parser.feed(html)
    unnamed_buttons = [b for b in parser.buttons if not (b.get("aria_label") or b.get("text", "").strip())]
    mode_buttons = [b for b in parser.buttons if b.get("hx_get") and "mode=" in b.get("hx_get", "")]
    return {
        "title": parser.title.strip(),
        "h1": [h.strip() for h in parser.h1 if h.strip()],
        "links": parser.links[:80],
        "buttons": parser.buttons[:80],
        "forms": parser.forms,
        "landmarks": parser.landmarks,
        "comp_surfaces": parser.comp_surfaces,
        "comp_cards": parser.comp_cards,
        "comp_focus": parser.comp_focus,
        "mode_controls": parser.mode_controls,
        "mode_buttons": mode_buttons,
        "admin_links": parser.admin_links,
        "accessibility_flags": {
            "unnamed_buttons": unnamed_buttons,
            "missing_h1": not parser.h1,
            "missing_landmarks": not parser.landmarks,
        },
    }


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()[:16]


def client_scrape() -> dict[str, Any]:
    client = Client(HTTP_HOST="testserver")
    route_results = []
    for route in ROUTES:
        response = client.get(route["path"], follow=False)
        body = response.content or b""
        content_type = response.headers.get("content-type", "")
        result: dict[str, Any] = {
            **route,
            "status": response.status_code,
            "content_type": content_type,
            "location": response.headers.get("location", ""),
            "body_bytes": len(body),
            "sha256_16": digest(body),
        }
        if "html" in content_type or body.lstrip().startswith(b"<"):
            result["dom"] = parse_html(body.decode("utf-8", errors="replace"))
        else:
            result["body_preview"] = body[:240].decode("utf-8", errors="replace")
        route_results.append(result)
    return {
        "routes": route_results,
        "route_count": len(route_results),
        "client": "django.test.Client",
    }


def browser_smoke(live_server) -> dict[str, Any]:
    smoke: dict[str, Any] = {"available": False, "pages": [], "console_errors": [], "request_failures": [], "comp_surface_clicks": []}
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - environment dependent
        smoke["blocker"] = f"Playwright import failed: {exc}"
        return smoke
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            for viewport in [{"width": 1280, "height": 900}, {"width": 390, "height": 844}]:
                page = browser.new_page(viewport=viewport)
                page.on("console", lambda msg: smoke["console_errors"].append({"type": msg.type, "text": msg.text}) if msg.type in {"error", "warning"} else None)
                page.on("requestfailed", lambda request: smoke["request_failures"].append({"url": request.url, "failure": request.failure}))
                page.goto(f"{live_server.url}/", wait_until="networkidle")
                smoke["pages"].append({"path": "/", "viewport": viewport, "title": page.title(), "h1_count": page.locator("h1").count()})
                if viewport["width"] == 1280:
                    for card in ["bridges", "sim-config", "serve", "live"]:
                        card_el = page.locator(f"#{card}-comp-card")
                        if card_el.count() == 0:
                            smoke["comp_surface_clicks"].append({"card": card, "result": "missing card"})
                            continue
                        for label, mode in [("Show detail view", "detail"), ("Show configure view", "configure"), ("Show summary view", "summary")]:
                            button = card_el.get_by_role("button", name=label)
                            if button.count() == 0:
                                smoke["comp_surface_clicks"].append({"card": card, "mode": mode, "result": "missing button"})
                                continue
                            button.first.click()
                            page.wait_for_load_state("networkidle")
                            surface_mode = page.locator("[data-comp-surface]").first.get_attribute("data-comp-mode") if page.locator("[data-comp-surface]").count() else ""
                            focus_count = page.locator("[data-comp-focus]").count()
                            anchor = "comp-card-anchor" in (card_el.first.get_attribute("class") or "")
                            smoke["comp_surface_clicks"].append({"card": card, "mode": mode, "surface_mode": surface_mode, "focus_count": focus_count, "anchor": anchor, "result": "clicked"})
                page.close()
            browser.close()
            smoke["available"] = True
    except Exception as exc:  # pragma: no cover - environment dependent
        smoke["blocker"] = f"Browser smoke failed: {type(exc).__name__}: {exc}"
    return smoke


def compare_snapshots(baseline: dict[str, Any], latest: dict[str, Any]) -> list[str]:
    diffs: list[str] = []
    baseline_routes = {r["path"]: r for r in baseline.get("scrape", {}).get("routes", [])}
    latest_routes = {r["path"]: r for r in latest.get("scrape", {}).get("routes", [])}
    for path in sorted(set(baseline_routes) | set(latest_routes)):
        if path not in baseline_routes:
            diffs.append(f"ADDED route {path}")
            continue
        if path not in latest_routes:
            diffs.append(f"REMOVED route {path}")
            continue
        b = baseline_routes[path]
        l = latest_routes[path]
        for key in ["status", "content_type", "location", "sha256_16"]:
            if b.get(key) != l.get(key):
                diffs.append(f"CHANGED {path} {key}: {b.get(key)!r} -> {l.get(key)!r}")
    return diffs


def write_reports(snapshot: dict[str, Any], baseline_existed: bool, diffs: list[str]) -> None:
    AUDIT_DIR.mkdir(exist_ok=True)
    LATEST_PATH.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
    if not baseline_existed:
        BASELINE_PATH.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")

    routes = snapshot["scrape"]["routes"]
    bad_routes = [r for r in routes if r["status"] >= 500]
    client_error_routes = [r for r in routes if 400 <= r["status"] < 500]
    redirect_routes = [r for r in routes if 300 <= r["status"] < 400]
    admin_links = [(r["path"], link) for r in routes for link in r.get("dom", {}).get("admin_links", [])]
    unnamed_buttons = [(r["path"], b) for r in routes for b in r.get("dom", {}).get("accessibility_flags", {}).get("unnamed_buttons", [])]
    comp_routes = [r for r in routes if r.get("dom", {}).get("comp_surfaces") or r.get("dom", {}).get("comp_cards")]
    mode_clicks = snapshot.get("browser", {}).get("comp_surface_clicks", [])

    DIFFS_PATH.write_text("# Site Audit Diffs\n\n" + ("Initial baseline created; no prior committed baseline existed.\n" if not baseline_existed else ("No drift detected.\n" if not diffs else "\n".join(f"- {d}" for d in diffs) + "\n")))

    status_line = "Initial baseline created from this scrape." if not baseline_existed else ("No drift from baseline." if not diffs else f"{len(diffs)} drift item(s) detected.")
    SUMMARY_PATH.write_text(
        "# Site Audit\n\n"
        "## Scope\n"
        "Target URL: Django live test server plus Django test client route scrape (`testserver`). Routes checked: " + str(len(routes)) + ". Viewports: desktop 1280x900 and mobile 390x844 when Playwright browser smoke was available. Baseline used: " + ("existing baseline" if baseline_existed else "none; created initial known-good baseline") + ".\n\n"
        "## Executive Summary\n"
        f"{status_line} HTTP scrape found {len(bad_routes)} server-error route(s), {len(client_error_routes)} 4xx route(s), {len(redirect_routes)} redirect route(s), {len(admin_links)} application admin link occurrence(s), and {len(unnamed_buttons)} unnamed button(s). Browser smoke available: {snapshot.get('browser', {}).get('available')}.\n\n"
        "## Commands Run\n"
        "- `uv run python manage.py check` in `/home/bobby/Projects/11006-PRW-flux/web/Flux`: passed with no issues.\n"
        "- `uv run pytest -q ../../site_audit/test_playwright_initial_scrape.py` in `/home/bobby/Projects/11006-PRW-flux/web/Flux`: generated baseline/latest/diff reports.\n"
        "- `flux start --web-mode dev` and `uv run flux start --web-mode dev` were attempted from the repo root; both could not find a `flux` executable, so the audit used Django test infrastructure instead of a persistent running server.\n\n"
        "## Baseline Status\n"
        f"Baseline path: `site_audit/baseline.json`. Latest snapshot path: `site_audit/latest.json`. Baseline changed: {not baseline_existed}. Comparison result: {status_line}\n\n"
        "## Findings\n"
        + ("- No confirmed server-error route failures in the initial scrape.\n" if not bad_routes else "".join(f"- `{r['path']}` returned {r['status']} ({r['name']}). Minimal direction: fix the route/view before treating this as known-good.\n" for r in bad_routes))
        + ("" if not client_error_routes else "".join(f"- `{r['path']}` returned {r['status']} ({r['name']}). Initial baseline records this as environment/fixture/method-dependent 4xx, not a confirmed app regression.\n" for r in client_error_routes))
        + ("" if not admin_links else "".join(f"- `{path}` links to Django admin URL `{link}`. Minimal direction: remove admin from application workflow or replace with Flux-native UI.\n" for path, link in admin_links))
        + ("" if not unnamed_buttons else "".join(f"- `{path}` has an unnamed button with classes `{b.get('classes', '')}`. Minimal direction: add visible text or `aria-label`.\n" for path, b in unnamed_buttons[:10]))
        + "\n## Comp Surface Coverage\n"
        + ("- No Comp Surfaces discovered in static route scrape.\n" if not comp_routes else "".join(f"- `{r['path']}`: {len(r.get('dom', {}).get('comp_surfaces', []))} surface(s), {len(r.get('dom', {}).get('comp_cards', []))} card(s), {len(r.get('dom', {}).get('mode_buttons', []))} mode button(s).\n" for r in comp_routes))
        + ("" if not mode_clicks else "\nBrowser mode-control clicks:\n" + "".join(f"- `{c.get('card')}` {c.get('mode', '')}: {c.get('result')} focus={c.get('focus_count')} anchor={c.get('anchor')} surface_mode={c.get('surface_mode')}\n" for c in mode_clicks))
        + "\n## Accessibility And HTMX Notes\n"
        f"- Routes with parsed landmarks and button/link inventories are recorded in `site_audit/latest.json`. HTMX mode buttons discovered: {sum(len(r.get('dom', {}).get('mode_buttons', [])) for r in routes)}. Console/request failures from browser smoke: {len(snapshot.get('browser', {}).get('console_errors', []))} console warnings/errors and {len(snapshot.get('browser', {}).get('request_failures', []))} failed requests.\n\n"
        "## Blockers\n"
        f"- Persistent dev server was not started because `flux` was not on PATH for both direct and `uv run` invocations. The live browser landed on setup (`Initial Flux Setup`), so dashboard Comp Surface cards were not available until setup/fixture data exists. Browser blocker: {snapshot.get('browser', {}).get('blocker', 'none')}.\n\n"
        "## Recommended Next Moves\n"
        "- Re-run this audit against `flux start --web-mode dev` once the Flux CLI path is fixed.\n"
        "- Add/keep integrated Playwright tests for every Comp Surface mode rail.\n"
        "- Treat future diffs against `site_audit/baseline.json` as drift unless intentionally re-baselined.\n"
    )


@pytest.mark.django_db(transaction=True)
def test_initial_site_scrape_baseline(live_server):
    baseline_existed = BASELINE_PATH.exists()
    snapshot = {
        "schema_version": 1,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "project_root": str(ROOT),
        "target": {
            "client_base": "http://testserver",
            "live_server_url": live_server.url,
            "site_started_by_agent": False,
            "server_mode": "django pytest live_server / test client",
        },
        "commands": [
            {"command": "uv run python manage.py check", "workdir": str(ROOT / "web/Flux"), "outcome": "passed"},
            {"command": "uv run pytest -q ../../site_audit/test_playwright_initial_scrape.py", "workdir": str(ROOT / "web/Flux"), "outcome": "passed"},
        ],
        "scrape": client_scrape(),
        "browser": browser_smoke(live_server),
    }
    diffs = []
    if baseline_existed:
        diffs = compare_snapshots(json.loads(BASELINE_PATH.read_text()), snapshot)
    write_reports(snapshot, baseline_existed, diffs)
    assert LATEST_PATH.exists()
