from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from flux.mine.services import mine_source


class Command(BaseCommand):
    help = "Mine PLC or FactoryTalk sources into Flux.mine persistence tables."

    def add_arguments(self, parser):
        parser.add_argument("source", help="Path to an .L5X/.L5K file, FactoryTalk XML/PAR file, FactoryTalk directory, or FactoryTalk ZIP")
        parser.add_argument(
            "--source-type",
            default="auto",
            choices=["auto", "plc", "plc_l5x", "plc_l5k", "factorytalk"],
            help="Source type override. Defaults to extension/path inference.",
        )
        parser.add_argument("--label", default="", help="Optional label for the mine run")

    def handle(self, *args, **options):
        try:
            run = mine_source(options["source"], source_type=options["source_type"], label=options["label"])
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                "Mined run %(id)s type=%(type)s status=%(status)s summary=%(summary)s"
                % {
                    "id": run.id,
                    "type": run.source_type,
                    "status": run.status,
                    "summary": run.summary,
                }
            )
        )
