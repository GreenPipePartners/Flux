from django.http import JsonResponse
from django.shortcuts import render

from .models import FieldAgentHeartbeat, FieldDevice, FieldEndpoint, FieldNode, FieldTag
from .selectors import enabled_endpoint_configs


def index(request):
    return render(
        request,
        "field/index.html",
        {
            "endpoints": FieldEndpoint.objects.prefetch_related("nodes"),
            "devices": FieldDevice.objects.select_related("endpoint").prefetch_related("tags"),
            "field_tags": FieldTag.objects.select_related("device", "device__endpoint"),
            "nodes": FieldNode.objects.select_related("endpoint", "field_tag", "field_tag__device"),
            "heartbeats": FieldAgentHeartbeat.objects.select_related("endpoint").order_by("-last_seen_at")[:20],
        },
    )


def config(request):
    return JsonResponse({"endpoints": enabled_endpoint_configs()})
