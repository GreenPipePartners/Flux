import os
import time

from django.core.management.base import BaseCommand, CommandError

from flux.sim.engine import configure_enabled_tags, run_history_backfill, write_due_tags
from flux.sim.models import SimHistoryBackfill


class Command(BaseCommand):
    help = "Run Flux simulation work through Fluxy."

    def add_arguments(self, parser):
        parser.add_argument("--base-url", default=os.getenv("FLUXY_BASE_URL", "http://localhost:8088/system/webdev/flux"))
        parser.add_argument("--token", default=os.getenv("FLUXY_TOKEN"))
        parser.add_argument("--project-location", default=os.getenv("FLUXY_PROJECT_LOCATION", "../ignition_flux_project"))
        parser.add_argument("--configure", action="store_true")
        parser.add_argument("--backfill", help="Run a named pending SimHistoryBackfill")
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--interval", type=float, default=0.5)

    def handle(self, *args, **options):
        try:
            import fluxy
        except ImportError as exc:
            raise CommandError("Install fluxy in this environment before running Flux Sim") from exc

        fx = fluxy.Fluxy(
            base_url=options["base_url"],
            token=options["token"],
            project_location=options["project_location"],
        )

        if options["configure"]:
            fx.deploy_webdev()
            fx.project.request_scan()
            results = configure_enabled_tags(fx)
            self.stdout.write("Configured %s simulated tag results" % len(results))

        if options["backfill"]:
            try:
                backfill = SimHistoryBackfill.objects.get(name=options["backfill"])
            except SimHistoryBackfill.DoesNotExist as exc:
                raise CommandError("Unknown SimHistoryBackfill: %s" % options["backfill"]) from exc
            written = run_history_backfill(fx, backfill)
            self.stdout.write("Wrote %s simulated history points" % written)
            if options["once"]:
                return

        while True:
            count = write_due_tags(fx)
            if count:
                self.stdout.write("Wrote %s simulated tag values" % count)
            if options["once"]:
                return
            time.sleep(options["interval"])
