from __future__ import annotations

import os
import platform
import socket
import time
from uuid import uuid4

from django.utils import timezone

from flux.serve.models import ServeHeartbeat


def run_worker_heartbeat(*, service_name: str = "flux-worker", interval: float = 5.0, once: bool = False, stdout=None) -> None:
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
            "current_job": "heartbeat",
        },
    )

    while True:
        heartbeat.status = ServeHeartbeat.Status.RUNNING
        heartbeat.pid = os.getpid()
        heartbeat.last_seen_at = timezone.now()
        heartbeat.current_job = "heartbeat"
        heartbeat.save(update_fields=["status", "pid", "last_seen_at", "current_job"])
        if stdout is not None:
            stdout.write("%s heartbeat %s" % (service_name, instance_id))
        if once:
            return
        time.sleep(interval)
