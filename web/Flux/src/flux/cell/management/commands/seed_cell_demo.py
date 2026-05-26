from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from flux.cell.services import seed_demo_cell_bundle


class Command(BaseCommand):
    help = "Seed a small Flux.cell demo bundle backed by cached runtime and trace values."

    def add_arguments(self, parser):
        parser.add_argument(
            "--skip-runtime",
            action="store_true",
            help="Create cells only; do not seed runtime or Plane sample values",
        )

    def handle(self, *args, **options):
        include_runtime = not options["skip_runtime"]
        try:
            result = seed_demo_cell_bundle(include_runtime=include_runtime)
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        runtime_detail = ""
        if include_runtime:
            runtime_detail = (
                f", {result.runtime_tags} runtime tags, {result.plane_sample_points} Plane sample points"
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded Flux.cell demo bundle {result.bundle.key}: {result.cells} cells, {result.points} points{runtime_detail}. "
                f"Open {result.anchor_url}"
            )
        )
