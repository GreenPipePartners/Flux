import os
import time

import pytest

from flux.sim.live_extract import (
    build_trial_live_source,
    cleanup_live_extraction_trial,
    extract_live_tags,
    historical_path,
    replay_live_extraction,
    tag_path,
    trial_history_paths,
    trial_tag_paths,
)
from flux.sim.management.commands.trial_live_extraction import (
    wait_for_history_rows,
    wait_for_no_history_rows,
    wait_for_tags_not_good,
)


pytestmark = pytest.mark.integration


def test_live_ignition_tags_and_history_extract_into_sim_namespace():
    if os.getenv("FLUX_LIVE_EXTRACTION_INTEGRATION") != "1":
        pytest.skip("Set FLUX_LIVE_EXTRACTION_INTEGRATION=1 to run live extraction trial")

    import fluxy
    from fluxy import FluxyError

    provider = os.getenv("FLUX_LIVE_EXTRACTION_PROVIDER", "default")
    source_folder = os.getenv("FLUX_LIVE_EXTRACTION_SOURCE", "FluxLiveSourceTrialTest")
    target_folder = os.getenv("FLUX_LIVE_EXTRACTION_TARGET", "FluxSimReplayTrialTest")
    history_provider = os.getenv("FLUX_LIVE_EXTRACTION_HISTORY_PROVIDER", "Core Historian")
    tag_names = ["Pressure", "Rate", "Cycles"]
    start_ms = int((time.time() - 3600) * 1000)
    end_ms = start_ms + 600_000
    fx = fluxy.Fluxy(
        base_url=os.getenv("FLUXY_BASE_URL", "http://localhost:8088/system/webdev/flux"),
        token=os.getenv("FLUXY_TOKEN"),
    )

    try:
        cleanup_trial(fx, provider, source_folder, target_folder, tag_names, history_provider, start_ms, end_ms)
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
                historical_path(
                    provider=provider,
                    folder=source_folder,
                    tag_name=name,
                    history_provider=history_provider,
                )
                for name in tag_names
            ],
            start_ms - 1,
            end_ms,
            minimum_rows=1,
        )
        source_tag_values = fx.tag.read_blocking(
            [
                tag_path(provider=provider, folder=source_folder, tag_name=name)
                for name in tag_names
            ]
        )
        assert len(source_tag_values) == 3
        assert all("Good" in value.quality for value in source_tag_values)

        extraction = extract_live_tags(
            fx,
            provider=provider,
            source_folder=source_folder,
            target_folder=target_folder,
            start_ms=start_ms - 1,
            end_ms=end_ms,
            history_provider=history_provider,
        )
        assert len(extraction.tag_configs) == 1
        assert extraction.tag_configs[0]["name"] == target_folder
        assert len(extraction.history_points) > 0
        assert len(extraction.history_points) <= source_points

        replayed_points = replay_live_extraction(fx, extraction, history_provider=history_provider)
        assert replayed_points == len(extraction.history_points)

        target_tag_paths = [
            tag_path(provider=provider, folder=target_folder, tag_name=name)
            for name in sorted({point.tag_name for point in extraction.history_points})
        ]
        target_tag_values = fx.tag.read_blocking(target_tag_paths)
        assert len(target_tag_values) == len(target_tag_paths)
        assert all("Good" in value.quality for value in target_tag_values)

        target_history_paths = [
            historical_path(
                provider=provider,
                folder=target_folder,
                tag_name=name,
                history_provider=history_provider,
            )
            for name in sorted({point.tag_name for point in extraction.history_points})
        ]
        target_history = wait_for_history_rows(
            fx,
            target_history_paths,
            start_ms - 1,
            end_ms,
            minimum_rows=replayed_points,
        )
        assert len(target_history) >= replayed_points
    except FluxyError as exc:
        if "Trial Expired" in str(exc):
            pytest.skip("Ignition trial expired during live extraction test")
        raise
    finally:
        remaining_good, remaining_history = cleanup_trial(
            fx, provider, source_folder, target_folder, tag_names, history_provider, start_ms, end_ms
        )
        assert remaining_good == []
        # Fluxy intentionally stays on public Ignition APIs. Those APIs can delete
        # tags, annotations, and metadata, but they do not expose raw historian
        # point deletion. Raw history may remain queryable until retention or a
        # database-source-specific cleanup removes it.
        assert isinstance(remaining_history, list)


def cleanup_trial(
    fx,
    provider: str,
    source_folder: str,
    target_folder: str,
    tag_names: list[str],
    history_provider: str,
    start_ms: int,
    end_ms: int,
) -> tuple[list[str], list[dict]]:
    cleanup_live_extraction_trial(
        fx,
        provider=provider,
        source_folder=source_folder,
        target_folder=target_folder,
        tag_names=tag_names,
        history_provider=history_provider,
    )
    remaining_good = wait_for_tags_not_good(
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
    return remaining_good, list(remaining_history)
