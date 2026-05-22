from __future__ import annotations

from django.utils import timezone

from flux.base.models import FieldEndpoint

from .models import ServeCommand


START_SIM_SERVER = "start_sim_server"
STOP_SIM_SERVER = "stop_sim_server"


def request_sim_server_start(endpoint_id: int, *, requested_by=None) -> ServeCommand:
    endpoint = FieldEndpoint.objects.get(id=endpoint_id)
    endpoint.enabled = True
    endpoint.status = FieldEndpoint.Status.STARTING
    endpoint.last_error = "Start requested through Flux.serve."
    endpoint.save(update_fields=["enabled", "status", "last_error", "updated_at"])
    return ServeCommand.objects.create(
        command=START_SIM_SERVER,
        payload={"endpoint_id": endpoint.id, "endpoint_name": endpoint.name},
        requested_by=requested_by if getattr(requested_by, "is_authenticated", False) else None,
    )


def request_sim_server_stop(endpoint_id: int, *, requested_by=None) -> ServeCommand:
    endpoint = FieldEndpoint.objects.get(id=endpoint_id)
    endpoint.enabled = False
    endpoint.status = FieldEndpoint.Status.DISABLED
    endpoint.last_error = "Stop requested through Flux.serve."
    endpoint.save(update_fields=["enabled", "status", "last_error", "updated_at"])
    return ServeCommand.objects.create(
        command=STOP_SIM_SERVER,
        payload={"endpoint_id": endpoint.id, "endpoint_name": endpoint.name},
        requested_by=requested_by if getattr(requested_by, "is_authenticated", False) else None,
    )


def claim_requested_commands(*, service_name: str, limit: int = 50) -> list[ServeCommand]:
    now = timezone.now()
    claimed = []
    requested = list(
        ServeCommand.objects.filter(
            command__in=[START_SIM_SERVER, STOP_SIM_SERVER],
            status=ServeCommand.Status.REQUESTED,
        ).order_by("requested_at")[:limit]
    )
    for command in requested:
        updated = ServeCommand.objects.filter(
            id=command.id,
            status=ServeCommand.Status.REQUESTED,
        ).update(
            status=ServeCommand.Status.CLAIMED,
            claimed_at=now,
            result={"claimed_by": service_name},
        )
        if updated:
            command.status = ServeCommand.Status.CLAIMED
            command.claimed_at = now
            claimed.append(command)
    return claimed


def complete_command(command: ServeCommand, *, result: dict | None = None) -> None:
    command.status = ServeCommand.Status.COMPLETED
    command.completed_at = timezone.now()
    command.result = result or {}
    command.error = ""
    command.save(update_fields=["status", "completed_at", "result", "error"])


def fail_command(command: ServeCommand, *, error: str) -> None:
    command.status = ServeCommand.Status.FAILED
    command.completed_at = timezone.now()
    command.error = error
    command.save(update_fields=["status", "completed_at", "error"])


def apply_claimed_command(command: ServeCommand) -> dict:
    endpoint_id = command.payload.get("endpoint_id")
    if not endpoint_id:
        raise ValueError("Serve command missing endpoint_id")
    endpoint = FieldEndpoint.objects.get(id=endpoint_id)
    if command.command == START_SIM_SERVER:
        endpoint.enabled = True
        endpoint.status = FieldEndpoint.Status.STARTING
        endpoint.last_error = ""
        endpoint.save(update_fields=["enabled", "status", "last_error", "updated_at"])
        return {"endpoint_id": endpoint.id, "endpoint_name": endpoint.name, "enabled": True}
    if command.command == STOP_SIM_SERVER:
        endpoint.enabled = False
        endpoint.status = FieldEndpoint.Status.DISABLED
        endpoint.last_error = ""
        endpoint.save(update_fields=["enabled", "status", "last_error", "updated_at"])
        return {"endpoint_id": endpoint.id, "endpoint_name": endpoint.name, "enabled": False}
    raise ValueError("Unsupported serve command: %s" % command.command)
