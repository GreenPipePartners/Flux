from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from .selectors import LiveCard

LIVE_CARD_CONTEXT_DOCS_URL = "docs/live-card-context.md"


def render_card_table_markdown(card: LiveCard) -> str:
    lines = [
        f"# {card.title}",
        "",
        "| Point | Value | Units | Quality | Stale | Address |",
        "| --- | ---: | --- | --- | --- | --- |",
    ]
    lines.extend(table_row(point) for point in card.points)
    return "\n".join(lines)


def render_card_copy_markdown(
    card: LiveCard,
    *,
    scope_slug: str = "",
    scope_name: str = "",
    page_url: str = "",
) -> str:
    payload = card_copy_payload(card, scope_slug=scope_slug, scope_name=scope_name, page_url=page_url)
    lines = [
        "# Flux Live Card Context",
        "",
    ]
    if page_url:
        lines.extend([f"URL: {page_url}", ""])
    lines.extend(
        [
            "This is a point-in-time snapshot. Treat the address space as the stable card definition and the current values as diagnostic state.",
            "",
            "## Card",
            f"Scope: {scope_slug or '-'}",
            f"Scope Name: {scope_name or '-'}",
            f"Group: {card.group or '-'}",
            f"Kind: {card.kind or '-'}",
            f"Title: {card.title or '-'}",
            "",
            "## Address Space",
        ]
    )
    lines.extend(f"- {point.full_path}" for point in card.points if point.full_path)
    lines.extend(
        [
            "",
            "## Current Values",
            "| Point | Value | Units | Quality | Stale | Read At |",
            "| --- | ---: | --- | --- | --- | --- |",
        ]
    )
    lines.extend(value_row(point) for point in card.points)
    lines.extend(
        [
            "",
            "## Documentation",
            f"- {LIVE_CARD_CONTEXT_DOCS_URL}",
            "",
            "## Reproducible Definition",
            "```json",
            json.dumps(payload, indent=2, sort_keys=True),
            "```",
        ]
    )
    return "\n".join(lines)


def card_copy_payload(
    card: LiveCard,
    *,
    scope_slug: str = "",
    scope_name: str = "",
    page_url: str = "",
) -> dict[str, Any]:
    return {
        "type": "flux.live.card.context",
        "version": 1,
        "url": page_url,
        "scope": {"slug": scope_slug, "name": scope_name},
        "definition": {
            "title": card.title,
            "group": card.group,
            "kind": card.kind,
            "points": [
                {
                    "label": point.label,
                    "full_path": point.full_path,
                }
                for point in card.points
            ],
        },
        "snapshot": {
            "points": [
                {
                    "label": point.label,
                    "value": json_safe_value(point.value),
                    "display_value": point.display_value,
                    "units": point.units,
                    "quality": point.quality,
                    "stale": point.stale,
                    "read_at": iso_value(point.read_at),
                    "history": [asdict(extreme) for extreme in point.history],
                }
                for point in card.points
            ],
        },
    }


def value_row(point) -> str:
    return "| %s | %s | %s | %s | %s | %s |" % (
        markdown_cell(point.label),
        markdown_cell(point.display_value or "missing"),
        markdown_cell(point.units or "-"),
        markdown_cell(point.quality or "-"),
        "true" if point.stale else "false",
        markdown_cell(iso_value(point.read_at) or "-"),
    )


def table_row(point) -> str:
    return "| %s | %s | %s | %s | %s | %s |" % (
        markdown_cell(point.label),
        markdown_cell(point.display_value or "missing"),
        markdown_cell(point.units or "-"),
        markdown_cell(point.quality or "-"),
        "true" if point.stale else "false",
        markdown_cell(point.full_path or "-"),
    )


def markdown_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def iso_value(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def json_safe_value(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)
