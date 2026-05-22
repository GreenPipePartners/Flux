from django.contrib import messages
from django.conf import settings
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from flux.links import flux_link

from .models import ServeCommand, ServeHeartbeat, ServeServiceSnapshot
from .monitor import service_snapshot_status
from .status import serve_heartbeat_status


def index(request):
    heartbeats = ServeHeartbeat.objects.order_by("service_name", "instance_id")
    snapshots = ServeServiceSnapshot.objects.order_by("category", "service_key")
    commands = ServeCommand.objects.select_related("requested_by").order_by("-requested_at")[:20]
    status = serve_heartbeat_status(heartbeats, stale_after_seconds=settings.STALE_AFTER_SECONDS)
    snapshot_status = service_snapshot_status(snapshots, stale_after_seconds=settings.STALE_AFTER_SECONDS)
    return render(
        request,
        "serve/index.html",
        {
            "heartbeats": heartbeats,
            "snapshots": snapshots,
            "commands": commands,
            "serve_status": status,
            "snapshot_status": snapshot_status,
            "stale_after_seconds": settings.STALE_AFTER_SECONDS,
            "platform_link": flux_link(
                title="Flux Serve Platform",
                description="Service snapshots are Flux.serve's observed health view; heartbeat rows remain process self-reports.",
                rows=[
                    ("Healthy snapshots", snapshot_status["ok_count"]),
                    ("Warning snapshots", snapshot_status["warning_count"]),
                    ("Error snapshots", snapshot_status["error_count"]),
                    ("Running heartbeats", status["running_count"]),
                ],
                payload={
                    "type": "flux.serve.service_snapshots.context",
                    "snapshots": service_snapshot_payload(snapshot_status),
                    "heartbeats": status,
                },
                docs_path="apps/serve/",
                page_url=request.build_absolute_uri(),
            ),
            "commands_link": flux_link(
                title="Flux Serve Logs",
                description="Recent logs are service command records claimed and applied by Flux Serve workers or supervisors.",
                rows=[("Recent logs", commands.count() if hasattr(commands, "count") else len(commands))],
                payload={"type": "flux.serve.logs.context"},
                docs_path="apps/serve/",
                page_url=request.build_absolute_uri(),
            ),
        },
    )


def service_snapshot_payload(snapshot_status: dict) -> dict:
    return {
        key: value
        for key, value in snapshot_status.items()
        if key != "items"
    } | {
        "items": [
            {
                "service_key": item["service_key"],
                "category": item["category"],
                "desired_state": item["desired_state"],
                "observed_state": item["observed_state"],
                "severity": item["severity"],
                "summary": item["summary"],
                "age_seconds": item["age_seconds"],
            }
            for item in snapshot_status["items"]
        ]
    }


@require_POST
def delete_heartbeat(request, heartbeat_id):
    heartbeat = get_object_or_404(ServeHeartbeat, id=heartbeat_id)
    status = serve_heartbeat_status([heartbeat], stale_after_seconds=settings.STALE_AFTER_SECONDS)["items"][0]
    if status["running"]:
        messages.error(request, "Cannot delete a fresh running heartbeat.")
        return redirect("serve:index")
    label = "%s / %s" % (heartbeat.service_name, heartbeat.instance_id)
    heartbeat.delete()
    messages.success(request, "Deleted stale service heartbeat %s." % label)
    return redirect("serve:index")


@require_POST
def delete_stale_heartbeats(request):
    heartbeats = list(ServeHeartbeat.objects.order_by("service_name", "instance_id"))
    status = serve_heartbeat_status(heartbeats, stale_after_seconds=settings.STALE_AFTER_SECONDS)
    stale_ids = [item["heartbeat"].id for item in status["items"] if item["stale"] and not item["running"]]
    deleted, _details = ServeHeartbeat.objects.filter(id__in=stale_ids).delete()
    messages.success(request, "Deleted %s stale service heartbeat(s)." % deleted)
    return redirect("serve:index")
