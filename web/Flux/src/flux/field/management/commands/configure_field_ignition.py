import os

from django.core.management.base import BaseCommand

import fluxy
from flux.base.field_config import enabled_endpoint_configs
from flux.field.ignition import configure_field_agent_ignition


class Command(BaseCommand):
    help = "Configure Ignition OPC UA connections and OPC tags for enabled FieldAgent endpoints."

    def add_arguments(self, parser):
        parser.add_argument("--base-url", default=os.getenv("FLUXY_BASE_URL", "http://localhost:8088/system/webdev/flux"))
        parser.add_argument("--token", default=os.getenv("FLUXY_TOKEN"))
        parser.add_argument(
            "--project-location",
            default=os.getenv("FLUXY_PROJECT_LOCATION"),
            help="Optional Ignition project filesystem path for Fluxy project helpers.",
        )
        parser.add_argument("--tag-provider", default="default")
        parser.add_argument("--tag-folder", default="FieldAgent")
        parser.add_argument(
            "--collision-policy",
            default="o",
            choices=["a", "m", "o", "i"],
            help="Ignition system.tag.configure collision policy.",
        )
        parser.add_argument(
            "--no-cleanup",
            action="store_true",
            help="Do not delete the target tag folder or remove generated OPC UA connections first.",
        )

    def handle(self, *args, **options):
        config = {"endpoints": enabled_endpoint_configs()}
        client = fluxy.Fluxy(
            base_url=options["base_url"],
            token=options["token"],
            project_location=options["project_location"],
        )
        result = configure_field_agent_ignition(
            client,
            config,
            tag_provider=options["tag_provider"],
            tag_folder=options["tag_folder"],
            cleanup_existing=not options["no_cleanup"],
            collision_policy=options["collision_policy"],
        )
        self.stdout.write(
            self.style.SUCCESS(
                "Configured %(connections)s OPC UA connection(s) and %(tags)s OPC tag(s) under %(base)s%(folder)s"
                % {
                    "connections": len(result.connection_names),
                    "tags": result.tag_count,
                    "base": result.tag_base_path,
                    "folder": result.tag_folder,
                }
            )
        )
