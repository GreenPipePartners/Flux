from django.core.management.base import BaseCommand, CommandError

from trace.providers.nav_wells import seeded_well_profiles
from trace.questdb_data_plane import export_trace_cache_to_questdb


class Command(BaseCommand):
    help = "Export local TraceCachePoint rows into QuestDB for data-plane comparison."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument("--replace", action="store_true")
        parser.add_argument("--batch-size", type=int, default=5000)

    def handle(self, *args, **options):
        profiles = seeded_well_profiles()
        if options["limit"]:
            profiles = profiles[: options["limit"]]
        if not profiles:
            raise CommandError("No seeded nav well Trace profiles found")
        total = export_trace_cache_to_questdb(
            profile_keys=[profile.key for profile in profiles],
            replace=options["replace"],
            batch_size=options["batch_size"],
        )
        self.stdout.write("Exported %s Trace cache points into QuestDB" % total)
