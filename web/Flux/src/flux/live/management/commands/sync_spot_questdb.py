from django.core.management.base import BaseCommand, CommandError

from flux.plane.questdb_samples import export_series_samples_to_questdb
from flux.spot.models import LiveCardPointDefinition, LiveScope


class Command(BaseCommand):
    help = "Export Spot scope Plane sample rows into QuestDB plane_samples."

    def add_arguments(self, parser):
        parser.add_argument("scopes", nargs="*", help="Spot scope slugs to export. Defaults to all enabled scopes.")
        parser.add_argument("--replace", action="store_true", help="Replace the QuestDB plane_samples table before export.")
        parser.add_argument("--batch-size", type=int, default=5000)

    def handle(self, *args, **options):
        requested_scopes = options["scopes"]
        scopes = LiveScope.objects.filter(enabled=True)
        if requested_scopes:
            scopes = scopes.filter(slug__in=requested_scopes)
        scope_slugs = list(scopes.values_list("slug", flat=True))
        if not scope_slugs:
            raise CommandError("No enabled Spot scopes matched the request.")
        series_ids = list(
            LiveCardPointDefinition.objects.filter(
                card__scope__slug__in=scope_slugs,
                card__scope__enabled=True,
                card__enabled=True,
                enabled=True,
                series__isnull=False,
            )
            .order_by("series_id")
            .values_list("series_id", flat=True)
            .distinct()
        )
        if not series_ids:
            raise CommandError("Selected Spot scopes have no Plane-linked points to export.")
        total = export_series_samples_to_questdb(
            series_ids=series_ids,
            replace=options["replace"],
            batch_size=options["batch_size"],
        )
        self.stdout.write("Exported %s Spot Plane sample points for %s scopes and %s series into QuestDB" % (total, len(scope_slugs), len(series_ids)))
