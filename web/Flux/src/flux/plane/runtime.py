from __future__ import annotations

from collections.abc import Iterable, Mapping

from django.utils import timezone

from flux.base.runtime import LatestTagValue, RuntimeTag, TagSample
from flux.plane.services import RuntimePlaneSample, mirror_runtime_samples_to_plane


def sample_runtime_bad_quality(
    runtime_tags: Iterable[RuntimeTag],
    qualities: Mapping[str, str],
    *,
    now=None,
) -> int:
    """Record a bad-quality runtime sample for each tag keyed by full path."""

    read_at = now or timezone.now()
    samples = []
    plane_samples = []
    count = 0
    for tag in runtime_tags:
        quality = qualities.get(tag.full_path, "Bad_SourceOffline")
        LatestTagValue.objects.update_or_create(
            tag=tag,
            defaults={
                "value": None,
                "quality_code": quality,
                "value_timestamp": read_at,
                "read_at": read_at,
            },
        )
        samples.append(
            TagSample(
                tag=tag,
                value=None,
                quality_code=quality,
                value_timestamp=read_at,
                read_at=read_at,
            )
        )
        plane_samples.append(
            RuntimePlaneSample(
                tag=tag,
                value=None,
                quality_code=quality,
                value_timestamp=read_at,
                read_at=read_at,
            )
        )
        count += 1
    if samples:
        TagSample.objects.bulk_create(samples)
        mirror_runtime_samples_to_plane(plane_samples, now=read_at)
    return count
