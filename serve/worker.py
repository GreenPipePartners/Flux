from __future__ import annotations

import os
import platform
import socket
import time
from typing import Callable
from uuid import uuid4

from django.utils import timezone

from flux.serve.models import ServeHeartbeat
from flux.status.models import LatestStatus
from flux.status.services import record_worker_status


def current_job_value(value: str) -> str:
    return value[:255]


def linux_platform_name() -> str:
    system = platform.system().lower()
    if system != "linux":
        raise RuntimeError("Flux workers require Linux; detected %s" % (system or "unknown"))
    return ServeHeartbeat.Platform.LINUX


def run_worker_heartbeat(
    *,
    service_name: str = "flux-worker",
    interval: float = 5.0,
    once: bool = False,
    stdout=None,
    job_name: str = "heartbeat",
    job: Callable[[], object] | None = None,
) -> None:
    instance_id = "%s-%s" % (socket.gethostname(), uuid4().hex[:8])
    platform_name = linux_platform_name()
    heartbeat, _created = ServeHeartbeat.objects.get_or_create(
        service_name=service_name,
        instance_id=instance_id,
        defaults={
            "platform": platform_name,
            "status": ServeHeartbeat.Status.RUNNING,
            "pid": os.getpid(),
            "started_at": timezone.now(),
            "last_seen_at": timezone.now(),
            "current_job": current_job_value(job_name),
        },
    )

    while True:
        heartbeat.status = ServeHeartbeat.Status.RUNNING
        heartbeat.pid = os.getpid()
        heartbeat.last_seen_at = timezone.now()
        heartbeat.current_job = current_job_value(job_name)
        heartbeat.save(update_fields=["status", "pid", "last_seen_at", "current_job"])
        record_worker_status(
            service_name=service_name,
            instance_id=instance_id,
            observed_state=LatestStatus.ObservedState.OK,
            severity=LatestStatus.Severity.OK,
            summary="Worker heartbeat is running.",
            last_seen_at=heartbeat.last_seen_at,
            evidence={"pid": heartbeat.pid, "job": heartbeat.current_job},
        )
        try:
            result = job() if job is not None else None
        except Exception as exc:
            heartbeat.status = ServeHeartbeat.Status.ERROR
            heartbeat.current_job = current_job_value("%s failed: %s" % (job_name, exc))
            heartbeat.last_error = str(exc)
            heartbeat.last_seen_at = timezone.now()
            heartbeat.save(update_fields=["status", "current_job", "last_error", "last_seen_at"])
            record_worker_status(
                service_name=service_name,
                instance_id=instance_id,
                observed_state=LatestStatus.ObservedState.ERROR,
                severity=LatestStatus.Severity.ERROR,
                summary="Worker job failed.",
                detail=str(exc),
                last_seen_at=heartbeat.last_seen_at,
                evidence={"pid": heartbeat.pid, "job": heartbeat.current_job, "error": str(exc)},
            )
            if stdout is not None:
                stdout.write("%s %s %s failed: %s" % (service_name, job_name, instance_id, exc))
            if once:
                return
            time.sleep(interval)
            continue
        if stdout is not None:
            suffix = "" if result is None else " %s" % result
            stdout.write("%s %s %s%s" % (service_name, job_name, instance_id, suffix))
        if once:
            return
        time.sleep(interval)
