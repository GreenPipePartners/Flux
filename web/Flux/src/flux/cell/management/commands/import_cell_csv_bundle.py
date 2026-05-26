from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from flux.cell.services import import_cell_bundle_path


class Command(BaseCommand):
    help = "Import a Flux.cell CSV bundle containing cells.csv and points.csv."

    def add_arguments(self, parser):
        parser.add_argument("path", help="Directory containing cells.csv and points.csv")
        parser.add_argument("--replace", action="store_true", help="Replace existing cells/points for bundles in cells.csv")

    def handle(self, *args, **options):
        try:
            result = import_cell_bundle_path(options["path"], replace=options["replace"])
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                "Imported %(bundles)s bundles, %(cells)s cells, %(points)s points"
                % {"bundles": result.bundles, "cells": result.cells, "points": result.points}
            )
        )
