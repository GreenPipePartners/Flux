from django.core.management.base import BaseCommand

from flux.sim.jobs import run_next_sim_job
from serve.worker import run_worker_heartbeat


class Command(BaseCommand):
    help = "Run queued Flux.sim jobs outside request/response paths."

    def add_arguments(self, parser):
        parser.add_argument("--service-name", default="flux-sim-worker")
        parser.add_argument("--interval", type=float, default=5.0)
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        run_worker_heartbeat(
            service_name=options["service_name"],
            interval=options["interval"],
            once=options["once"],
            stdout=self.stdout,
            job_name="sim_jobs",
            job=run_next_sim_job,
        )
