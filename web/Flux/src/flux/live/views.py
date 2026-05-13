from django.conf import settings
from django.shortcuts import render
from django.utils import timezone

from runtime.models import RuntimeTag
from flux.nav.context import navigation_context

from .selectors import pad_overview_cards


PAD_OVERVIEW_TABS = ("Well", "Meter", "Tank")


def index(request):
    tags = RuntimeTag.objects.select_related("latest_value", "schedule").order_by(
        "asset_name", "display_name"
    )
    now = timezone.now()
    stale_after_seconds = settings.STALE_AFTER_SECONDS
    stale_count = 0
    bad_quality_count = 0
    online_count = 0

    for tag in tags:
        value = getattr(tag, "latest_value", None)
        if value is None:
            stale_count += 1
            continue
        if value.quality_code.lower() != "good":
            bad_quality_count += 1
        if value.is_stale(now, stale_after_seconds):
            stale_count += 1
        else:
            online_count += 1

    return render(
        request,
        "live/index.html",
        {
            "tags": tags,
            "online_count": online_count,
            "stale_count": stale_count,
            "bad_quality_count": bad_quality_count,
            "stale_after_seconds": stale_after_seconds,
        },
    )


def pad_overview(request):
    tab = selected_pad_overview_tab(request)
    cards = filtered_pad_overview_cards(tab)
    return render(request, "live/pad_overview.html", pad_overview_context(tab, cards, request=request))


def pad_overview_cards_partial(request):
    cards = filtered_pad_overview_cards(selected_pad_overview_tab(request))
    return render(request, "live/partials/pad_overview_content.html", pad_overview_content_context(cards))


def pad_overview_tab_panel(request):
    tab = selected_pad_overview_tab(request)
    cards = filtered_pad_overview_cards(tab)
    return render(request, "live/partials/pad_overview_tab_panel.html", pad_overview_context(tab, cards))


def selected_pad_overview_tab(request) -> str:
    requested = request.GET.get("equipment", PAD_OVERVIEW_TABS[0]).strip().lower()
    for tab in PAD_OVERVIEW_TABS:
        if tab.lower() == requested:
            return tab
    return PAD_OVERVIEW_TABS[0]


def filtered_pad_overview_cards(tab: str):
    return [card for card in pad_overview_cards() if card.equipment_type == tab]


def pad_overview_context(tab: str, cards, *, request=None):
    context = {
        "cards": cards,
        "refresh_timer": refresh_timer(cards),
        "equipment_tabs": PAD_OVERVIEW_TABS,
        "selected_equipment": tab,
    }
    if request is not None:
        context.update(navigation_context(request, default_profile_key="well"))
    return context


def pad_overview_content_context(cards):
    return {
        "cards": cards,
        "refresh_timer": refresh_timer(cards),
    }


def refresh_timer(cards):
    points = [point for card in cards for point in card.points]
    ready_points = [point for point in points if point.next_read_seconds is not None]
    if not ready_points:
        return {"label": "waiting", "seconds": None, "percent": 0}
    point = min(ready_points, key=lambda item: item.next_read_seconds)
    return {"label": f"{point.next_read_seconds}s", "seconds": point.next_read_seconds, "percent": point.countdown_percent}
