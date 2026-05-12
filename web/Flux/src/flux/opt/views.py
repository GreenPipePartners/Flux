from django.shortcuts import render

from .models import BrowseNode, OptimizationLease, OptimizedTagPath, RefreshLane


def index(request):
    return render(
        request,
        "opt/index.html",
        {
            "lanes": RefreshLane.objects.order_by("priority", "interval_seconds"),
            "tag_path_count": OptimizedTagPath.objects.count(),
            "browse_node_count": BrowseNode.objects.count(),
            "active_lease_count": OptimizationLease.objects.filter(completed_at__isnull=True).count(),
        },
    )
