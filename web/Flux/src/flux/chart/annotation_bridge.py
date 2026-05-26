from __future__ import annotations

import os


def fluxy_historian():
    import fluxy

    fx = fluxy.Fluxy(
        base_url=os.getenv("FLUXY_BASE_URL", "http://localhost:8088/system/webdev/flux"),
        token=os.getenv("FLUXY_TOKEN") or None,
    )
    return fx.historian


def store_ignition_annotations(*, paths: list[str], marker_ms: int, storage_ids: list[str], annotation_data: str):
    return fluxy_historian().store_annotations(
        paths,
        [marker_ms] * len(paths),
        end_times=[marker_ms] * len(paths),
        types=["flux.trace.annotation"] * len(paths),
        data=[annotation_data] * len(paths),
        storage_ids=storage_ids,
    )


def query_ignition_annotations(*, paths: list[str], start_time: int, end_time: int):
    return fluxy_historian().query_annotations(paths, start_time, end_date=end_time)
