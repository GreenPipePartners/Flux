from __future__ import annotations

import os
import time

from django.core.management.base import BaseCommand

from flux.sim.live_extract import (
    build_trial_live_source,
    cleanup_live_extraction_trial,
    datasource_info,
    extract_live_tags,
    historical_path,
    replay_live_extraction,
    tag_path,
    trial_history_paths,
    trial_tag_paths,
)


class Command(BaseCommand):
    help = "Trial live Ignition tag/history extraction and replay using one local gateway."

    def add_arguments(self, parser):
        parser.add_argument("--base-url", default=os.getenv("FLUXY_BASE_URL", "http://localhost:8088/system/webdev/flux"))
        parser.add_argument("--token", default=os.getenv("FLUXY_TOKEN"))
        parser.add_argument("--provider", default="default")
        parser.add_argument("--source-folder", default="FluxLiveSourceTrial")
        parser.add_argument("--target-folder", default="FluxSimReplayTrial")
        parser.add_argument("--history-provider", default="Core Historian")
        parser.add_argument("--historian-database", default="FluxyPostgres")
        parser.add_argument("--sample-count", type=int, default=4)
        parser.add_argument("--cleanup", action="store_true")
        parser.add_argument(
            "--require-history-cleanup",
            action="store_true",
            help="Fail if raw historian rows remain after tag cleanup. This is expected to fail with Fluxy-only public APIs.",
        )

    def handle(self, *args, **options):
        import fluxy

        fx = fluxy.Fluxy(base_url=options["base_url"], token=options["token"])
        provider = options["provider"]
        source_folder = options["source_folder"]
        target_folder = options["target_folder"]
        history_provider = options["history_provider"]
        historian_database = options["historian_database"]
        tag_names = ["Pressure", "Rate", "Cycles"]
        start_ms = int((time.time() - 3600) * 1000)
        end_ms = start_ms + 600_000

        cleanup_live_extraction_trial(
            fx,
            provider=provider,
            source_folder=source_folder,
            target_folder=target_folder,
            tag_names=tag_names,
            history_provider=history_provider,
        )

        source_points = build_trial_live_source(
            fx,
            provider=provider,
            source_folder=source_folder,
            start_ms=start_ms,
            history_provider=history_provider,
        )
        wait_for_history_rows(
            fx,
            [
                historical_path(provider=provider, folder=source_folder, tag_name=name, history_provider=history_provider)
                for name in tag_names
            ],
            start_ms - 1,
            end_ms,
            minimum_rows=1,
        )
        extraction = extract_live_tags(
            fx,
            provider=provider,
            source_folder=source_folder,
            target_folder=target_folder,
            start_ms=start_ms - 1,
            end_ms=end_ms,
            history_provider=history_provider,
        )
        replayed_points = replay_live_extraction(fx, extraction, history_provider=history_provider)

        target_tag_paths = [
            tag_path(provider=provider, folder=target_folder, tag_name=name)
            for name in sorted({point.tag_name for point in extraction.history_points})
        ]
        target_values = fx.tag.read_blocking(target_tag_paths)
        target_history_paths = [
            historical_path(provider=provider, folder=target_folder, tag_name=name, history_provider=history_provider)
            for name in sorted({point.tag_name for point in extraction.history_points})
        ]
        target_history = wait_for_history_rows(
            fx,
            target_history_paths,
            start_ms - 1,
            end_ms,
            minimum_rows=replayed_points,
        )

        self.stdout.write("Built live source history points: %s" % source_points)
        self.stdout.write("Extracted live history points: %s" % len(extraction.history_points))
        self.stdout.write("Replayed sim history points: %s" % replayed_points)
        self.stdout.write("Verified target tags: %s" % len(target_values))
        self.stdout.write("Verified target history rows: %s" % len(target_history))
        try:
            ds_info = datasource_info(fx, historian_database)
        except Exception as exc:
            self.stdout.write(self.style.WARNING("Could not inspect historian datasource %s: %s" % (historian_database, exc)))
        else:
            self.stdout.write("Historian datasource %s type: %s" % (ds_info.name, ds_info.db_type or "unknown"))

        if not extraction.history_points:
            raise RuntimeError("Extraction returned no history points")
        if len(target_history) < replayed_points:
            raise RuntimeError("Replay returned fewer target history rows than replayed points")

        if options["cleanup"]:
            cleanup_live_extraction_trial(
                fx,
                provider=provider,
                source_folder=source_folder,
                target_folder=target_folder,
                tag_names=tag_names,
                history_provider=history_provider,
            )
            remaining_good_tags = wait_for_tags_not_good(
                fx,
                trial_tag_paths(provider=provider, folders=[source_folder, target_folder], tag_names=tag_names),
            )
            remaining_history = wait_for_no_history_rows(
                fx,
                trial_history_paths(
                    provider=provider,
                    folders=[source_folder, target_folder],
                    tag_names=tag_names,
                    history_provider=history_provider,
                ),
                start_ms - 1,
                end_ms,
            )
            self.stdout.write("Cleanup verified non-Good trial tags: %s" % (not remaining_good_tags))
            self.stdout.write("Cleanup verified remaining trial history rows: %s" % len(remaining_history))
            if remaining_good_tags:
                raise RuntimeError("Cleanup left readable trial tags: %s" % remaining_good_tags)
            if remaining_history and options["require_history_cleanup"]:
                raise RuntimeError("Cleanup left queryable trial history rows: %s" % len(remaining_history))
            if remaining_history:
                self.stdout.write(
                    self.style.WARNING(
                        "Fluxy-only cleanup cannot delete raw historian points; trial history remains queryable until historian retention/database cleanup."
                    )
                )


def wait_for_history_rows(fx, paths, start_ms: int, end_ms: int, *, minimum_rows: int, timeout_seconds: float = 20.0):
    deadline = time.monotonic() + timeout_seconds
    latest_rows = []
    while time.monotonic() < deadline:
        latest_rows = fx.historian.query_raw_points(paths, start_ms, end_ms, return_size=10_000)
        if len(latest_rows) >= minimum_rows:
            return latest_rows
        time.sleep(1.0)
    return latest_rows


def wait_for_no_history_rows(fx, paths, start_ms: int, end_ms: int, *, timeout_seconds: float = 20.0):
    deadline = time.monotonic() + timeout_seconds
    latest_rows = []
    while time.monotonic() < deadline:
        try:
            latest_rows = fx.historian.query_raw_points(paths, start_ms, end_ms, return_size=10_000)
        except Exception:
            latest_rows = []
        if not latest_rows:
            return latest_rows
        time.sleep(1.0)
    return latest_rows


def wait_for_tags_not_good(fx, paths, *, timeout_seconds: float = 20.0) -> list[str]:
    deadline = time.monotonic() + timeout_seconds
    remaining_good = paths
    while time.monotonic() < deadline:
        try:
            values = fx.tag.read_blocking(paths)
        except Exception:
            return []
        remaining_good = [path for path, value in zip(paths, values, strict=True) if "Good" in value.quality]
        if not remaining_good:
            return []
        time.sleep(1.0)
    return remaining_good
