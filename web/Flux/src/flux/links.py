from __future__ import annotations

import json
from typing import Any


DOCS_BASE_URL = "http://localhost:8001/"


def flux_link(
    *,
    title: str,
    description: str,
    rows: list[tuple[str, Any]] | None = None,
    payload: dict[str, Any] | None = None,
    docs_path: str = "",
    page_url: str = "",
) -> dict[str, str]:
    rows = rows or []
    docs_url = docs_url_for_path(docs_path)
    machine_payload = {
        "type": (payload or {}).get("type", "flux.link.context"),
        "version": 1,
        "url": page_url,
        "docs_url": docs_url,
        **(payload or {}),
    }
    table = render_table(title, rows)
    llm = "\n".join(
        [
            f"# {title} Context",
            "",
            *( [f"URL: {page_url}", ""] if page_url else [] ),
            description,
            "",
            "## Card Data",
            table,
            "",
            "## Documentation",
            f"- {docs_url}",
            "",
            "## Machine Context",
            "```json",
            json.dumps(machine_payload, default=str, indent=2, sort_keys=True),
            "```",
        ]
    )
    return {"docs_url": docs_url, "table": table, "llm": llm}


def render_table(title: str, rows: list[tuple[str, Any]]) -> str:
    lines = [f"# {title}", "", "| Field | Value |", "| --- | --- |"]
    lines.extend("| %s | %s |" % (markdown_cell(label), markdown_cell(value)) for label, value in rows)
    return "\n".join(lines)


def docs_url_for_path(path: str) -> str:
    return DOCS_BASE_URL + path.lstrip("/")


def markdown_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
