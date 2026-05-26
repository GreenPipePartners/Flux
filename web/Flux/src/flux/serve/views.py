from django.contrib import messages
from django.conf import settings
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from flux.links import flux_link
from flux.pagination import table_page
from flux.web_pulse import display_pulse_context, latest_timestamp

from .models import ServeCommand, ServeHeartbeat, ServeServiceSnapshot
from .monitor import service_snapshot_status
from .status import serve_heartbeat_status


def index(request):
    heartbeats = ServeHeartbeat.objects.order_by("service_name", "instance_id")
    snapshots = ServeServiceSnapshot.objects.order_by("category", "service_key")
    commands = ServeCommand.objects.select_related("requested_by").order_by("-requested_at")
    full_status = serve_heartbeat_status(heartbeats, stale_after_seconds=settings.STALE_AFTER_SECONDS)
    full_snapshot_status = service_snapshot_status(snapshots, stale_after_seconds=settings.STALE_AFTER_SECONDS)
    pulse = serve_pulse_context(full_snapshot_status, full_status)
    snapshot_page = table_page(request, full_snapshot_status["items"], "snapshots_page")
    heartbeat_page = table_page(request, full_status["items"], "heartbeats_page")
    commands_page = table_page(request, commands, "commands_page")
    status = {**full_status, "items": list(heartbeat_page.object_list)}
    snapshot_status = {**full_snapshot_status, "items": list(snapshot_page.object_list)}
    return render(
        request,
        "serve/index.html",
        {
            "heartbeats": heartbeats,
            "snapshots": snapshots,
            "commands": commands_page.object_list,
            "snapshot_page": snapshot_page,
            "heartbeat_page": heartbeat_page,
            "commands_page": commands_page,
            "commands_total_count": commands.count(),
            "serve_status": status,
            "snapshot_status": snapshot_status,
            "stale_after_seconds": settings.STALE_AFTER_SECONDS,
            "platform_link": flux_link(
                title="Flux Serve Platform",
                description="Service snapshots are Flux.serve's observed health view; heartbeat rows remain process self-reports.",
                rows=[
                    ("Healthy snapshots", full_snapshot_status["ok_count"]),
                    ("Warning snapshots", full_snapshot_status["warning_count"]),
                    ("Error snapshots", full_snapshot_status["error_count"]),
                    ("Running heartbeats", full_status["running_count"]),
                ],
                payload={
                    "type": "flux.serve.service_snapshots.context",
                    "snapshots": service_snapshot_payload(full_snapshot_status),
                    "heartbeats": full_status,
                },
                docs_path="apps/serve/",
                page_url=request.build_absolute_uri(),
            ),
            "commands_link": flux_link(
                title="Flux Serve Logs",
                description="Recent logs are service command records claimed and applied by Flux Serve workers or supervisors.",
                rows=[("Recent logs", commands.count())],
                payload={"type": "flux.serve.logs.context"},
                docs_path="apps/serve/",
                page_url=request.build_absolute_uri(),
            ),
            "flux_web_pulse": pulse,
        },
    )


def serve_pulse_context(snapshot_status: dict, heartbeat_status: dict) -> dict:
    if snapshot_status["total_count"]:
        return display_pulse_context(
            source_label="Flux.serve service snapshots",
            last_backend_at=latest_timestamp(item["last_checked_at"] for item in snapshot_status["items"]),
            state=snapshot_status["state"],
            detail="%s healthy · %s warning · %s error"
            % (snapshot_status["ok_count"], snapshot_status["warning_count"], snapshot_status["error_count"]),
        )
    return display_pulse_context(
        source_label="Flux.serve heartbeats",
        last_backend_at=latest_timestamp(item["heartbeat"].last_seen_at for item in heartbeat_status["items"]),
        state=heartbeat_status["state"],
        detail="%s running · %s stale · %s error"
        % (heartbeat_status["running_count"], heartbeat_status["stale_count"], heartbeat_status["error_count"]),
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
