import os
import platform
import socket
import time
from uuid import uuid4

from django.core.management.base import BaseCommand
from django.utils import timezone

from flux.serve.models import ServeHeartbeat


class Command(BaseCommand):
    help = "Run the Flux worker heartbeat loop. Optimization work will attach here."

    def add_arguments(self, parser):
        parser.add_argument("--service-name", default="flux-worker")
        parser.add_argument("--interval", type=float, default=5.0)
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        instance_id = "%s-%s" % (socket.gethostname(), uuid4().hex[:8])
        service_name = options["service_name"]
        interval = options["interval"]

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
            self.stdout.write("%s heartbeat %s" % (service_name, instance_id))
            if options["once"]:
                return
            time.sleep(interval)
