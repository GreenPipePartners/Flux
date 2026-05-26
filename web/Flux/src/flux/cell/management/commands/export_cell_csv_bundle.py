from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from flux.cell.services import write_cell_bundle_exports


class Command(BaseCommand):
    help = "Export Flux.cell draft rows into Live/Trace-compatible CSV files."

    def add_arguments(self, parser):
        parser.add_argument("bundle_key", help="Cell bundle key to export")
        parser.add_argument("--output", required=True, help="Output directory for live_scope.csv and trace_scopes.csv")

    def handle(self, *args, **options):
        try:
            paths = write_cell_bundle_exports(options["bundle_key"], options["output"])
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS("Exported %(live)s and %(trace)s" % {"live": paths["live_scope"], "trace": paths["trace_scopes"]}))
