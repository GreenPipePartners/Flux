from django.core.management.base import BaseCommand

from flux.chart.importer import import_trace_scopes_csv


class Command(BaseCommand):
    help = "Import generic Flux.chart scopes from a wide CSV file."

    def add_arguments(self, parser):
        parser.add_argument("csv_path")

    def handle(self, *args, **options):
        result = import_trace_scopes_csv(options["csv_path"])
        self.stdout.write(
            "Imported profiles=%s tags=%s signals=%s"
            % (result.profiles, result.tags, result.signals)
        )
