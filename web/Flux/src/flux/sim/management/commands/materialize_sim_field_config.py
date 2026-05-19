from django.core.management.base import BaseCommand

from flux.sim.field_bridge import materialize_enabled_sim_devices


class Command(BaseCommand):
    help = "Materialize enabled SimDevice catalog rows into FieldAgent runtime configuration."

    def add_arguments(self, parser):
        parser.add_argument(
            "--provider", help="Optional provider name to materialize, for example Tag_02"
        )

    def handle(self, *args, **options):
        result = materialize_enabled_sim_devices(provider_name=options["provider"])
        self.stdout.write(
            self.style.SUCCESS(
                "Materialized %(endpoints)s endpoints, %(devices)s devices, and %(tags)s tags"
                % {
                    "endpoints": result.endpoint_count,
                    "devices": result.device_count,
                    "tags": result.tag_count,
                }
            )
        )
