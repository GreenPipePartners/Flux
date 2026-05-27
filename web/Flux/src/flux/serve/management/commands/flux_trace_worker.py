import os

from django.core.management.base import BaseCommand, CommandError

from serve.worker import run_worker_heartbeat


class Command(BaseCommand):
    help = "Run the dedicated Flux Chart Plane sample worker."

    def add_arguments(self, parser):
        parser.add_argument("--service-name", default="flux-charts-worker")
        parser.add_argument("--interval", type=float, default=60.0)
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--profile-key", default="")
        parser.add_argument("--base-url", default=os.getenv("FLUXY_BASE_URL", "http://localhost:8088/system/webdev/flux"))
        parser.add_argument("--token", default=os.getenv("FLUXY_TOKEN"))

    def handle(self, *args, **options):
        try:
            import fluxy
        except ImportError as exc:
            raise CommandError("Install fluxy before running the charts worker") from exc

        fx = fluxy.Fluxy(base_url=options["base_url"], token=options["token"])

        from flux.chart.cache import sync_plane_samples

        profile_key = options["profile_key"] or None

        def job():
            result = sync_plane_samples(fx, profile_key=profile_key)
            return "plane_samples profiles=%s signals=%s points=%s" % (
                result.profile_count,
                result.signal_count,
                result.point_count,
            )

        job_name = "plane_samples"

        run_worker_heartbeat(
            service_name=options["service_name"],
            interval=options["interval"],
            once=options["once"],
            stdout=self.stdout,
            job_name=job_name,
            job=job,
        )
