import sys
from pathlib import Path

from django.core.management.base import BaseCommand

REPO_ROOT = Path(__file__).resolve().parents[7]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from serve.worker import run_worker_heartbeat  # noqa: E402


class Command(BaseCommand):
    help = "Run the Flux worker heartbeat loop. Optimization work will attach here."

    def add_arguments(self, parser):
        parser.add_argument("--service-name", default="flux-worker")
        parser.add_argument("--interval", type=float, default=5.0)
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        run_worker_heartbeat(
            service_name=options["service_name"],
            interval=options["interval"],
            once=options["once"],
            stdout=self.stdout,
        )
