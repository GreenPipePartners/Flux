from django.core.management.base import BaseCommand, CommandError

from flux.chart.questdb_data_plane import export_plane_samples_to_questdb
from flux.trace.models import TraceProfile


class Command(BaseCommand):
    help = "Export local Plane sample rows into QuestDB plane_samples for data-plane comparison."

    def add_arguments(self, parser):
        parser.add_argument("profiles", nargs="*", help="Trace profile keys to export. Defaults to all enabled profiles.")
        parser.add_argument("--replace", action="store_true")
        parser.add_argument("--batch-size", type=int, default=5000)

    def handle(self, *args, **options):
        profiles = TraceProfile.objects.filter(enabled=True).order_by("key")
        if options["profiles"]:
            profiles = profiles.filter(key__in=options["profiles"])
        profiles = list(profiles)
        if not profiles:
            raise CommandError("No enabled Trace profiles matched the request")
        total = export_plane_samples_to_questdb(
            profile_keys=[profile.key for profile in profiles],
            replace=options["replace"],
            batch_size=options["batch_size"],
        )
        self.stdout.write("Exported %s Plane sample points into QuestDB" % total)
