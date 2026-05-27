from django.conf import settings
from django.db.models import Count, Q
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from flux.base.runtime import RuntimeTag
from flux.links import flux_link
from flux.opt.services import touch_runtime_demand
from flux.pagination import table_page
from flux.serve.status import runtime_read_status
from flux.web_pulse import display_pulse_context, latest_timestamp

from .copy_context import render_card_copy_markdown, render_card_table_markdown
from .models import LiveScope
from .selectors import pad_overview_cards, parse_full_tag_path, scope_cards


PAD_OVERVIEW_TABS = ("Well", "Meter", "Tank")


def spot_route_name(name: str) -> str:
    return f"spot:{name}"


def live_route_context() -> dict[str, str]:
    return {
        "live_index_route": spot_route_name("index"),
        "live_pad_overview_route": spot_route_name("pad_overview"),
        "live_pad_overview_tab_panel_route": spot_route_name("pad_overview_tab_panel"),
        "live_pad_overview_cards_route": spot_route_name("pad_overview_cards"),
        "live_scope_detail_route": spot_route_name("scope_detail"),
        "live_scope_panel_route": spot_route_name("scope_panel"),
        "live_scope_cards_route": spot_route_name("scope_cards"),
    }


def index(request):
    all_tags = list(live_table_tags())
    tag_page = table_page(request, all_tags, "live_table_page")
    tags = list(tag_page.object_list)
    live_table_summary = live_table_counts(all_tags)
    now = timezone.now()
    stale_after_seconds = settings.STALE_AFTER_SECONDS
    stale_count = 0
    bad_quality_count = 0
    online_count = 0
    last_read_at = None

    for tag in all_tags:
        value = getattr(tag, "latest_value", None)
        if value is not None and (last_read_at is None or value.read_at > last_read_at):
            last_read_at = value.read_at
        status = runtime_read_status(value, now=now, stale_after_seconds=stale_after_seconds)
        if status.bad_quality:
            bad_quality_count += 1
        if status.stale:
            stale_count += 1
        if status.online:
            online_count += 1
    selected_live_card, live_surface_mode, live_platform_mode, live_paths_mode, live_table_mode = live_surface_modes(request)
    platform_status = live_platform_status(online_count, stale_count, bad_quality_count)

    return render(
        request,
        "live/index.html",
        {
            "tags": tags,
            "tag_page": tag_page,
            "online_count": online_count,
            "stale_count": stale_count,
            "bad_quality_count": bad_quality_count,
            "platform_status": platform_status,
            "stale_after_seconds": stale_after_seconds,
            "live_table_summary": live_table_summary,
            "live_paths": live_path_index(),
            "selected_live_card": selected_live_card,
            "live_surface_mode": live_surface_mode,
            "live_platform_mode": live_platform_mode,
            "live_paths_mode": live_paths_mode,
            "live_table_mode": live_table_mode,
            "live_index_link": flux_link(
                title="Flux Spot Tag Snapshots",
                description="Flux Spot shows latest cached runtime tag values without browser-driven Ignition binding pressure.",
                rows=[("Online", online_count), ("Stale", stale_count), ("Bad quality", bad_quality_count), ("Stale after", f"{stale_after_seconds}s")],
                payload={"type": "flux.spot.index.context"},
                docs_path="apps/spot/",
                page_url=request.build_absolute_uri(),
            ),
            "flux_web_pulse": display_pulse_context(
                source_label="Flux.spot latest values",
                last_backend_at=last_read_at,
                state=live_pulse_state(platform_status, stale_count, bad_quality_count),
                detail=f"{online_count} online · {stale_count} stale · {bad_quality_count} bad",
            ),
            **live_route_context(),
        },
    )


def live_surface_modes(request):
    selected_card = request.GET.get("card", "")
    if selected_card not in {"live-platform", "live-paths", "live-table"}:
        selected_card = ""
    requested_mode = request.GET.get("mode", "summary")
    live_platform_mode = requested_mode if selected_card == "live-platform" and requested_mode == "detail" else "summary"
    live_paths_mode = requested_mode if selected_card == "live-paths" and requested_mode == "detail" else "summary"
    live_table_mode = requested_mode if selected_card == "live-table" and requested_mode == "detail" else "summary"
    surface_mode = next(
        (mode for mode in (live_platform_mode, live_paths_mode, live_table_mode) if mode != "summary"),
        "summary",
    )
    return selected_card, surface_mode, live_platform_mode, live_paths_mode, live_table_mode


def live_platform_status(online_count: int, stale_count: int, bad_quality_count: int) -> dict[str, str]:
    if online_count and not stale_count and not bad_quality_count:
        return {"state": "ok", "label": "Ready"}
    if online_count:
        return {"state": "warning", "label": "Attention needed"}
    return {"state": "error", "label": "Offline"}


def live_pulse_state(platform_status: dict[str, str], stale_count: int, bad_quality_count: int) -> str:
    if stale_count:
        return "stale"
    if bad_quality_count:
        return "warning"
    return platform_status["state"]


def live_table_tags():
    path_filter = Q(path__startswith="FluxLiveDemo")
    for full_path in live_scope_full_paths():
        try:
            provider, path = parse_full_tag_path(full_path)
        except ValueError:
            continue
        path_filter |= Q(provider=provider, path=path)
    return (
        RuntimeTag.objects.select_related("latest_value", "schedule")
        .filter(enabled=True)
        .filter(path_filter)
        .order_by("asset_name", "display_name")
    )


def live_scope_full_paths() -> list[str]:
    return list(
        LiveScope.objects.filter(enabled=True)
        .values_list("cards__points__full_path", flat=True)
        .filter(cards__enabled=True, cards__points__enabled=True, cards__points__full_path__gt="")
        .distinct()
    )


def live_table_counts(tags) -> dict[str, int]:
    visible_ids = [tag.id for tag in tags]
    hidden_tags = RuntimeTag.objects.filter(enabled=True).exclude(id__in=visible_ids)
    hidden_trace_count = hidden_tags.filter(category=RuntimeTag.Category.TRACE_STRESS).count()
    hidden_unlisted_count = hidden_tags.exclude(category=RuntimeTag.Category.TRACE_STRESS).count()
    return {
        "shown_count": len(tags),
        "total_count": RuntimeTag.objects.filter(enabled=True).count(),
        "hidden_count": hidden_trace_count + hidden_unlisted_count,
        "hidden_trace_count": hidden_trace_count,
        "hidden_unlisted_count": hidden_unlisted_count,
    }


def live_path_index() -> list[dict[str, str | int]]:
    paths: list[dict[str, str | int]] = [
        {
            "label": "Spot Tag Snapshots",
            "path": reverse(spot_route_name("index")),
            "description": "Runtime tag table and current-state health summary.",
            "detail": "Built-in",
        },
        {
            "label": "Pad Overview Demo",
            "path": reverse(spot_route_name("pad_overview")),
            "description": "Demo Comp Surface for current-state well, meter, and tank cards.",
            "detail": "Built-in",
        },
    ]
    scopes = (
        LiveScope.objects.filter(enabled=True)
        .annotate(
            card_count=Count("cards", filter=Q(cards__enabled=True), distinct=True),
            point_count=Count(
                "cards__points",
                filter=Q(cards__enabled=True, cards__points__enabled=True),
                distinct=True,
            ),
        )
        .order_by("slug")
    )
    for scope in scopes:
        paths.append(
            {
                "label": scope.name,
                "path": reverse(spot_route_name("scope_detail"), args=[scope.slug]),
                "description": scope.description or f"Configured spot scope `{scope.slug}`.",
                "detail": f"{scope.card_count} cards / {scope.point_count} points",
            }
        )
    return paths


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
    touch_scope_runtime_demand(scope=scope, group=selected_group, cards=cards)
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
    touch_scope_runtime_demand(scope=scope, group=selected_group, cards=cards)
    live_scope = LiveScope.objects.filter(slug=scope, enabled=True).first()
    cards = attach_copy_contexts(
        cards,
        request=request,
        scope_slug=scope,
        scope_name=live_scope.name if live_scope is not None else "",
    )
    return render(request, "live/partials/scope_refresh_panel.html", scope_refresh_context(scope, selected_group, cards, request=request))


def scope_tab_panel(request, scope):
    selected_group = selected_scope_group(request, scope)
    cards = filtered_scope_cards(scope, selected_group)
    touch_scope_runtime_demand(scope=scope, group=selected_group, cards=cards)
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
    return render(request, "live/partials/pad_overview_tab_panel.html", pad_overview_context(tab, cards, request=request))


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


def touch_scope_runtime_demand(*, scope: str, group: str, cards) -> int:
    return touch_runtime_demand(
        source_key=scope_runtime_demand_source_key(scope=scope, group=group),
        full_paths=card_full_paths(cards),
    )


def scope_runtime_demand_source_key(*, scope: str, group: str) -> str:
    normalized_scope = scope.strip().lower() or "unknown"
    normalized_group = group.strip().lower() if group else "all"
    return f"spot:{normalized_scope}:{normalized_group}"


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
        context.update(live_route_context())
        context["flux_web_pulse"] = live_cards_pulse_context(
            cards,
            source_label="Flux.spot runtime snapshots",
            detail=f"{len(cards)} {tab.lower()} cards",
        )
        context["live_page_link"] = flux_link(
            title="Flux Spot Pad Overview",
            description="Pad overview renders current-state well, meter, and tank cards from Flux runtime snapshots.",
            rows=[("Selected equipment", tab), ("Card count", len(cards))],
            payload={"type": "flux.spot.pad_overview.context"},
            docs_path="apps/spot/",
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
        context.update(live_route_context())
        context["flux_web_pulse"] = live_cards_pulse_context(
            cards,
            source_label="Flux.spot scope snapshots",
            detail=f"{len(cards)} cards" + (f" · {group}" if group else ""),
        )
        context["live_page_link"] = flux_link(
            title="Flux Spot Scope",
            description="Spot scope renders configured current-state cards and leases their tag demand through Flux Opt.",
            rows=[("Scope", scope), ("Selected group", group or "-"), ("Card count", len(cards))],
            payload={"type": "flux.spot.scope.context", "scope": scope, "group": group},
            docs_path="apps/spot/",
            page_url=request.build_absolute_uri(),
        )
    return context


def pad_overview_content_context(cards):
    return {
        "cards": cards,
        "refresh_timer": refresh_timer(cards),
    }


def scope_refresh_context(scope: str, group: str, cards, *, request=None):
    context = {
        "scope_slug": scope,
        "selected_group": group,
        "cards": cards,
        "refresh_timer": refresh_timer(cards),
    }
    if request is not None:
        context.update(live_route_context())
    return context


def live_cards_pulse_context(cards, *, source_label: str, detail: str) -> dict[str, object]:
    points = [point for card in cards for point in card.points]
    latest_read_at = latest_timestamp(point.read_at for point in points)
    stale_count = sum(1 for point in points if point.stale)
    bad_quality_count = sum(1 for point in points if not point.quality_good)
    if latest_read_at is None:
        state = "unknown"
    elif stale_count:
        state = "stale"
    elif bad_quality_count:
        state = "warning"
    else:
        state = "ok"
    return display_pulse_context(
        source_label=source_label,
        last_backend_at=latest_read_at,
        state=state,
        detail=detail,
    )


def refresh_timer(cards):
    points = [point for card in cards for point in card.points]
    ready_points = [point for point in points if point.next_read_centiseconds is not None]
    if not ready_points:
        return {
            "label": "waiting",
            "seconds": None,
            "centiseconds": None,
            "interval_centiseconds": 0,
            "percent": 0,
            "precision": "second",
        }
    point = min(ready_points, key=lambda item: item.next_read_centiseconds)
    return {
        "label": point.next_read_label,
        "seconds": point.next_read_seconds,
        "centiseconds": point.next_read_centiseconds,
        "interval_centiseconds": point.refresh_interval_centiseconds,
        "percent": point.countdown_percent,
        "precision": "centisecond" if point.refresh_interval_centiseconds <= 100 else "second",
    }


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
