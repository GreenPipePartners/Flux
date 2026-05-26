from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from flux.bridge.services import bridge_config
from flux.base.field_selectors import enabled_endpoint_configs, endpoint_runtime_counts
from flux.sim.models import FieldEndpoint
from flux.sim.models import SimServer, TagNode, TagProvider
from flux.base.services import provider_tree_children as base_provider_tree_children
from flux.base.services import search_provider_tree
from flux.links import flux_link
from flux.serve.monitor import snapshot_status_item
from flux.serve.models import ServeServiceSnapshot
from flux.web_pulse import display_pulse_context

from .jobs import (
    enqueue_apply_selection,
    enqueue_import_provider_ignition,
    enqueue_import_provider_json,
    enqueue_remove_ignition_tags,
    latest_sim_jobs,
    sim_job_summary,
)
from .models import DeviceConfig, TagConfig
from .output import (
    SIM_OUTPUT_MODE_CHOICES,
    SIM_OUTPUT_MODE_OPTIONS,
    default_mode_groups,
    default_modes_from_post,
    hydrate_sim_output_tree,
    provider_default_modes,
    selected_output_plan,
)
from .provider_tree import (
    imported_provider_names,
    replace_imported_selection,
    selected_source_paths,
    set_imported_selection,
)


def index(request):
    selected_sim_card = selected_card(request.GET.get("card", ""))
    requested_mode = request.GET.get("mode", "summary")
    imported_providers = imported_provider_names()
    requested_catalog_mode = requested_mode if selected_sim_card == "sim-catalog" else "summary"
    sim_catalog_mode = "detail" if requested_catalog_mode == "detail" else "summary"
    sim_import_mode = requested_mode if selected_sim_card == "sim-import" and requested_mode == "configure" else "summary"
    sim_output_mode = requested_mode if selected_sim_card == "sim-output" and requested_mode in {"detail", "configure"} else "summary"
    sim_surface_mode = next(
        (mode for mode in (sim_catalog_mode, sim_import_mode, sim_output_mode) if mode != "summary"),
        "summary",
    )
    selected_imported_provider = request.GET.get("provider", "")
    imported_tag_tree = base_provider_tree_children(selected_imported_provider) if selected_imported_provider and sim_output_mode in {"detail", "configure"} else None
    if imported_tag_tree:
        hydrate_sim_output_tree(imported_tag_tree.nodes)
    provider_defaults = provider_default_modes(selected_imported_provider) if selected_imported_provider else None
    output_plan = selected_output_plan(selected_imported_provider) if selected_imported_provider and sim_output_mode == "configure" else None
    catalog_status = sim_catalog_status()
    platform_status = sim_platform_status()
    field_runtime = sim_field_runtime_status()
    page_url = request.build_absolute_uri()
    return render(
        request,
        "sim/index.html",
        {
            "imported_providers": imported_providers,
            "selected_imported_provider": selected_imported_provider,
            "imported_tag_tree": imported_tag_tree,
            "catalog_status": catalog_status,
            "catalog_lists": sim_catalog_lists() if sim_catalog_mode == "detail" else empty_catalog_lists(),
            "sim_catalog_mode": sim_catalog_mode,
            "sim_import_mode": sim_import_mode,
            "sim_output_mode": sim_output_mode,
            "sim_surface_mode": sim_surface_mode,
            "selected_sim_card": selected_sim_card,
            "sim_output_plan": output_plan,
            "sim_output_query_extra": f"&{urlencode({'provider': selected_imported_provider})}" if selected_imported_provider else "",
            "sim_output_mode_choices": SIM_OUTPUT_MODE_CHOICES,
            "sim_output_mode_options": SIM_OUTPUT_MODE_OPTIONS,
            "sim_output_default_mode_groups": default_mode_groups(provider_defaults),
            "sim_catalog_state": "ok" if catalog_status["provider_count"] else "warning",
            "platform_status": platform_status,
            "sim_default_tag_provider": settings.FLUX_SIM_DEFAULT_TAG_PROVIDER,
            "sim_tag_providers": settings.FLUX_SIM_TAG_PROVIDERS,
            "sim_catalog_link": sim_catalog_link(catalog_status, page_url=page_url),
            "sim_import_link": sim_import_link(imported_providers, page_url=page_url),
            "sim_output_link": sim_output_link(output_plan, selected_imported_provider, page_url=page_url),
            "sim_field_runtime": field_runtime,
            "sim_field_runtime_link": sim_field_runtime_link(field_runtime, page_url=page_url),
            "sim_jobs": latest_sim_jobs(),
            "sim_job_summary": sim_job_summary(),
            "flux_web_pulse": display_pulse_context(
                source_label="Flux.serve FieldAgent evidence",
                last_backend_at=field_runtime["latest_seen_at"],
                state=field_runtime["state"],
                detail="%s/%s endpoints verified"
                % (field_runtime["verified_endpoint_count"], field_runtime["enabled_endpoint_count"]),
            ),
        },
    )


def job_status(request):
    return render(
        request,
        "sim/partials/job_status.html",
        {"sim_jobs": latest_sim_jobs(), "sim_job_summary": sim_job_summary()},
    )


def selected_card(card: str) -> str:
    return card if card in {"sim-catalog", "sim-import", "sim-output"} else ""


def empty_catalog_lists() -> dict[str, object]:
    return {"providers": [], "devices": [], "opc_tags": [], "opc_tag_limit": 0, "opc_tag_overflow": 0}


def sim_catalog_lists(limit: int = 250) -> dict[str, object]:
    provider_device_counts = dict(
        DeviceConfig.objects.filter(source_provider_id__isnull=False)
        .values("source_provider_id")
        .annotate(total=Count("id"))
        .values_list("source_provider_id", "total")
    )
    device_tag_counts = {
        (row["sim_device__base_device__namespace"], row["sim_device__base_device__name"]): row["total"]
        for row in TagConfig.objects.filter(materialized=True, enabled=True)
        .values("sim_device__base_device__namespace", "sim_device__base_device__name")
        .annotate(total=Count("id"))
    }
    providers = [provider_summary(provider, provider_device_counts) for provider in TagProvider.objects.select_related("sim_server").order_by("name")]
    devices = [
        device_summary(device, device_tag_counts)
        for device in DeviceConfig.objects.filter(source_provider_id__isnull=False)
        .select_related("base_device", "source_provider", "driver")
        .order_by("source_provider__name", "base_device__name")
    ]
    opc_tags = (
        TagNode.objects.filter(value_source="opc")
        .exclude(path="")
        .select_related("provider")
        .order_by("provider__name", "path")[:limit]
    )
    opc_tag_count = TagNode.objects.filter(value_source="opc").exclude(path="").count()
    return {
        "providers": providers,
        "devices": devices,
        "opc_tags": opc_tags,
        "opc_tag_limit": limit,
        "opc_tag_overflow": max(0, opc_tag_count - limit),
    }


def provider_summary(provider: TagProvider, provider_device_counts: dict[int, int]) -> dict[str, object]:
    return {
        "name": provider.name,
        "source_label": provider.get_source_display(),
        "device_count": provider_device_counts.get(provider.id, 0),
        "opc_tag_count": provider.atomic_tag_count,
        "sim_server_name": provider.sim_server.name if provider.sim_server else "",
    }


def device_summary(device: DeviceConfig, device_tag_counts: dict[tuple[str, str], int]) -> dict[str, object]:
    device_key = (device.base_device.namespace, device.base_device.name)
    return {
        "provider_name": device.source_provider.name if device.source_provider_id else "",
        "name": device.base_device.name,
        "driver_label": device.driver.label if device.driver_id else device.base_device.device_type,
        "enabled_tag_count": device_tag_counts.get(device_key, 0),
        "mode_label": device.get_mode_display(),
        "enabled": device.enabled,
    }


SIM_RUNTIME_DEVICE_DESCRIPTION_PREFIX = "Materialized from sim.device catalog"


def sim_catalog_link(catalog_status: dict[str, int], *, page_url: str) -> dict[str, str]:
    return flux_link(
        title="Flux.sim.catalog",
        description="Flux.sim.catalog summarizes imported Ignition provider catalogs, simulated devices, and OPC tag leaves.",
        rows=[
            ("Tag Providers", catalog_status["provider_count"]),
            ("Devices", catalog_status["device_count"]),
            ("Tags", catalog_status["opc_tag_count"]),
        ],
        payload={"type": "flux.sim.catalog.surface.context", "catalog_status": catalog_status},
        docs_path="apps/sim/",
        page_url=page_url,
    )


def sim_import_link(imported_providers: list[str], *, page_url: str) -> dict[str, str]:
    return flux_link(
        title="Flux.sim.import",
        description="Flux.sim.import imports Ignition provider catalogs from JSON or a live Ignition provider and selects provider branches for simulation.",
        rows=[("Imported Providers", len(imported_providers)), ("JSON Import", "available"), ("Ignition Import", "available")],
        payload={"type": "flux.sim.import.surface.context", "imported_providers": imported_providers},
        docs_path="apps/sim/",
        page_url=page_url,
    )


def sim_output_link(plan, selected_provider: str, *, page_url: str) -> dict[str, str]:
    selected_count = plan.selected_count if plan is not None else 0
    create_count = plan.create_count if plan is not None else 0
    keep_count = plan.keep_count if plan is not None else 0
    return flux_link(
        title="Flux.sim.output",
        description="Flux.sim.output reconciles desired imported tag selections into materialized simulator OPC output tags.",
        rows=[("Selected Provider", selected_provider or "-"), ("Selected Tags", selected_count), ("New Output Tags", create_count), ("Existing Output Tags", keep_count)],
        payload={
            "type": "flux.sim.output.surface.context",
            "selected_provider": selected_provider,
            "selected_count": selected_count,
            "create_count": create_count,
            "keep_count": keep_count,
        },
        docs_path="apps/sim/",
        page_url=page_url,
    )


def sim_field_runtime_link(status: dict[str, object], *, page_url: str) -> dict[str, str]:
    return flux_link(
        title="Flux.sim.runtime",
        description="Flux.sim.runtime summarizes FieldAgent endpoints, simulated devices, tag counts, heartbeats, and Flux.serve snapshots verified by runtime evidence.",
        rows=[
            ("Endpoints", status["endpoint_count"]),
            ("Verified", status["verified_endpoint_count"]),
            ("Devices", status["enabled_device_count"]),
            ("Tags", status["enabled_tag_count"]),
        ],
        payload={"type": "flux.sim.runtime.surface.context", "runtime_status": status["summary"]},
        docs_path="apps/sim/",
        page_url=page_url,
    )


def sim_field_runtime_status() -> dict[str, object]:
    endpoints = list(FieldEndpoint.objects.prefetch_related("heartbeats").order_by("name"))
    runtime_counts = endpoint_runtime_counts({endpoint.id for endpoint in endpoints})
    now = timezone.now()
    snapshot_items = {
        snapshot.service_key.removeprefix("Flux.serve.field-agent:"): snapshot_status_item(
            snapshot,
            now=now,
            stale_after_seconds=settings.STALE_AFTER_SECONDS,
        )
        for snapshot in ServeServiceSnapshot.objects.filter(service_key__startswith="Flux.serve.field-agent:")
    }
    endpoint_items = []
    enabled_endpoint_count = 0
    stored_running_endpoint_count = 0
    verified_endpoint_count = 0
    enabled_device_count = 0
    enabled_tag_count = 0
    heartbeat_count = 0
    latest_seen_at = None
    for endpoint in endpoints:
        heartbeats = list(endpoint.heartbeats.all())
        heartbeat_count += len(heartbeats)
        latest_heartbeat = max((heartbeat.last_seen_at for heartbeat in heartbeats), default=None)
        seen_at = endpoint.last_seen_at or latest_heartbeat
        if seen_at is not None and (latest_seen_at is None or seen_at > latest_seen_at):
            latest_seen_at = seen_at
        endpoint_counts = runtime_counts.get(endpoint.id, {"device_count": 0, "tag_count": 0})
        endpoint_enabled_device_count = endpoint_counts["device_count"]
        endpoint_enabled_tag_count = endpoint_counts["tag_count"]
        enabled_device_count += endpoint_enabled_device_count
        enabled_tag_count += endpoint_enabled_tag_count
        if endpoint.enabled:
            enabled_endpoint_count += 1
        if endpoint.enabled and endpoint.status == FieldEndpoint.Status.RUNNING:
            stored_running_endpoint_count += 1
        snapshot_item = snapshot_items.get(endpoint.name)
        if (
            endpoint.enabled
            and snapshot_item is not None
            and snapshot_item["observed_state"] == ServeServiceSnapshot.ObservedState.HEALTHY
            and snapshot_item["severity"] == ServeServiceSnapshot.Severity.OK
        ):
            verified_endpoint_count += 1
        endpoint_items.append(
            {
                "endpoint": endpoint,
                "snapshot": snapshot_item,
                "enabled_device_count": endpoint_enabled_device_count,
                "enabled_tag_count": endpoint_enabled_tag_count,
                "latest_seen_at": seen_at,
            }
        )
    return {
        "state": "ok" if verified_endpoint_count else "warning" if enabled_endpoint_count else "offline",
        "endpoint_count": len(endpoints),
        "enabled_endpoint_count": enabled_endpoint_count,
        "running_endpoint_count": verified_endpoint_count,
        "stored_running_endpoint_count": stored_running_endpoint_count,
        "verified_endpoint_count": verified_endpoint_count,
        "enabled_device_count": enabled_device_count,
        "enabled_tag_count": enabled_tag_count,
        "heartbeat_count": heartbeat_count,
        "latest_seen_at": latest_seen_at,
        "endpoint_items": endpoint_items,
        "summary": {
            "endpoint_count": len(endpoints),
            "enabled_endpoint_count": enabled_endpoint_count,
            "stored_running_endpoint_count": stored_running_endpoint_count,
            "verified_endpoint_count": verified_endpoint_count,
            "enabled_device_count": enabled_device_count,
            "enabled_tag_count": enabled_tag_count,
            "heartbeat_count": heartbeat_count,
        },
    }


def sim_catalog_status() -> dict[str, int]:
    catalog_devices = DeviceConfig.objects.filter(source_provider_id__isnull=False)
    return {
        "provider_count": TagProvider.objects.count(),
        "sim_server_count": SimServer.objects.filter(tag_providers__isnull=False).distinct().count(),
        "opc_tag_count": TagNode.objects.filter(value_source="opc").exclude(path="").count(),
        "device_count": catalog_devices.count(),
        "enabled_device_count": catalog_devices.filter(enabled=True).count(),
        "unknown_status_device_count": catalog_devices.filter(source_status="").count()
        + catalog_devices.filter(source_status__iexact="unknown").count(),
        "runtime_endpoint_count": DeviceConfig.objects.filter(endpoint_id__isnull=False).values("endpoint_id").distinct().count(),
        "runtime_device_count": DeviceConfig.objects.filter(endpoint_id__isnull=False).count(),
        "runtime_tag_count": TagConfig.objects.filter(materialized=True, sim_device__endpoint_id__isnull=False).count(),
    }


def sim_platform_status() -> dict[str, str]:
    bridge = bridge_config()
    if bridge.last_test_ok:
        return {"label": "Trial", "state": "trial", "detail": "Ignition gateway reachable for simulation workflows."}
    if bridge.last_test_message:
        return {"label": "Unlicensed", "state": "unlicensed", "detail": bridge.last_test_message}
    return {"label": "Unlicensed", "state": "unlicensed", "detail": "Ignition gateway status has not been verified."}


@require_POST
def import_provider_json(request):
    upload = request.FILES.get("provider_json")
    provider = (request.POST.get("provider") or "").strip()
    if upload is None:
        messages.error(request, "Choose an Ignition provider JSON export to import.")
        return redirect("sim:index")
    provider_name = provider or upload.name.rsplit(".", 1)[0]
    job = enqueue_import_provider_json(content=upload.read(), provider_name=provider_name, source_name=upload.name)
    messages.success(request, f"Queued sim job #{job.id} to import provider JSON for {provider_name}.")
    return redirect("/sim/?card=sim-import&mode=configure")


@require_POST
def import_provider_ignition(request):
    source_provider = (request.POST.get("source_provider") or settings.FLUX_SIM_DEFAULT_TAG_PROVIDER).strip()
    provider = (request.POST.get("provider") or source_provider).strip()
    job = enqueue_import_provider_ignition(source_provider=source_provider, provider_name=provider)
    messages.success(
        request,
        f"Queued sim job #{job.id} to import Ignition provider {source_provider} as {provider}.",
    )
    return redirect("/sim/?card=sim-import&mode=configure")


@require_POST
def remove_ignition_sim_tags(request):
    provider = (request.POST.get("provider") or "").strip()
    folder_path = (request.POST.get("folder_path") or "").strip().strip("/")
    if not provider or not folder_path:
        messages.error(request, "Provider and folder path are required to remove simulated tags from Ignition.")
        return redirect("sim:index")
    job = enqueue_remove_ignition_tags(provider=provider, folder_path=folder_path)
    messages.success(request, f"Queued sim job #{job.id} to remove [{provider}]{folder_path} from Ignition.")
    return redirect("sim:index")


@require_POST
def set_imported_enabled(request):
    provider = request.POST.get("provider", "")
    path = request.POST.get("path", "")
    enabled = request.POST.get("enabled") == "1"
    set_imported_selection(provider, path, enabled=enabled)
    if request.headers.get("X-Flux-Async") == "1":
        return JsonResponse({"provider": provider, "path": path, "enabled": enabled})
    messages.success(request, f"{path} {'selected' if enabled else 'removed'} for provider {provider}.")
    return redirect(f"/sim/?card=sim-output&mode=detail&provider={provider}")


@require_POST
def set_imported_bulk(request):
    provider = request.POST.get("provider", "")
    count = replace_imported_selection(provider, request.POST.getlist("paths"))
    messages.success(request, f"{count} provider branch selection(s) saved for {provider}.")
    return redirect(f"/sim/?card=sim-output&mode=detail&provider={provider}")


@require_POST
def apply_selection(request):
    provider = (request.POST.get("provider") or "").strip()
    selection_paths = request.POST.getlist("selection_paths")
    selection_enabled = request.POST.getlist("selection_enabled")
    selection_modes = request.POST.getlist("selection_modes")
    selection_configs = request.POST.getlist("selection_configs")
    if len(selection_modes) < len(selection_paths):
        selection_modes.extend([""] * (len(selection_paths) - len(selection_modes)))
    if len(selection_configs) < len(selection_paths):
        selection_configs.extend([""] * (len(selection_paths) - len(selection_configs)))
    default_modes = default_modes_from_post(request.POST)
    if not provider:
        messages.error(request, "Choose a provider before applying simulator output.")
        return redirect("/sim/?card=sim-output&mode=detail")
    job = enqueue_apply_selection(
        provider=provider,
        selection_paths=selection_paths,
        selection_enabled=selection_enabled,
        selection_modes=selection_modes,
        selection_configs=selection_configs,
        default_modes=default_modes,
        rehydrate=request.POST.get("rehydrate") == "1",
    )
    messages.success(request, f"Queued sim job #{job.id} to apply simulator output for {provider}.")
    return redirect(f"/sim/?card=sim-output&mode=detail&provider={provider}")


def submitted_rehydration_paths(selection_paths: list[str], selection_enabled: list[str]) -> list[str] | None:
    if not selection_paths:
        return None
    return [
        path.strip("/")
        for path, enabled in zip(selection_paths, selection_enabled, strict=False)
        if enabled == "1" and path.strip("/")
    ]


def submitted_removed_paths(selection_paths: list[str], selection_enabled: list[str]) -> list[str]:
    return [
        path.strip("/")
        for path, enabled in zip(selection_paths, selection_enabled, strict=False)
        if enabled != "1" and path.strip("/")
    ]




def selected_paths(request):
    provider = request.GET.get("provider", "")
    return JsonResponse(
        {
            "provider": provider,
            "selected_source_paths": selected_source_paths(provider),
        }
    )


@require_GET
def provider_tree_children(request):
    provider = request.GET.get("provider", "")
    parent = request.GET.get("parent", "")
    query = request.GET.get("q", "")
    tree = search_provider_tree(provider, query) if query else base_provider_tree_children(provider, parent)
    if tree:
        hydrate_sim_output_tree(tree.nodes)
    return render(
        request,
        "sim/partials/imported_tag_tree.html",
        {"nodes": tree.nodes if tree else [], "provider": provider, "sim_output_mode_options": SIM_OUTPUT_MODE_OPTIONS},
    )


def field_config(request):
    return JsonResponse({"endpoints": enabled_endpoint_configs()})
