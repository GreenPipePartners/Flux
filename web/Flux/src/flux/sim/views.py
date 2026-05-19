from dataclasses import dataclass, field
import json
import os

from django.contrib import messages
from django.http import JsonResponse
from django.db.models import QuerySet
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
import fluxy
from django.conf import settings
from flux.base.models import FieldDevice, FieldEndpoint, FieldTag, SimDevice, SimDeviceTag, TagNode, TagProvider
from flux.base.services import import_provider_from_fluxy, import_provider_json_bytes
from flux.base.field_selectors import enabled_endpoint_configs

from .engine import delete_tag_branch
from .models import SimHistoryBackfill, SimSchedule, SimTag
from .provider_tree import (
    build_imported_provider_tree,
    imported_provider_names,
    replace_imported_selection,
    selected_source_paths,
    set_imported_selection,
)


@dataclass
class TagTreeFolder:
    name: str
    path: str
    children: dict[str, "TagTreeFolder"] = field(default_factory=dict)
    tags: list[SimTag] = field(default_factory=list)
    enabled_count: int = 0
    total_count: int = 0

    @property
    def children_list(self) -> list["TagTreeFolder"]:
        return sorted(self.children.values(), key=lambda folder: folder.name.lower())


@dataclass
class TagTreeProvider:
    name: str
    folders: dict[str, TagTreeFolder] = field(default_factory=dict)
    root_tags: list[SimTag] = field(default_factory=list)
    enabled_count: int = 0
    total_count: int = 0

    @property
    def folders_list(self) -> list[TagTreeFolder]:
        return sorted(self.folders.values(), key=lambda folder: folder.name.lower())


def index(request):
    tags = list(SimTag.objects.select_related("schedule"))
    imported_providers = imported_provider_names()
    selected_imported_provider = request.GET.get("provider") or (imported_providers[0] if imported_providers else "")
    return render(
        request,
        "sim/index.html",
        {
            "schedules": SimSchedule.objects.prefetch_related("tags"),
            "tags": tags,
            "tag_tree": build_tag_tree(tags),
            "imported_providers": imported_providers,
            "selected_imported_provider": selected_imported_provider,
            "imported_tag_tree": build_imported_provider_tree(selected_imported_provider),
            "catalog_status": sim_catalog_status(),
            "sim_default_tag_provider": settings.FLUX_SIM_DEFAULT_TAG_PROVIDER,
            "sim_tag_providers": settings.FLUX_SIM_TAG_PROVIDERS,
            "backfills": SimHistoryBackfill.objects.order_by("-created_at")[:10],
            "behavior_choices": SimTag.Behavior.choices,
        },
    )


def sim_catalog_status() -> dict[str, int]:
    referenced_paths = SimDeviceTag.objects.values("provider_id", "source_path")
    referenced_by_provider: dict[int, set[str]] = {}
    for row in referenced_paths:
        referenced_by_provider.setdefault(row["provider_id"], set()).add(row["source_path"])

    unreferenced_opc_tag_count = 0
    for provider in TagProvider.objects.all():
        referenced = referenced_by_provider.get(provider.id, set())
        provider_opc_paths = TagNode.objects.filter(provider=provider, value_source="opc").exclude(path="").values_list("path", flat=True)
        unreferenced_opc_tag_count += sum(1 for path in provider_opc_paths if path not in referenced)

    return {
        "provider_count": TagProvider.objects.count(),
        "node_count": TagNode.objects.count(),
        "opc_tag_count": TagNode.objects.filter(value_source="opc").exclude(path="").count(),
        "device_count": SimDevice.objects.count(),
        "enabled_device_count": SimDevice.objects.filter(enabled=True).count(),
        "tag_count": SimDeviceTag.objects.count(),
        "enabled_tag_count": SimDeviceTag.objects.filter(enabled=True).count(),
        "unknown_status_device_count": SimDevice.objects.filter(source_status="").count()
        + SimDevice.objects.filter(source_status__iexact="unknown").count(),
        "unreferenced_opc_tag_count": unreferenced_opc_tag_count,
        "runtime_endpoint_count": FieldEndpoint.objects.filter(name__startswith="sim-").count(),
        "runtime_device_count": FieldDevice.objects.filter(description__startswith="Materialized from SimDevice catalog").count(),
        "runtime_tag_count": FieldTag.objects.filter(device__description__startswith="Materialized from SimDevice catalog").count(),
    }


@require_POST
def set_enabled(request):
    scope = request.POST.get("scope", "")
    enabled = request.POST.get("enabled") == "1"
    tags = tags_for_scope(scope, request.POST)
    count = tags.update(enabled=enabled)
    state = "enabled" if enabled else "disabled"
    messages.success(request, f"{count} simulated tag(s) {state}.")
    return redirect("sim:index")


@require_POST
def set_behavior(request):
    tag = get_object_or_404(SimTag, id=request.POST.get("tag_id"))
    behavior = request.POST.get("behavior") or SimTag.Behavior.IMMEDIATE
    valid_behaviors = {choice[0] for choice in SimTag.Behavior.choices}
    if behavior not in valid_behaviors:
        messages.error(request, "Unknown simulated tag behavior: %s" % behavior)
        return redirect("sim:index")
    try:
        response_delay_seconds = max(int(request.POST.get("response_delay_seconds") or 0), 0)
    except ValueError:
        messages.error(request, "Response delay must be a whole number of seconds.")
        return redirect("sim:index")

    tag.behavior = behavior
    tag.response_delay_seconds = response_delay_seconds if behavior == SimTag.Behavior.SLOW_RESPONSE else 0
    if behavior == SimTag.Behavior.WRITE_TO_OTHER_TAG_RESPONSE:
        mode_config = write_to_other_mode_config(request.POST)
        if mode_config is None:
            messages.error(request, "Response tag path is required for write-to-other behavior.")
            return redirect("sim:index")
        tag.mode_config = mode_config
    else:
        tag.mode_config = None
    tag.pending_value = None
    tag.pending_apply_at = None
    tag.save(update_fields=["behavior", "response_delay_seconds", "mode_config", "pending_value", "pending_apply_at"])
    messages.success(request, "Updated simulated behavior for %s." % tag.tag_path)
    return redirect("sim:index")


def parse_optional_json_value(value: str):
    return None if value == "" else parse_json_value(value)


def parse_json_value(value: str):
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def write_to_other_mode_config(post_data) -> dict | None:
    response_tag_path = (post_data.get("response_tag_path") or "").strip()
    if not response_tag_path:
        return None
    config = {
        "response_tag_path": response_tag_path,
        "response_value": parse_json_value(post_data.get("response_value", "")),
    }
    trigger_value = parse_optional_json_value(post_data.get("trigger_value", ""))
    if trigger_value is not None:
        config["trigger_value"] = trigger_value
    return config


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


def tags_for_scope(scope: str, post) -> QuerySet[SimTag]:
    tags = SimTag.objects.all()
    if scope == "provider":
        return tags.filter(provider=post.get("provider", ""))
    if scope == "folder":
        provider = post.get("provider", "")
        folder_path = normalize_folder_path(post.get("folder_path", ""))
        return tags.filter(provider=provider).filter(folder_path=folder_path) | tags.filter(
            provider=provider,
            folder_path__startswith=f"{folder_path}/",
        )
    if scope == "tag":
        return tags.filter(id=post.get("tag_id"))
    return tags.none()


def build_tag_tree(tags: list[SimTag]) -> list[TagTreeProvider]:
    providers: dict[str, TagTreeProvider] = {}
    for tag in tags:
        provider = providers.setdefault(tag.provider, TagTreeProvider(name=tag.provider))
        provider.total_count += 1
        if tag.enabled:
            provider.enabled_count += 1

        folder_path = normalize_folder_path(tag.folder_path)
        if not folder_path:
            provider.root_tags.append(tag)
            continue

        folders = provider.folders
        parts = folder_path.split("/")
        for index, part in enumerate(parts):
            path = "/".join(parts[: index + 1])
            folder = folders.setdefault(part, TagTreeFolder(name=part, path=path))
            folder.total_count += 1
            if tag.enabled:
                folder.enabled_count += 1
            folders = folder.children
        folder.tags.append(tag)

    return sorted(providers.values(), key=lambda provider: provider.name.lower())


def normalize_folder_path(folder_path: str) -> str:
    return folder_path.strip("/")
