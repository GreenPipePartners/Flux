from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from numbers import Real
from typing import Any

from django.utils import timezone
from flux_sim.value_profile import PRODUCTION_PROFILE_CONFIG_KEY, fit_value_profile

from flux.base.models import Tag
from flux.sim.models import SimDriver, TagProvider
from flux.base.runtime import RuntimeTag, TagSample
from flux.sim.kernel_sync import upsert_device_config, upsert_tag_config
from flux.sim.models import TagConfig


PROFILE_X_UNIT = "minutes_since_first_sample"


@dataclass(frozen=True)
class RuntimeProfileResult:
    runtime_tag: RuntimeTag
    profile: dict[str, Any]
    sample_count: int
    first_sample_at: Any
    last_sample_at: Any

    def to_metadata(self) -> dict[str, Any]:
        metadata = dict(self.profile)
        metadata.update(
            {
                "sample_count": self.sample_count,
                "x_unit": PROFILE_X_UNIT,
                "runtime_tag": {
                    "id": self.runtime_tag.id,
                    "provider": self.runtime_tag.provider,
                    "path": self.runtime_tag.path,
                    "full_path": self.runtime_tag.full_path,
                    "display_name": self.runtime_tag.display_name,
                    "asset_name": self.runtime_tag.asset_name,
                    "engineering_units": self.runtime_tag.engineering_units,
                },
                "first_sample_at": self.first_sample_at.isoformat(),
                "last_sample_at": self.last_sample_at.isoformat(),
                "generated_at": timezone.now().isoformat(),
            }
        )
        return metadata


def build_runtime_tag_profile(
    runtime_tag: RuntimeTag,
    *,
    limit: int | None = None,
    min_samples: int = 3,
) -> RuntimeProfileResult | None:
    """Fit a serializable value profile from local RuntimeTag history."""

    samples = numeric_tag_samples(runtime_tag, limit=limit)
    if len(samples) < min_samples:
        return None

    first_sample_at = samples[0].read_at
    profile_samples = []
    for sample in samples:
        value = numeric_value(sample.value)
        if value is not None:
            x = (sample.read_at - first_sample_at).total_seconds() / 60.0
            profile_samples.append((x, value))
    profile = fit_value_profile(profile_samples).to_dict()
    return RuntimeProfileResult(
        runtime_tag=runtime_tag,
        profile=profile,
        sample_count=len(samples),
        first_sample_at=first_sample_at,
        last_sample_at=samples[-1].read_at,
    )


def build_production_profile_map(
    runtime_tags: Iterable[RuntimeTag] | None = None,
    *,
    limit: int | None = None,
    min_samples: int = 3,
) -> dict[str, dict[str, Any]]:
    """Return profile metadata keyed by RuntimeTag full path for sim integration."""

    tags = runtime_tags if runtime_tags is not None else RuntimeTag.objects.filter(enabled=True)
    profile_map: dict[str, dict[str, Any]] = {}
    for runtime_tag in tags:
        result = build_runtime_tag_profile(runtime_tag, limit=limit, min_samples=min_samples)
        if result is not None:
            profile_map[runtime_tag.full_path] = result.to_metadata()
    return profile_map


def persist_field_tag_production_profile(
    field_tag: TagConfig,
    runtime_tag: RuntimeTag,
    *,
    limit: int | None = None,
    min_samples: int = 3,
) -> dict[str, Any] | None:
    """Write a RuntimeTag-derived profile into TagConfig.config."""

    result = build_runtime_tag_profile(runtime_tag, limit=limit, min_samples=min_samples)
    if result is None:
        return None

    metadata = result.to_metadata()
    config = dict(field_tag.config or {})
    config[PRODUCTION_PROFILE_CONFIG_KEY] = metadata
    field_tag.config = config
    field_tag.save(update_fields=["config"])
    return metadata


def persist_field_tag_production_profiles(
    bindings: Iterable[tuple[TagConfig, RuntimeTag]],
    *,
    limit: int | None = None,
    min_samples: int = 3,
) -> dict[str, dict[str, Any]]:
    persisted: dict[str, dict[str, Any]] = {}
    for field_tag, runtime_tag in bindings:
        metadata = persist_field_tag_production_profile(
            field_tag,
            runtime_tag,
            limit=limit,
            min_samples=min_samples,
        )
        if metadata is not None:
            persisted[field_tag.opc_item_path] = metadata
    return persisted


def numeric_tag_samples(runtime_tag: RuntimeTag, *, limit: int | None = None) -> list[TagSample]:
    query = runtime_tag.samples.order_by("read_at")
    if limit is not None:
        query = query[:limit]
    return [sample for sample in query if numeric_value(sample.value) is not None]


def numeric_value(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    return float(value)


def production_profile_from_config(config: Mapping[str, Any]) -> dict[str, Any] | None:
    payload = config.get(PRODUCTION_PROFILE_CONFIG_KEY)
    return payload if isinstance(payload, dict) else None


def materialize_profile_sim_device(
    *,
    provider_name: str,
    device_name: str,
    runtime_tags: Iterable[RuntimeTag],
    profile_map: Mapping[str, dict[str, Any]],
    source_fixture: str,
    driver_key: str = "profile-derived",
    driver_label: str = "Profile Derived",
) -> list[TagConfig]:
    runtime_tag_list = list(runtime_tags)
    provider, _created = TagProvider.objects.update_or_create(
        name=provider_name,
        defaults={
            "source": TagProvider.Source.IGNITION_PROVIDER,
            "source_name": "%s derived profile" % source_fixture,
            "source_sha256": "0" * 64,
            "total_nodes": len(runtime_tag_list),
            "atomic_tag_count": len(runtime_tag_list),
        },
    )
    driver, _created = SimDriver.objects.update_or_create(
        key=driver_key,
        defaults={"label": driver_label, "strategy_key": "profile"},
    )
    device = upsert_device_config(
        namespace=f"provider:{provider.name}",
        name=device_name,
        device_type=driver.label,
        source_provider=provider,
        driver=driver,
        browse_path=provider.name,
        enabled=True,
        description="Profile-derived sim device",
        config={"disposable": True},
    )

    tags = []
    for runtime_tag in runtime_tag_list:
        profile = profile_map.get(runtime_tag.full_path)
        if profile is None:
            continue
        source_path = f"{device_name}/{runtime_tag.path.rsplit('/', 1)[-1]}"
        tag = upsert_tag_config(
            sim_device=device,
            provider=provider.name,
            tagpath=source_path,
            tag_name=runtime_tag.display_name,
            data_type=Tag.DataType.FLOAT,
            simulation_type=TagConfig.SimulationType.RAMP,
            source_path=source_path,
            mode_config={
                "source_fixture": source_fixture,
                "source_runtime_tag_id": runtime_tag.id,
                "profile": profile,
            },
            enabled=True,
            materialized=False,
            description=source_path,
            config={"value_source": "memory"},
        )
        tags.append(tag)
    return tags
