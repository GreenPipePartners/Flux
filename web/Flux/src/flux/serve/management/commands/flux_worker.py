import sys
import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

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
        parser.add_argument("--plane-samples", action="store_true")
        parser.add_argument("--nav-well-live", action="store_true")
        parser.add_argument("--nav-well-limit", type=int, default=None)
        parser.add_argument("--trace-profile-key", default="")
        parser.add_argument("--base-url", default=os.getenv("FLUXY_BASE_URL", "http://localhost:8088/system/webdev/flux"))
        parser.add_argument("--token", default=os.getenv("FLUXY_TOKEN"))

    def handle(self, *args, **options):
        job = None
        job_name = "heartbeat"
        if options["plane_samples"] or options["nav_well_live"]:
            try:
                import fluxy
            except ImportError as exc:
                raise CommandError("Install fluxy before running the trace worker") from exc

            fx = fluxy.Fluxy(base_url=options["base_url"], token=options["token"])
            profile_key = options["trace_profile_key"] or None

            if options["nav_well_live"]:
                from flux.chart.providers.nav_wells import sync_nav_well_plane_samples, update_nav_well_live_values

                def job():
                    updated = update_nav_well_live_values(fx, limit=options["nav_well_limit"])
                    result = sync_nav_well_plane_samples(fx, limit=options["nav_well_limit"], force=True)
                    return "updated=%s profiles=%s signals=%s points=%s" % (updated, result.profile_count, result.signal_count, result.point_count)

                job_name = "nav_well_live"
            else:
                from flux.chart.cache import sync_plane_samples

                def job():
                    result = sync_plane_samples(fx, profile_key=profile_key)
                    return "profiles=%s signals=%s points=%s" % (result.profile_count, result.signal_count, result.point_count)

                job_name = "plane_samples"

        run_worker_heartbeat(
            service_name=options["service_name"],
            interval=options["interval"],
            once=options["once"],
            stdout=self.stdout,
            job_name=job_name,
            job=job,
        )
