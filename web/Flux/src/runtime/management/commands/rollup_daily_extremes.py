from datetime import date

from django.core.management.base import BaseCommand

from flux.base.runtime_extremes import rollup_daily_extremes


class Command(BaseCommand):
    help = "Persist completed-day runtime tag min/max extremes."

    def add_arguments(self, parser):
        parser.add_argument("--date", help="Local date to roll up as YYYY-MM-DD. Defaults to yesterday.")

    def handle(self, *args, **options):
        day = date.fromisoformat(options["date"]) if options["date"] else None
        count = rollup_daily_extremes(day=day)
        self.stdout.write("Rolled up %s runtime tag daily extremes" % count)
