import csv
from io import StringIO

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.conf import settings
from django.core.management.base import CommandError
from django.shortcuts import redirect, render
from django.template.response import TemplateResponse
from dataclasses import replace

from flux.base.runtime import RuntimeTag
from flux.bridge.models import IgnitionBridgeConfig
from flux.bridge.services import bridge_config, test_bridge, update_bridge_config
from flux.spot.management.commands.import_spot_scope_csv import import_live_scope_rows
from flux.spot.models import LiveScope
from flux.opt.models import RefreshLane
from flux.opt.services import REFRESH_LANES
from flux.chart.importer import import_trace_scopes_csv
from flux.pagination import table_page
from flux.web_pulse import display_pulse_context

from .copy_context import (
    DOCS_URL,
    dashboard_card_copy_context,
    render_bridge_llm_markdown,
    render_bridge_table_markdown,
    serve_heartbeat_copy_context,
    simserver_copy_context,
    stale_recovery_copy_context,
)
from .forms import IgnitionBridgeConfigForm, InitialSuperuserForm
from .services import (
    dashboard_readiness,
    dashboard_runtime_state,
    excluded_interface_runtime_tag_count,
    field_device_status,
    ignition_bridge_status,
    interface_runtime_tags,
    refresh_runtime_tags,
    serve_status,
    start_sim_server,
    stop_sim_server,
)


def setup_required() -> bool:
    return not get_user_model().objects.exists()


def home(request):
    if setup_required():
        return redirect("dashboard:setup")

    aliased_card = {"live": "spot", "trace": "chart"}.get(request.GET.get("card", ""))
    if aliased_card:
        query = request.GET.copy()
        query["card"] = aliased_card
        if request.method == "GET":
            return redirect(f"{request.path}?{query.urlencode()}")
        request.GET = query

    if request.method == "GET" and request.GET.get("partial") == "simserver_card":
        return simserver_card_response(request)

    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "save_bridge":
            if "name" in request.POST:
                bridge_form = IgnitionBridgeConfigForm(request.POST)
                if bridge_form.is_valid():
                    config = bridge_form.save()
                    messages.success(request, f"Saved Ignition bridge {config.name}.")
                    if not request.htmx:
                        return redirect("dashboard:home")
                elif not request.htmx:
                    messages.warning(request, "Ignition bridge configuration is invalid.")
                    return redirect("dashboard:home")
            else:
                base_url = request.POST.get("fluxy_base_url", "").strip()
                token = request.POST.get("fluxy_token", "")
                clear_token = request.POST.get("clear_fluxy_token") == "on"
                if base_url:
                    update_bridge_config(base_url=base_url, token=token if token else None, clear_token=clear_token)
                    messages.success(request, "Saved Ignition Bridge configuration.")
                else:
                    messages.warning(request, "Ignition Bridge URL is required.")
                if not request.htmx:
                    return redirect("dashboard:home")
        if action == "test_bridge":
            bridge_id = request.POST.get("bridge_id", "")
            bridge = IgnitionBridgeConfig.objects.filter(id=bridge_id).first() if bridge_id.isdigit() else None
            config = test_bridge(bridge)
            if config.last_test_ok:
                messages.success(request, config.last_test_message)
            else:
                messages.error(request, f"Ignition bridge test failed: {config.last_test_message}")
            if not request.htmx:
                return redirect("dashboard:home")
        if action == "delete_bridge":
            bridge_id = request.POST.get("bridge_id", "")
            config = IgnitionBridgeConfig.objects.filter(id=bridge_id).first() if bridge_id.isdigit() else None
            if config is None:
                messages.error(request, "Bridge not found.")
            else:
                name = config.name
                config.delete()
                messages.success(request, f"Deleted Ignition bridge {name}.")
            if not request.htmx:
                return redirect("dashboard:home")
        if action == "refresh_stale":
            stale_ids = [int(value) for value in request.POST.getlist("stale_tag_id") if value.isdigit()]
            stale_tags = list(RuntimeTag.objects.filter(id__in=stale_ids, enabled=True).select_related("schedule"))
            try:
                refreshed = refresh_runtime_tags(stale_tags)
            except Exception as exc:
                messages.error(request, f"Stale tag refresh failed: {exc}")
            else:
                messages.success(request, f"Refreshed {refreshed} stale runtime tags from Ignition.")
            if not request.htmx:
                return redirect("dashboard:home")
        if action == "import_live_scope_csv":
            csv_upload = request.FILES.get("live_scope_csv")
            if csv_upload is None:
                messages.error(request, "Choose a Flux.spot CSV file to import.")
            else:
                try:
                    rows = list(csv.DictReader(StringIO(csv_upload.read().decode("utf-8-sig"))))
                    result = import_live_scope_rows(
                        rows,
                        default_scope=(request.POST.get("live_scope") or "Fluxolot"),
                        replace=request.POST.get("replace_live_scope") == "on",
                    )
                except (UnicodeDecodeError, CommandError, ValueError) as exc:
                    messages.error(request, f"Flux.spot CSV import failed: {exc}")
                else:
                    messages.success(
                        request,
                        "Imported %(scopes)s spot scopes, %(cards)s cards, and %(points)s points." % result,
                    )
            if not request.htmx:
                return redirect("dashboard:home")
        if action == "import_trace_scope_csv":
            csv_upload = request.FILES.get("trace_scope_csv")
            if csv_upload is None:
                messages.error(request, "Choose a Flux.chart CSV file to import.")
            else:
                try:
                    result = import_trace_scopes_csv(StringIO(csv_upload.read().decode("utf-8-sig")))
                except (UnicodeDecodeError, ValueError) as exc:
                    messages.error(request, f"Flux.chart CSV import failed: {exc}")
                else:
                    messages.success(
                        request,
                        "Imported %s charts, %s tags, and %s signals."
                        % (result.profiles, result.tags, result.signals),
                    )
            if not request.htmx:
                return redirect("dashboard:home")
        if action == "save_live_refresh_lanes":
            errors = []
            updates = {}
            for lane_name in ("hot", "warm", "cold"):
                raw_value = request.POST.get(f"{lane_name}_interval_seconds", "").strip()
                try:
                    interval_seconds = int(raw_value)
                except ValueError:
                    errors.append(f"{lane_name.title()} refresh must be a whole number of seconds.")
                    continue
                if interval_seconds < 1:
                    errors.append(f"{lane_name.title()} refresh must be at least 1 second.")
                    continue
                updates[lane_name] = interval_seconds
            if errors:
                for error in errors:
                    messages.error(request, error)
            else:
                for lane_name, interval_seconds in updates.items():
                    defaults = {**REFRESH_LANES[lane_name], "interval_seconds": interval_seconds}
                    RefreshLane.objects.update_or_create(name=lane_name, defaults=defaults)
                messages.success(request, "Saved Flux.spot refresh intervals.")
            if not request.htmx:
                return redirect("dashboard:home")
        if action == "start_sim_server":
            endpoint_id = request.POST.get("endpoint_id", "")
            if not endpoint_id.isdigit():
                messages.error(request, "Cannot start SimServer: invalid endpoint id.")
                if request.htmx and request.GET.get("partial") == "simserver_card":
                    return simserver_card_response(request)
                if not request.htmx:
                    return redirect("dashboard:home")
            try:
                endpoint = start_sim_server(int(endpoint_id), requested_by=request.user)
            except Exception as exc:
                messages.error(request, f"Failed to start SimServer: {exc}")
            else:
                messages.success(request, f"Requested start for SimServer {endpoint.name}.")
            if request.htmx and request.GET.get("partial") == "simserver_card":
                return simserver_card_response(request)
            if not request.htmx:
                return redirect("dashboard:home")
        if action == "stop_sim_server":
            endpoint_id = request.POST.get("endpoint_id", "")
            if not endpoint_id.isdigit():
                messages.error(request, "Cannot stop SimServer: invalid endpoint id.")
                if request.htmx and request.GET.get("partial") == "simserver_card":
                    return simserver_card_response(request)
                if not request.htmx:
                    return redirect("dashboard:home")
            try:
                endpoint = stop_sim_server(int(endpoint_id), requested_by=request.user)
            except Exception as exc:
                messages.error(request, f"Failed to stop SimServer: {exc}")
            else:
                messages.success(request, f"Requested stop for SimServer {endpoint.name}.")
            if request.htmx and request.GET.get("partial") == "simserver_card":
                return simserver_card_response(request)
            if not request.htmx:
                return redirect("dashboard:home")

    tags = interface_runtime_tags()
    runtime_state = dashboard_runtime_state(tags)
    service_status = serve_status()
    bridge_status = ignition_bridge_status()
    ensure_live_refresh_lanes()
    live_refresh_lanes = RefreshLane.objects.filter(name__in=("hot", "warm", "cold")).in_bulk(field_name="name")
    readiness = dashboard_readiness(runtime_state, service_status)
    charts_readiness = next((item for item in readiness if item.label == "Flux.chart"), None)
    trace_profile_count = charts_readiness.meta.get("chart_count", 0) if charts_readiness else 0
    trace_signal_count = charts_readiness.meta.get("signal_count", 0) if charts_readiness else 0
    page_url = request.build_absolute_uri()
    readiness = attach_readiness_copy_contexts(readiness, page_url=page_url)
    readiness.insert(
        0,
        type(readiness[0])(
            "Flux.bridge",
            "ok" if bridge_status["connected_count"] else "offline",
            "%s connected" % bridge_status["connected_count"],
            "Configure",
            "/bridges/",
            (
                "%s Production" % bridge_status["production_count"],
                "%s Simulated" % bridge_status["simulator_count"],
            ),
        ),
    )
    service_state = "ok" if all(item.state == "ok" for item in readiness) else "warning"
    pulse_state = dashboard_pulse_state(runtime_state, service_state)
    bridge = bridge_config()
    device_status = field_device_status()
    bridge_configs = bridge_status["configs"]
    active_stale_tag_items, legacy_source_missing_items = split_legacy_source_missing_items(
        runtime_state["stale_tag_items"]
    )
    stale_tag_page = table_page(request, active_stale_tag_items, "live_stale_page")
    stale_tag_items = list(stale_tag_page.object_list)
    serve_status_page = table_page(request, service_status.get("items", []), "dashboard_serve_page")
    service_status = {**service_status, "items": list(serve_status_page.object_list)}

    return render(
        request,
        "dashboard/home.html",
        {
            "tags": tags,
            "online_count": runtime_state["online_count"],
            "stale_count": runtime_state["stale_count"],
            "bad_quality_count": runtime_state["bad_quality_count"],
            "stale_after_seconds": runtime_state["stale_after_seconds"],
            "tag_count": runtime_state["tag_count"],
            "last_read_at": runtime_state["last_read_at"],
            "excluded_runtime_tag_count": excluded_interface_runtime_tag_count(),
            "readiness": readiness,
            "service_state": service_state,
            "stale_tag_items": stale_tag_items,
            "stale_tag_page": stale_tag_page,
            "active_stale_count": len(active_stale_tag_items),
            "legacy_source_missing_count": len(legacy_source_missing_items),
            "device_status": device_status,
            "serve_status": service_status,
            "serve_status_page": serve_status_page,
            "trace_profile_count": trace_profile_count,
            "trace_signal_count": trace_signal_count,
            "live_scopes": LiveScope.objects.filter(enabled=True).order_by("slug"),
            "live_refresh_lanes": [live_refresh_lanes[name] for name in ("hot", "warm", "cold") if name in live_refresh_lanes],
            "bridge": {
                "base_url": bridge.base_url,
                "token_set": bool(bridge.token),
                "online": bridge.last_test_ok,
                "message": bridge.last_test_message,
                "last_test_at": bridge.last_test_at,
            },
            "bridge_status": bridge_status,
            "sim_default_tag_provider": settings.FLUX_SIM_DEFAULT_TAG_PROVIDER,
            "sim_tag_providers": settings.FLUX_SIM_TAG_PROVIDERS,
            "bridge_form": locals().get("bridge_form") or IgnitionBridgeConfigForm(
                initial={
                    "name": bridge.name,
                    "role": bridge.role,
                    "base_url": bridge.base_url,
                }
            ),
            "bridge_copy_docs_url": DOCS_URL,
            "bridge_copy_table_markdown": render_bridge_table_markdown(bridge_configs),
            "bridge_copy_llm_markdown": render_bridge_llm_markdown(
                bridge_configs,
                page_url=page_url,
            ),
            "stale_recovery_copy": stale_recovery_copy_context(
                stale_tag_items,
                stale_count=runtime_state["stale_count"],
                page_url=page_url,
            ),
            "simserver_copy": simserver_copy_context(device_status, page_url=page_url),
            "serve_copy": serve_heartbeat_copy_context(service_status, page_url=page_url),
            "flux_web_pulse": display_pulse_context(
                source_label="Flux.storage interface tags",
                last_backend_at=runtime_state["last_read_at"],
                state=pulse_state,
                detail="%s/%s interface runtime tags online"
                % (runtime_state["online_count"], runtime_state["tag_count"]),
            ),
        },
    )


def dashboard_pulse_state(runtime_state: dict[str, object], service_state: str) -> str:
    if runtime_state["last_read_at"] is None:
        return "offline" if runtime_state["tag_count"] else "unknown"
    if runtime_state["stale_count"]:
        return "stale"
    if runtime_state["bad_quality_count"]:
        return "warning"
    return service_state


def split_legacy_source_missing_items(stale_items: list[dict]) -> tuple[list[dict], list[dict]]:
    active_items = []
    legacy_items = []
    for item in stale_items:
        if item.get("legacy_source_missing"):
            legacy_items.append(item)
        else:
            active_items.append(item)
    return active_items, legacy_items


def bridges(request):
    if setup_required():
        return redirect("dashboard:setup")
    return redirect("/?card=bridges&mode=configure")


def ensure_live_refresh_lanes() -> None:
    for lane_name in ("hot", "warm", "cold"):
        RefreshLane.objects.get_or_create(name=lane_name, defaults=REFRESH_LANES[lane_name])


def simserver_card_response(request):
    device_status = field_device_status()
    return TemplateResponse(
        request,
        "dashboard/partials/simserver_card.html",
        {"device_status": device_status, "simserver_copy": simserver_copy_context(device_status, page_url=request.build_absolute_uri())},
    )


def attach_readiness_copy_contexts(readiness, *, page_url: str):
    contexts = {
        "Flux.sim": (
            "#sim-config",
            "Flux.sim card context summarizes configured simulated OPC servers and tags.",
        ),
        "Flux.mine": (
            "#fluxmine-readiness",
            "Flux.mine readiness context summarizes recovered PLC and HMI source primitives.",
        ),
        "Flux.build": (
            "#fluxbuild-readiness",
            "Flux.build readiness context summarizes process cells built from recovered source primitives.",
        ),
        "Flux.spot": (
            "#latest-reads",
            "Flux.spot card context summarizes current runtime tag freshness and quality from Flux storage.",
        ),
        "Flux.serve": (
            "#fluxserve-readiness",
            "Flux.serve readiness context summarizes supervisor and worker heartbeat health for the local Flux stack.",
        ),
        "Flux.chart": (
            "#fluxcharts-readiness",
            "Flux.chart readiness context summarizes configured charts and signal definitions.",
        ),
    }
    copied = []
    for item in readiness:
        config = contexts.get(item.label)
        if config is None:
            copied.append(item)
            continue
        docs_anchor, description = config
        rows = [("State", item.state), ("Detail", item.detail)]
        rows.extend(("Detail line", line) for line in item.detail_lines)
        if item.action_label:
            rows.append(("Action", "%s %s" % (item.action_label, item.action_url)))
        context = dashboard_card_copy_context(
            title=item.label,
            description=description,
            rows=rows,
            payload={
                "type": "flux.dashboard.readiness_card.context",
                "label": item.label,
                "state": item.state,
                "detail": item.detail,
                "detail_lines": item.detail_lines,
                "action_label": item.action_label,
                "action_url": item.action_url,
            },
            docs_anchor=docs_anchor,
            page_url=page_url,
        )
        copied.append(
            replace(
                item,
                copy_docs_url=context["docs_url"],
                copy_table_markdown=context["table"],
                copy_llm_markdown=context["llm"],
            )
        )
    return copied


def setup(request):
    if not setup_required():
        return redirect("dashboard:home")

    if request.method == "POST":
        form = InitialSuperuserForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Initial Flux superuser created.")
            return redirect("dashboard:home")
    else:
        form = InitialSuperuserForm()

    return render(request, "dashboard/setup.html", {"form": form})
