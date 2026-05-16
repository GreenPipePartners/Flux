import json

from django.core.management.base import BaseCommand

from flux.base.field_selectors import enabled_endpoint_configs


class Command(BaseCommand):
    help = "Export enabled Flux simulation FieldAgent configuration as JSON."

    def add_arguments(self, parser):
        parser.add_argument("--output", help="Optional file path. Writes to stdout when omitted.")

    def handle(self, *args, **options):
        payload = {"endpoints": enabled_endpoint_configs()}
        text = json.dumps(payload, indent=2, sort_keys=True)
        if options["output"]:
            with open(options["output"], "w", encoding="utf-8") as output:
                output.write(text)
                output.write("\n")
            self.stdout.write("Wrote Flux simulation FieldAgent config to %s" % options["output"])
        else:
            self.stdout.write(text)
