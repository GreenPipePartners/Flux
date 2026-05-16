from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import DEFAULT_DB_ALIAS, connections, transaction


class Command(BaseCommand):
    help = "Reset database sequences for models in the selected apps."

    def add_arguments(self, parser):
        parser.add_argument(
            "app_labels",
            nargs="*",
            default=["base"],
            help="App labels to repair. Defaults to base.",
        )
        parser.add_argument("--database", default=DEFAULT_DB_ALIAS)

    def handle(self, *args, **options):
        connection = connections[options["database"]]
        models = []
        for app_label in options["app_labels"]:
            app_config = apps.get_app_config(app_label)
            models.extend(app_config.get_models())

        statements = connection.ops.sequence_reset_sql(self.style, models)
        if not statements:
            self.stdout.write("No database sequences needed repair.")
            return

        with transaction.atomic(using=options["database"]):
            with connection.cursor() as cursor:
                for statement in statements:
                    cursor.execute(statement)

        self.stdout.write("Repaired %s database sequences." % len(statements))
