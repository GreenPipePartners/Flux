from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from flux_sim.provider_import import import_provider_export


class Command(BaseCommand):
    help = "Import an Ignition tag provider export into the standalone Flux Sim SQLite database."

    def add_arguments(self, parser):
        parser.add_argument("source", help="Path to an Ignition tag provider JSON export")
        parser.add_argument("--provider", default="ACM02", help="Target simulated provider name")
        parser.add_argument(
            "--database",
            "-d",
            default=str(default_sim_database_path()),
            help="Standalone Flux Sim SQLite database path",
        )
        parser.add_argument("--batch-size", type=int, default=1000)
        parser.add_argument(
            "--skip-raw-config",
            action="store_true",
            help="Do not store each tag's raw Ignition config payload",
        )

    def handle(self, *args, **options):
        try:
            result = import_provider_export(
                options["source"],
                options["database"],
                provider_name=options["provider"],
                batch_size=options["batch_size"],
                keep_raw_config=not options["skip_raw_config"],
            )
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                "Imported %(total)s nodes for provider %(provider)s "
                "(%(folders)s folders, %(atomic)s atomic tags, %(udts)s UDT instances, %(types)s UDT types)"
                % {
                    "total": result.total_nodes,
                    "provider": result.provider_name,
                    "folders": result.counts.get("Folder", 0),
                    "atomic": result.counts.get("AtomicTag", 0),
                    "udts": result.counts.get("UdtInstance", 0),
                    "types": result.counts.get("UdtType", 0),
                }
            )
        )
        self.stdout.write(f"Database: {options['database']}")


def default_sim_database_path() -> Path:
    return settings.BASE_DIR.parents[1] / "sim" / "flux-sim.db"
