from __future__ import annotations

from html import escape

from flux_build.hmi.models import HmiMapScreen


def render_hmi_map_svg(screen: HmiMapScreen) -> str:
    width = int(screen.width or max_component_extent(screen, "width") or 1024)
    height = int(screen.height or max_component_extent(screen, "height") or 768)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(screen.name)} symbolic HMI map">',
        '<rect x="0" y="0" width="100%" height="100%" fill="#111827" />',
    ]
    for component in sorted(screen.components, key=lambda item: (item.bounds.get("top", 0), item.bounds.get("left", 0), item.name)):
        bounds = component.bounds or {}
        x = float(bounds.get("left", 0))
        y = float(bounds.get("top", 0))
        w = max(float(bounds.get("width", 36)), 18.0)
        h = max(float(bounds.get("height", 24)), 18.0)
        title = escape(component.name or component.vendor_type or component.component_key)
        symbol = escape(component.symbol)
        component_key = escape(component.component_key)
        parts.append(
            f'<g data-hmi-map-node="{component_key}" data-symbol="{symbol}" tabindex="0">'
            f'<title>{title}</title>'
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" rx="3" fill="#1f2937" stroke="#93c5fd" stroke-width="1" />'
            f'<text x="{x + w / 2:.2f}" y="{y + h / 2:.2f}" dominant-baseline="middle" text-anchor="middle" fill="#e5e7eb" font-family="monospace" font-size="14">{symbol}</text>'
            "</g>"
        )
    parts.append("</svg>")
    return "\n".join(parts)


def max_component_extent(screen: HmiMapScreen, axis: str) -> float:
    if axis == "width":
        return max((component.bounds.get("left", 0) + component.bounds.get("width", 0) for component in screen.components), default=0)
    return max((component.bounds.get("top", 0) + component.bounds.get("height", 0) for component in screen.components), default=0)
