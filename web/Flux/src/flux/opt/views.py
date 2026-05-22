from django.shortcuts import render

from flux.links import flux_link

from .models import BrowseNode, OptimizationLease, OptimizedTagPath, RefreshLane


def index(request):
    lanes = RefreshLane.objects.order_by("priority", "interval_seconds")
    tag_path_count = OptimizedTagPath.objects.count()
    browse_node_count = BrowseNode.objects.count()
    active_lease_count = OptimizationLease.objects.filter(completed_at__isnull=True).count()
    return render(
        request,
        "opt/index.html",
        {
            "lanes": lanes,
            "tag_path_count": tag_path_count,
            "browse_node_count": browse_node_count,
            "active_lease_count": active_lease_count,
            "platform_link": flux_link(
                title="Flux Opt Platform",
                description="Flux Opt owns refresh lanes, browse discovery, demand leases, and cold-spot optimization.",
                rows=[("Optimized paths", tag_path_count), ("Browse nodes", browse_node_count), ("Active leases", active_lease_count)],
                payload={"type": "flux.opt.platform.context"},
                docs_path="apps/opt/",
                page_url=request.build_absolute_uri(),
            ),
            "lanes_link": flux_link(
                title="Flux Opt Refresh Lanes",
                description="Refresh lanes define polling intervals, priorities, batch limits, and enabled state for runtime sampling.",
                rows=[("Lane count", lanes.count())],
                payload={"type": "flux.opt.refresh_lanes.context"},
                docs_path="apps/opt/",
                page_url=request.build_absolute_uri(),
            ),
        },
    )
