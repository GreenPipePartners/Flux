from __future__ import annotations

from django import template

register = template.Library()

VALID_MODES = {"summary", "detail", "configure"}


@register.simple_tag
def comp_card_mode(request, card_id: str, default: str = "summary") -> str:
    """Return the requested mode for a card, defaulting other cards to summary."""
    if default not in VALID_MODES:
        default = "summary"
    if not request or request.GET.get("card") != card_id:
        return default
    mode = request.GET.get("mode", default)
    return mode if mode in VALID_MODES else default


@register.inclusion_tag("flux/partials/comp_card_controls.html")
def comp_card_controls(card_id: str, current_mode: str, modes: str = "summary,detail,configure"):
    requested_modes = [mode.strip() for mode in modes.split(",")]
    available_modes = [mode for mode in requested_modes if mode in VALID_MODES]
    if not available_modes:
        available_modes = ["summary"]
    if current_mode not in available_modes:
        current_mode = available_modes[0]
    return {
        "card_id": card_id,
        "current_mode": current_mode,
        "modes": [
            {
                "name": mode,
                "icon": {"summary": "↖", "detail": "↘", "configure": "⚙"}[mode],
                "label": {
                    "summary": "Show summary view",
                    "detail": "Show detail view",
                    "configure": "Show configure view",
                }[mode],
                "active": mode == current_mode,
            }
            for mode in available_modes
        ],
    }
