from __future__ import annotations

import os
import platform
import socket
import time
from typing import Callable
from uuid import uuid4

from django.utils import timezone

from flux.serve.models import ServeHeartbeat


def current_job_value(value: str) -> str:
    return value[:255]


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
    system = platform.system().lower()
    platform_name = system if system in {"windows", "linux"} else ServeHeartbeat.Platform.UNKNOWN
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
        try:
            result = job() if job is not None else None
        except Exception as exc:
            heartbeat.status = ServeHeartbeat.Status.ERROR
            heartbeat.current_job = current_job_value("%s failed: %s" % (job_name, exc))
            heartbeat.last_error = str(exc)
            heartbeat.last_seen_at = timezone.now()
            heartbeat.save(update_fields=["status", "current_job", "last_error", "last_seen_at"])
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
