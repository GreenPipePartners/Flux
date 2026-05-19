from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from flux.sim.tag_data_ingest import ingest_tag_data_catalog


class Command(BaseCommand):
    help = "Import a tag_data provider export and device inventory into Flux base simulation catalog tables."

    def add_arguments(self, parser):
        parser.add_argument("provider", help="Provider name to import, for example Tag_02")
        parser.add_argument("--devices", required=True, help="Path to device inventory text file")
        parser.add_argument("--tags", required=True, help="Path to Ignition provider JSON export")
        parser.add_argument("--skip-raw-config", action="store_true")

    def handle(self, *args, **options):
        devices_path = Path(options["devices"])
        tags_path = Path(options["tags"])
        if not devices_path.exists():
            raise CommandError("Device inventory file does not exist: %s" % devices_path)
        if not tags_path.exists():
            raise CommandError("Tag export file does not exist: %s" % tags_path)

        result = ingest_tag_data_catalog(
            provider_name=options["provider"],
            devices_path=devices_path,
            tags_path=tags_path,
            keep_raw_config=not options["skip_raw_config"],
        )
        self.stdout.write(
            self.style.SUCCESS(
                "Imported %(devices)s devices and %(tags)s device tags for %(provider)s "
                "(%(unknown)s unknown referenced devices, %(unused)s unreferenced inventory devices)"
                % {
                    "devices": result.device_count,
                    "tags": result.tag_count,
                    "provider": result.provider.name,
                    "unknown": result.unknown_device_count,
                    "unused": result.unreferenced_device_count,
                }
            )
        )
