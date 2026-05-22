from django.conf import settings
from django.shortcuts import render
from django.utils import timezone

from flux.base.runtime import RuntimeTag
from flux.links import flux_link
from flux.opt.services import lease_runtime_demand
from flux.serve.status import runtime_read_status
from flux.nav.context import navigation_context

from .copy_context import render_card_copy_markdown, render_card_table_markdown
from .models import LiveScope
from .selectors import pad_overview_cards, scope_cards


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
        status = runtime_read_status(value, now=now, stale_after_seconds=stale_after_seconds)
        if status.bad_quality:
            bad_quality_count += 1
        if status.stale:
            stale_count += 1
        if status.online:
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
            "live_index_link": flux_link(
                title="Flux Live Tag Snapshots",
                description="Flux Live shows latest cached runtime tag values without browser-driven Ignition binding pressure.",
                rows=[("Online", online_count), ("Stale", stale_count), ("Bad quality", bad_quality_count), ("Stale after", f"{stale_after_seconds}s")],
                payload={"type": "flux.live.index.context"},
                docs_path="apps/live/",
                page_url=request.build_absolute_uri(),
            ),
        },
    )


def pad_overview(request):
    tab = selected_pad_overview_tab(request)
    cards = filtered_pad_overview_cards(tab)
    cards = attach_copy_contexts(cards, request=request, scope_slug="pad-overview", scope_name="Pad Overview Demo")
    return render(request, "live/pad_overview.html", pad_overview_context(tab, cards, request=request))


def pad_overview_cards_partial(request):
    cards = filtered_pad_overview_cards(selected_pad_overview_tab(request))
    cards = attach_copy_contexts(cards, request=request, scope_slug="pad-overview", scope_name="Pad Overview Demo")
    return render(request, "live/partials/pad_overview_content.html", pad_overview_content_context(cards))


def scope_detail(request, scope):
    selected_group = selected_scope_group(request, scope)
    cards = filtered_scope_cards(scope, selected_group)
    lease_runtime_demand(full_paths=card_full_paths(cards))
    live_scope = LiveScope.objects.filter(slug=scope, enabled=True).first()
    cards = attach_copy_contexts(
        cards,
        request=request,
        scope_slug=scope,
        scope_name=live_scope.name if live_scope is not None else "",
    )
    return render(request, "live/scope.html", scope_context(scope, selected_group, cards, request=request))


def scope_cards_partial(request, scope):
    selected_group = selected_scope_group(request, scope)
    cards = filtered_scope_cards(scope, selected_group)
    lease_runtime_demand(full_paths=card_full_paths(cards))
    live_scope = LiveScope.objects.filter(slug=scope, enabled=True).first()
    cards = attach_copy_contexts(
        cards,
        request=request,
        scope_slug=scope,
        scope_name=live_scope.name if live_scope is not None else "",
    )
    return render(request, "live/partials/scope_refresh_panel.html", scope_refresh_context(scope, selected_group, cards))


def scope_tab_panel(request, scope):
    selected_group = selected_scope_group(request, scope)
    cards = filtered_scope_cards(scope, selected_group)
    lease_runtime_demand(full_paths=card_full_paths(cards))
    live_scope = LiveScope.objects.filter(slug=scope, enabled=True).first()
    cards = attach_copy_contexts(
        cards,
        request=request,
        scope_slug=scope,
        scope_name=live_scope.name if live_scope is not None else "",
    )
    return render(request, "live/partials/scope_tab_panel.html", scope_context(scope, selected_group, cards, request=request))


def pad_overview_tab_panel(request):
    tab = selected_pad_overview_tab(request)
    cards = filtered_pad_overview_cards(tab)
    cards = attach_copy_contexts(cards, request=request, scope_slug="pad-overview", scope_name="Pad Overview Demo")
    return render(request, "live/partials/pad_overview_tab_panel.html", pad_overview_context(tab, cards))


def selected_pad_overview_tab(request) -> str:
    requested = request.GET.get("equipment", PAD_OVERVIEW_TABS[0]).strip().lower()
    for tab in PAD_OVERVIEW_TABS:
        if tab.lower() == requested:
            return tab
    return PAD_OVERVIEW_TABS[0]


def filtered_pad_overview_cards(tab: str):
    return [card for card in pad_overview_cards() if card.equipment_type == tab]


def selected_scope_group(request, scope: str) -> str:
    groups = scope_groups(scope)
    if not groups:
        return ""
    requested = request.GET.get("group", groups[0]).strip().lower()
    for group in groups:
        if group.lower() == requested:
            return group
    return groups[0]


def filtered_scope_cards(scope: str, group: str):
    cards = scope_cards(scope)
    if not group:
        return cards
    return [card for card in cards if card.group == group]


def scope_groups(scope: str) -> tuple[str, ...]:
    values = (
        LiveScope.objects.filter(slug=scope, enabled=True)
        .values_list("cards__group", flat=True)
        .filter(cards__enabled=True)
        .distinct()
        .order_by("cards__group")
    )
    return tuple(group for group in values if group)


def pad_overview_context(tab: str, cards, *, request=None):
    context = {
        "cards": cards,
        "refresh_timer": refresh_timer(cards),
        "equipment_tabs": PAD_OVERVIEW_TABS,
        "selected_equipment": tab,
    }
    if request is not None:
        context.update(navigation_context(request, default_profile_key="well"))
        context["live_page_link"] = flux_link(
            title="Flux Live Pad Overview",
            description="Pad overview renders current-state well, meter, and tank cards from Flux runtime snapshots.",
            rows=[("Selected equipment", tab), ("Card count", len(cards))],
            payload={"type": "flux.live.pad_overview.context"},
            docs_path="apps/live/",
            page_url=request.build_absolute_uri(),
        )
    return context


def scope_context(scope: str, group: str, cards, *, request=None):
    live_scope = LiveScope.objects.filter(slug=scope, enabled=True).first()
    context = {
        "scope": live_scope,
        "scope_slug": scope,
        "cards": cards,
        "refresh_timer": refresh_timer(cards),
        "group_tabs": scope_groups(scope),
        "selected_group": group,
    }
    if request is not None:
        context.update(navigation_context(request, default_profile_key="well"))
        context["live_page_link"] = flux_link(
            title="Flux Live Scope",
            description="Live scope renders configured current-state cards and leases their tag demand through Flux Opt.",
            rows=[("Scope", scope), ("Selected group", group or "-"), ("Card count", len(cards))],
            payload={"type": "flux.live.scope.context", "scope": scope, "group": group},
            docs_path="apps/live/",
            page_url=request.build_absolute_uri(),
        )
    return context


def pad_overview_content_context(cards):
    return {
        "cards": cards,
        "refresh_timer": refresh_timer(cards),
    }


def scope_refresh_context(scope: str, group: str, cards):
    return {
        "scope_slug": scope,
        "selected_group": group,
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


def card_full_paths(cards) -> list[str]:
    return [point.full_path for card in cards for point in card.points if point.full_path]


def attach_copy_contexts(cards, *, request, scope_slug: str, scope_name: str):
    from dataclasses import replace

    page_url = request.build_absolute_uri() if request is not None else ""
    return [
        replace(
            card,
            copy_table_markdown=render_card_table_markdown(card),
            copy_llm_markdown=render_card_copy_markdown(
                card,
                scope_slug=scope_slug,
                scope_name=scope_name,
                page_url=page_url,
            ),
        )
        for card in cards
    ]
