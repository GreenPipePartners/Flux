from __future__ import annotations

import json
import os

from django.core.management.base import BaseCommand
from django.utils import timezone

from flux.base.runtime import RuntimeTag
from flux.sim.live_extract import datasource_info

from dashboard.services import bridge_config, dashboard_runtime_state, fluxy_client


class Command(BaseCommand):
    help = "Emit Flux app health state as JSON for the operator CLI."

    def add_arguments(self, parser):
        parser.add_argument("--historian-database", default=os.getenv("FLUX_HISTORIAN_DATABASE", "FluxyPostgres"))

    def handle(self, *args, **options):
        tags = list(RuntimeTag.objects.select_related("latest_value", "schedule").filter(enabled=True).order_by("id"))
        runtime_state = dashboard_runtime_state(tags)
        bridge = bridge_config()
        latest_read_age_seconds = None
        if runtime_state["last_read_at"] is not None:
            latest_read_age_seconds = int((timezone.now() - runtime_state["last_read_at"]).total_seconds())

        historian = {
            "database": options["historian_database"],
            "ok": False,
            "db_type": "",
            "status": "",
            "error": "",
        }
        try:
            info = datasource_info(fluxy_client(), options["historian_database"])
        except Exception as exc:
            historian["error"] = str(exc)
        else:
            historian.update(
                {
                    "ok": bool(info.db_type),
                    "database": info.name,
                    "db_type": info.db_type,
                    "status": info.status,
                }
            )

        bridge_online = False
        bridge_message = bridge.last_test_message
        try:
            version = fluxy_client().util.get_version(refresh=True)
        except Exception as exc:
            bridge_message = str(exc)
        else:
            bridge_online = True
            bridge_message = f"Connected to Ignition {version.version}."

        payload = {
            "bridge": {
                "base_url": bridge.base_url,
                "token_set": bool(bridge.token),
                "online": bridge_online,
                "message": bridge_message,
                "last_test_at": bridge.last_test_at.isoformat() if bridge.last_test_at else None,
            },
            "runtime": {
                "tag_count": runtime_state["tag_count"],
                "online_count": runtime_state["online_count"],
                "stale_count": runtime_state["stale_count"],
                "bad_quality_count": runtime_state["bad_quality_count"],
                "stale_after_seconds": runtime_state["stale_after_seconds"],
                "latest_read_at": runtime_state["last_read_at"].isoformat() if runtime_state["last_read_at"] else None,
                "latest_read_age_seconds": latest_read_age_seconds,
            },
            "historian": historian,
        }
        self.stdout.write(json.dumps(payload, sort_keys=True))
