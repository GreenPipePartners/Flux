import os

from django.core.management.base import BaseCommand

from flux.sim.tag_data_ingest import ingest_live_tag_data_catalog


class Command(BaseCommand):
    help = "Import a live Ignition provider export and device list into Flux base simulation catalog tables."

    def add_arguments(self, parser):
        parser.add_argument("source_provider", help="Ignition provider name to export, for example default")
        parser.add_argument("--provider", help="Flux catalog provider name. Defaults to source_provider.")
        parser.add_argument("--base-url", default=os.getenv("FLUXY_BASE_URL", "http://localhost:8088/system/webdev/flux"))
        parser.add_argument("--token", default=os.getenv("FLUXY_TOKEN"))
        parser.add_argument("--skip-raw-config", action="store_true")

    def handle(self, *args, **options):
        import fluxy

        source_provider = options["source_provider"]
        fx = fluxy.Fluxy(base_url=options["base_url"], token=options["token"], tag_provider=source_provider)
        result = ingest_live_tag_data_catalog(
            fx,
            source_provider=source_provider,
            provider_name=options["provider"],
            keep_raw_config=not options["skip_raw_config"],
        )
        self.stdout.write(
            self.style.SUCCESS(
                "Imported %(devices)s live devices and %(tags)s device tags for %(provider)s "
                "(%(unknown)s unknown referenced devices, %(unused)s unreferenced live devices)"
                % {
                    "devices": result.device_count,
                    "tags": result.tag_count,
                    "provider": result.provider.name,
                    "unknown": result.unknown_device_count,
                    "unused": result.unreferenced_device_count,
                }
            )
        )
