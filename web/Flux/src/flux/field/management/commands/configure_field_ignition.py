import os

from django.core.management.base import BaseCommand

import fluxy
from flux.base.field_config import endpoint_config
from flux.base.field_selectors import enabled_field_endpoint_queryset
from flux.field.ignition import configure_field_agent_ignition
from flux.serve.field_supervisor import DEFAULT_FIELD_AGENT_HOST, server_endpoint_url


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
            "--field-agent-host",
            default=DEFAULT_FIELD_AGENT_HOST,
            help="Connectable host advertised by supervised FieldAgent OPC UA servers.",
        )
        parser.add_argument("--supervised-base-port", type=int, default=4850)
        parser.add_argument("--use-db-endpoint-url", action="store_true")
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
        endpoints = enabled_field_endpoint_queryset()
        config = {
            "endpoints": [
                endpoint_config(
                    endpoint,
                    endpoint_url=endpoint.endpoint_url
                    if options["use_db_endpoint_url"]
                    else server_endpoint_url(
                        endpoint,
                        base_port=options["supervised_base_port"],
                        host=options["field_agent_host"],
                    ),
                )
                for endpoint in endpoints
            ]
        }
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
