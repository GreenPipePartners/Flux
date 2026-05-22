import os

from django.conf import settings
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
import fluxy

from dashboard.services import bridge_config
from flux.base.field_selectors import enabled_endpoint_configs
from flux.base.models import FieldDevice, FieldEndpoint, FieldTag, SimDevice, SimServer, TagNode, TagProvider
from flux.base.services import import_provider_from_fluxy, import_provider_json_bytes
from flux.links import flux_link

from .engine import delete_tag_branch
from .provider_tree import (
    build_imported_provider_tree,
    imported_provider_names,
    replace_imported_selection,
    selected_source_paths,
    set_imported_selection,
)


def index(request):
    imported_providers = imported_provider_names()
    selected_imported_provider = request.GET.get("provider", "")
    imported_tag_tree = build_imported_provider_tree(selected_imported_provider) if selected_imported_provider else None
    catalog_status = sim_catalog_status()
    platform_status = sim_platform_status()
    sim_link = flux_link(
        title="Flux Sim Platform",
        description="Flux Sim imports Ignition provider catalogs, maps devices/tags to Sim Servers, and materializes selected OPC tags into local simulator runtime.",
        rows=[
            ("Platform", platform_status["label"]),
            ("Providers", catalog_status["provider_count"]),
            ("Devices", catalog_status["device_count"]),
            ("OPC tags", catalog_status["opc_tag_count"]),
            ("Runtime devices", catalog_status["runtime_device_count"]),
            ("Runtime tags", catalog_status["runtime_tag_count"]),
        ],
        payload={"type": "flux.sim.platform.context", "catalog_status": catalog_status, "platform_status": platform_status},
        docs_path="apps/sim/",
        page_url=request.build_absolute_uri(),
    )
    return render(
        request,
        "sim/index.html",
        {
            "imported_providers": imported_providers,
            "selected_imported_provider": selected_imported_provider,
            "imported_tag_tree": imported_tag_tree,
            "catalog_status": catalog_status,
            "platform_status": platform_status,
            "sim_default_tag_provider": settings.FLUX_SIM_DEFAULT_TAG_PROVIDER,
            "sim_tag_providers": settings.FLUX_SIM_TAG_PROVIDERS,
            "sim_link": sim_link,
        },
    )


def sim_catalog_status() -> dict[str, int]:
    return {
        "provider_count": TagProvider.objects.count(),
        "sim_server_count": SimServer.objects.filter(tag_providers__isnull=False).distinct().count(),
        "opc_tag_count": TagNode.objects.filter(value_source="opc").exclude(path="").count(),
        "device_count": SimDevice.objects.count(),
        "enabled_device_count": SimDevice.objects.filter(enabled=True).count(),
        "unknown_status_device_count": SimDevice.objects.filter(source_status="").count()
        + SimDevice.objects.filter(source_status__iexact="unknown").count(),
        "runtime_endpoint_count": FieldEndpoint.objects.filter(
            devices__description__startswith="Materialized from SimDevice catalog"
        ).distinct().count(),
        "runtime_device_count": FieldDevice.objects.filter(description__startswith="Materialized from SimDevice catalog").count(),
        "runtime_tag_count": FieldTag.objects.filter(device__description__startswith="Materialized from SimDevice catalog").count(),
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
    try:
        content = upload.read()
        result = import_provider_json_bytes(
            content,
            provider_name=provider or upload.name.rsplit(".", 1)[0],
            source_name=upload.name,
        )
    except Exception as exc:
        messages.error(request, f"Provider JSON import failed: {exc}")
        return redirect("sim:index")
    messages.success(request, f"Imported {result.total_nodes} base tag node(s) for {result.provider.name}.")
    return redirect(f"/sim/?provider={result.provider.name}")


@require_POST
def import_provider_ignition(request):
    source_provider = (request.POST.get("source_provider") or settings.FLUX_SIM_DEFAULT_TAG_PROVIDER).strip()
    provider = (request.POST.get("provider") or source_provider).strip()
    base_url = os.getenv("FLUXY_BASE_URL", "http://localhost:8088/system/webdev/flux")
    token = os.getenv("FLUXY_TOKEN")
    try:
        fx = fluxy.Fluxy(base_url=base_url, token=token, tag_provider=source_provider)
        result = import_provider_from_fluxy(fx, source_provider=source_provider, provider_name=provider)
    except Exception as exc:
        messages.error(request, f"Ignition provider import failed: {exc}")
        return redirect("sim:index")
    messages.success(
        request,
        f"Imported {result.total_nodes} base tag node(s) from Ignition provider {source_provider} as {result.provider.name}.",
    )
    return redirect(f"/sim/?provider={result.provider.name}")


@require_POST
def remove_ignition_sim_tags(request):
    provider = (request.POST.get("provider") or "").strip()
    folder_path = (request.POST.get("folder_path") or "").strip().strip("/")
    if not provider or not folder_path:
        messages.error(request, "Provider and folder path are required to remove simulated tags from Ignition.")
        return redirect("sim:index")
    base_url = os.getenv("FLUXY_BASE_URL", "http://localhost:8088/system/webdev/flux")
    token = os.getenv("FLUXY_TOKEN")
    try:
        fx = fluxy.Fluxy(base_url=base_url, token=token, tag_provider=provider)
        deleted = delete_tag_branch(fx, provider=provider, folder_path=folder_path)
    except Exception as exc:
        messages.error(request, f"Ignition simulated tag removal failed: {exc}")
        return redirect("sim:index")
    messages.success(
        request,
        f"Requested deletion of {deleted} simulated tag branch(es) from Ignition for [{provider}]{folder_path}.",
    )
    return redirect("sim:index")


@require_POST
def set_imported_enabled(request):
    provider = request.POST.get("provider", "")
    path = request.POST.get("path", "")
    enabled = request.POST.get("enabled") == "1"
    set_imported_selection(provider, path, enabled=enabled)
    messages.success(request, f"{path} {'selected' if enabled else 'removed'} for provider {provider}.")
    return redirect(f"/sim/?provider={provider}")


@require_POST
def set_imported_bulk(request):
    provider = request.POST.get("provider", "")
    count = replace_imported_selection(provider, request.POST.getlist("paths"))
    messages.success(request, f"{count} provider branch selection(s) saved for {provider}.")
    return redirect(f"/sim/?provider={provider}")


def selected_paths(request):
    provider = request.GET.get("provider", "")
    return JsonResponse(
        {
            "provider": provider,
            "selected_source_paths": selected_source_paths(provider),
        }
    )


def field_config(request):
    return JsonResponse({"endpoints": enabled_endpoint_configs()})
