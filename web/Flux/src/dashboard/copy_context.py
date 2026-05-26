from __future__ import annotations

import json
from typing import Any

from flux.bridge.models import IgnitionBridgeConfig


DOCS_URL = "http://localhost:8001/apps/dashboard/#ignition-bridges"
DASHBOARD_DOCS_URL = "http://localhost:8001/apps/dashboard/"


def render_bridge_table_markdown(configs: list[IgnitionBridgeConfig]) -> str:
    lines = [
        "# Ignition Bridges",
        "",
        "| Name | Role | Endpoint | Status | Last Test | Note |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    lines.extend(bridge_table_row(config) for config in configs)
    return "\n".join(lines)


def render_bridge_llm_markdown(configs: list[IgnitionBridgeConfig], *, page_url: str = "") -> str:
    payload = bridge_payload(configs, page_url=page_url)
    lines = ["# Flux Ignition Bridges", ""]
    if page_url:
        lines.extend([f"URL: {page_url}", ""])
    lines.extend(
        [
            render_bridge_table_markdown(configs),
            "",
            f"Docs: {DOCS_URL}",
            "",
            "```json",
            json.dumps(payload, sort_keys=True, separators=(",", ":")),
            "```",
        ]
    )
    return "\n".join(lines)


def render_bridge_form_table_markdown() -> str:
    return "\n".join(
        [
            "# Ignition Bridge Configuration Fields",
            "",
            "| Field | Purpose | Notes |",
            "| --- | --- | --- |",
            "| Name | Stable bridge identifier | Updating by the same name edits the existing bridge. |",
            "| Role | Production or Simulator | Separates production and sim Ignition bridge intent. |",
            "| Fluxy base URL | WebDev Fluxy endpoint | Usually ends with `/system/webdev/flux`. |",
            "| Token | Optional bridge auth token | Write-only. Stored tokens are never rendered back. |",
            "| Clear stored token | Remove saved token | Use when rotating or disabling bridge auth. |",
        ]
    )


def render_bridge_form_llm_markdown(*, page_url: str = "") -> str:
    payload = {
        "type": "flux.dashboard.ignition_bridge_config_form.context",
        "version": 1,
        "url": page_url,
        "docs_url": DOCS_URL,
        "fields": [
            {"name": "name", "purpose": "Stable bridge identifier", "required": True},
            {"name": "role", "purpose": "Production or simulator bridge classification", "required": True},
            {"name": "base_url", "purpose": "Fluxy WebDev endpoint URL", "required": True},
            {"name": "token", "purpose": "Optional write-only bridge token", "required": False, "redacted": True},
            {"name": "clear_token", "purpose": "Remove stored token", "required": False},
        ],
    }
    lines = ["# Flux Ignition Bridge Form Context", ""]
    if page_url:
        lines.extend([f"URL: {page_url}", ""])
    lines.extend(
        [
            "This form creates or updates Fluxy WebDev bridge endpoints for production and simulator Ignition gateways.",
            "Tokens are write-only and must not be rendered back to the UI or copied into context packets.",
            "",
            "## Fields",
            render_bridge_form_table_markdown(),
            "",
            "## Documentation",
            f"- {DOCS_URL}",
            "",
            "## Machine Context",
            "```json",
            json.dumps(payload, indent=2, sort_keys=True),
            "```",
        ]
    )
    return "\n".join(lines)


def render_dashboard_card_table_markdown(title: str, rows: list[tuple[str, Any]]) -> str:
    lines = [
        f"# {title}",
        "",
        "| Field | Value |",
        "| --- | --- |",
    ]
    lines.extend("| %s | %s |" % (markdown_cell(label), markdown_cell(value)) for label, value in rows)
    return "\n".join(lines)


def render_dashboard_card_llm_markdown(
    *,
    title: str,
    description: str,
    rows: list[tuple[str, Any]],
    payload: dict[str, Any],
    docs_url: str,
    page_url: str = "",
) -> str:
    enriched_payload = {
        "type": payload.get("type", "flux.dashboard.card.context"),
        "version": 1,
        "url": page_url,
        "docs_url": docs_url,
        **payload,
    }
    lines = [f"# {title} Context", ""]
    if page_url:
        lines.extend([f"URL: {page_url}", ""])
    lines.extend(
        [
            description,
            "",
            "## Card Data",
            render_dashboard_card_table_markdown(title, rows),
            "",
            "## Documentation",
            f"- {docs_url}",
            "",
            "## Machine Context",
            "```json",
            json.dumps(enriched_payload, default=str, indent=2, sort_keys=True),
            "```",
        ]
    )
    return "\n".join(lines)


def dashboard_card_copy_context(
    *,
    title: str,
    description: str,
    rows: list[tuple[str, Any]],
    payload: dict[str, Any],
    docs_anchor: str,
    page_url: str = "",
) -> dict[str, str]:
    docs_url = DASHBOARD_DOCS_URL + docs_anchor
    return {
        "docs_url": docs_url,
        "table": render_dashboard_card_table_markdown(title, rows),
        "llm": render_dashboard_card_llm_markdown(
            title=title,
            description=description,
            rows=rows,
            payload=payload,
            docs_url=docs_url,
            page_url=page_url,
        ),
    }


def simserver_copy_context(device_status: dict[str, Any], *, page_url: str = "") -> dict[str, str]:
    endpoint_rows = []
    for item in device_status.get("endpoint_items", []):
        endpoint = item["endpoint"]
        endpoint_rows.append(
            {
                "name": endpoint.name,
                "status": endpoint.status,
                "verified_online": item["online"],
                "observed_state": item.get("observed_state", ""),
                "device_count": item["enabled_device_count"],
                "tag_count": item["enabled_tag_count"],
                "last_error": endpoint.last_error,
            }
        )
    rows = [
        ("Servers verified running", "%s/%s" % (device_status.get("running_endpoint_count", 0), device_status.get("enabled_endpoint_count", 0))),
        ("Device namespaces", device_status.get("enabled_device_count", 0)),
        ("Field tags", device_status.get("enabled_tag_count", 0)),
        ("Latest heartbeat", device_status.get("latest_seen_at") or "-"),
    ]
    return dashboard_card_copy_context(
        title="Flux.sim Runtime Connection",
        description="Runtime connection context describes the SimServer OPC endpoints used by Flux.sim. Dashboard rows show last reported endpoint state plus heartbeat evidence; verified process and TCP truth belongs to Flux.serve snapshots.",
        rows=rows,
        payload={"type": "flux.dashboard.simserver.context", "summary": dict(rows), "endpoints": endpoint_rows},
        docs_anchor="#sim-config",
        page_url=page_url,
    )


def serve_heartbeat_copy_context(serve_status: dict[str, Any], *, page_url: str = "") -> dict[str, str]:
    if serve_status.get("source") == "snapshots":
        rows = [
            ("Healthy", serve_status.get("ok_count", 0)),
            ("Warning", serve_status.get("warning_count", 0)),
            ("Error", serve_status.get("error_count", 0)),
            ("Stale snapshots", serve_status.get("stale_count", 0)),
        ]
        title = "Flux.serve Observed Health"
        description = "Observed service health is the consolidated Flux.serve platform view of expected services, dependencies, and raw heartbeat evidence."
        payload_type = "flux.dashboard.serve_observed_health.context"
        docs_anchor = "#service-visibility"
    else:
        rows = [
            ("Running", serve_status.get("running_count", 0)),
            ("Stale", serve_status.get("stale_count", 0)),
            ("Error", serve_status.get("error_count", 0)),
        ]
        title = "Flux.serve Service Heartbeats"
        description = "Service heartbeat context is the detail signal for Flux.serve supervisor and worker health."
        payload_type = "flux.dashboard.serve_heartbeats.context"
        docs_anchor = "#service-heartbeats"
    return dashboard_card_copy_context(
        title=title,
        description=description,
        rows=rows,
        payload={"type": payload_type, "summary": dict(rows)},
        docs_anchor=docs_anchor,
        page_url=page_url,
    )


def stale_recovery_copy_context(
    stale_items: list[dict[str, Any]],
    *,
    stale_count: int,
    page_url: str = "",
) -> dict[str, str]:
    rows = [("Stale count", stale_count), ("Active refresh rows", len(stale_items))]
    rows.extend(
        (
            "%s / %s" % (item["tag"].asset_name or "-", item["tag"].display_name),
            "%s%s · %s"
            % (
                item["reason"],
                " (%ss old)" % item["age_seconds"] if item.get("age_seconds") else "",
                item.get("status_label", "stale"),
            ),
        )
        for item in stale_items
    )
    return dashboard_card_copy_context(
        title="Flux.spot Stale Tag Recovery",
        description="Stale recovery context lists Flux.spot runtime tags selected for a consolidated Fluxy block refresh.",
        rows=rows,
        payload={
            "type": "flux.dashboard.stale_recovery.context",
            "stale_count": stale_count,
            "active_refresh_count": len(stale_items),
            "tags": [
                {
                    "full_path": item["tag"].full_path,
                    "asset_name": item["tag"].asset_name,
                    "display_name": item["tag"].display_name,
                    "reason": item["reason"],
                    "age_seconds": item.get("age_seconds"),
                    "source_context": item.get("source_context", ""),
                    "legacy_source_missing": item.get("legacy_source_missing", False),
                }
                for item in stale_items
            ],
        },
        docs_anchor="#stale-tag-recovery",
        page_url=page_url,
    )


def bridge_payload(configs: list[IgnitionBridgeConfig], *, page_url: str = "") -> dict[str, Any]:
    return {
        "type": "flux.dashboard.ignition_bridges.context",
        "version": 1,
        "url": page_url,
        "docs_url": DOCS_URL,
        "bridges": [
            {
                "name": config.name,
                "role": config.role,
                "base_url": config.base_url,
                "status": config.status_label,
                "token_set": bool(config.token),
                "last_test_at": config.last_test_at.isoformat() if config.last_test_at else "",
                "message": config.last_test_summary,
            }
            for config in configs
        ],
    }


def bridge_table_row(config: IgnitionBridgeConfig) -> str:
    return "| %s | %s | %s | %s | %s | %s |" % (
        markdown_cell(config.name),
        markdown_cell(config.get_role_display()),
        markdown_cell(config.base_url),
        markdown_cell("%s, %s" % (config.status_label, "token set" if config.token else "no token")),
        markdown_cell(config.last_test_at.isoformat() if config.last_test_at else "-"),
        markdown_cell(config.last_test_summary or "-"),
    )


def markdown_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
