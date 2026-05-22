from django.http import JsonResponse
from django.shortcuts import render

from flux.links import flux_link

from .models import FieldAgentHeartbeat, FieldDevice, FieldEndpoint, FieldNode, FieldTag
from .selectors import enabled_endpoint_configs


def index(request):
    endpoints = FieldEndpoint.objects.prefetch_related("nodes")
    devices = FieldDevice.objects.select_related("endpoint").prefetch_related("tags")
    field_tags = FieldTag.objects.select_related("device", "device__endpoint")
    nodes = FieldNode.objects.select_related("endpoint", "field_tag", "field_tag__device")
    heartbeats = FieldAgentHeartbeat.objects.select_related("endpoint").order_by("-last_seen_at")[:20]
    return render(
        request,
        "field/index.html",
        {
            "endpoints": endpoints,
            "devices": devices,
            "field_tags": field_tags,
            "nodes": nodes,
            "heartbeats": heartbeats,
            "field_link": flux_link(
                title="Flux Field Device Platform",
                description="Flux Field maps simulated values into FieldAgent OPC-UA endpoint/device/tag runtime interfaces.",
                rows=[("Endpoints", endpoints.count()), ("Devices", devices.count()), ("Field tags", field_tags.count()), ("Heartbeats", len(heartbeats))],
                payload={"type": "flux.field.platform.context"},
                docs_path="apps/sim/",
                page_url=request.build_absolute_uri(),
            ),
        },
    )


def config(request):
    return JsonResponse({"endpoints": enabled_endpoint_configs()})
