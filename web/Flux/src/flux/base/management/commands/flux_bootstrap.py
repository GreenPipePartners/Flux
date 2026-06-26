from django.core.management.base import BaseCommand

from flux.bridge.services import bridge_config
from flux.opt.services import normalize_refresh_lanes
from flux.schematics.catalog import ensure_catalog
from runtime.models import RuntimeSchedulerConfig


class Command(BaseCommand):
    help = "Create required Flux runtime defaults after structural migrations."

    def add_arguments(self, parser):
        parser.add_argument(
            "--skip-schematics",
            action="store_true",
            help="Skip schematics reference catalog defaults.",
        )
        parser.add_argument(
            "--skip-bridge",
            action="store_true",
            help="Skip default Ignition bridge config creation.",
        )

    def handle(self, *args, **options):
        scheduler = RuntimeSchedulerConfig.default()
        lane_creates = normalize_refresh_lanes()
        self.stdout.write("runtime scheduler=%s" % scheduler.name)
        self.stdout.write("refresh lanes normalized; created=%s" % lane_creates)

        if not options["skip_schematics"]:
            ensure_catalog()
            self.stdout.write("schematics catalog ensured")

        if not options["skip_bridge"]:
            config = bridge_config()
            self.stdout.write("bridge config=%s" % config.name)
