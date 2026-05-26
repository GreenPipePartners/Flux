from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.db import transaction
from django.utils import timezone

from flux.base.models import Tag
from flux.sim.models import FieldEndpoint
from flux.base.runtime import LatestTagValue, RuntimeTag, TagSample, TagSchedule, assign_balancer_codes, scheduler_config
from flux.field.ignition import FieldIgnitionConfiguration, configure_field_agent_ignition, cleanup_field_agent_ignition
from flux.sim.kernel_sync import disable_materialized_configs, upsert_device_config, upsert_tag_config
from flux.sim.models import DeviceConfig, TagConfig


FLUXOLOT_TAG_FOLDER = "FluxolotFishtank"
FLUXOLOT_SCHEDULE_NAME = "fluxolot-fishtank-10s"
FLUXOLOT_LIVE_SCOPE = "fluxolot"
FLUXOLOT_LIVE_SCOPE_NAME = "Fluxolot Fishtank"
FLUXOLOT_TRACE_SCOPE = "fluxolot"
FLUXOLOT_TRACE_PROFILE = "fluxolot"
FLUXOLOT_TRACE_PROFILE_PREFIX = "fluxolot"
FLUXOLOT_FIXTURE = "fluxolot-fishtank"


@dataclass(frozen=True)
class FluxolotTankSpec:
    key: str
    owner: str
    display_name: str
    endpoint_name: str
    endpoint_url: str
    device_name: str
    sort_order: int
    phase_offset: float


@dataclass(frozen=True)
class FluxolotTagSpec:
    name: str
    label: str
    cell_type: str
    instrument: str
    group: str
    kind: str
    data_type: str
    units: str
    initial_value: str
    min_value: float | None
    max_value: float | None
    simulation_type: str
    update_rate_ms: int = 1000
    phase: float = 0.0
    trace: bool = True


@dataclass(frozen=True)
class FluxolotFishtankResult:
    endpoints: list[FieldEndpoint]
    devices: list[DeviceConfig]
    field_tags: list[TagConfig]
    runtime_tags: list[RuntimeTag]
    sample_count: int


FLUXOLOT_TANKS = (
    FluxolotTankSpec(
        key="sir",
        owner="Sir Fluxolot",
        display_name="Sir Fluxolot Fishtank",
        endpoint_name="sir-fluxolot-fishtank",
        endpoint_url="opc.tcp://localhost:4840/flux/fluxolot/sir",
        device_name="Sir-Fluxolot-Fishtank",
        sort_order=1,
        phase_offset=0.0,
    ),
    FluxolotTankSpec(
        key="missus",
        owner="Missus Fluxolot",
        display_name="Missus Fluxolot Fishtank",
        endpoint_name="missus-fluxolot-fishtank",
        endpoint_url="opc.tcp://localhost:4841/flux/fluxolot/missus",
        device_name="Missus-Fluxolot-Fishtank",
        sort_order=2,
        phase_offset=0.9,
    ),
)


FLUXOLOT_TAGS = (
    FluxolotTagSpec(
        "PUMP_START_STOP_COMMAND",
        "Start/Stop Command",
        "Pump",
        "start/stop command",
        "Pump",
        "Recirculation Pump",
        Tag.DataType.BOOL,
        "",
        "false",
        None,
        None,
        TagConfig.SimulationType.TOGGLE,
        update_rate_ms=2000,
        phase=0.0,
        trace=False,
    ),
    FluxolotTagSpec(
        "PUMP_START_STOP_FEEDBACK",
        "Start/Stop Feedback",
        "Pump",
        "start/stop feedback",
        "Pump",
        "Recirculation Pump",
        Tag.DataType.BOOL,
        "",
        "true",
        None,
        None,
        TagConfig.SimulationType.TOGGLE,
        update_rate_ms=2000,
        phase=0.3,
        trace=False,
    ),
    FluxolotTagSpec(
        "PUMP_MOTOR_SETPOINT",
        "Motor Control Setpoint",
        "Pump",
        "motor control setpoint",
        "Pump",
        "Recirculation Pump",
        Tag.DataType.FLOAT,
        "%",
        "72",
        40,
        95,
        TagConfig.SimulationType.WAVE,
        update_rate_ms=5000,
        phase=0.6,
    ),
    FluxolotTagSpec(
        "PUMP_MOTOR_FEEDBACK",
        "Motor Control Feedback",
        "Pump",
        "motor control feedback",
        "Pump",
        "Recirculation Pump",
        Tag.DataType.FLOAT,
        "%",
        "70",
        38,
        96,
        TagConfig.SimulationType.WAVE,
        update_rate_ms=1000,
        phase=0.8,
    ),
    FluxolotTagSpec(
        "PUMP_HEAD_PRESSURE",
        "Head Pressure",
        "Pump",
        "head pressure",
        "Pump",
        "Recirculation Pump",
        Tag.DataType.FLOAT,
        "psi",
        "12",
        4,
        24,
        TagConfig.SimulationType.WAVE,
        phase=1.1,
    ),
    FluxolotTagSpec(
        "TANK_LEVEL",
        "Level",
        "Fishtank",
        "level",
        "Tank",
        "Fish Tank",
        Tag.DataType.FLOAT,
        "%",
        "78",
        55,
        95,
        TagConfig.SimulationType.WAVE,
        phase=1.4,
    ),
    FluxolotTagSpec(
        "TANK_TEMPERATURE",
        "Temperature",
        "Fishtank",
        "temperature",
        "Tank",
        "Fish Tank",
        Tag.DataType.FLOAT,
        "degF",
        "74",
        68,
        82,
        TagConfig.SimulationType.WAVE,
        phase=1.7,
    ),
    FluxolotTagSpec(
        "TANK_O2_PERCENT",
        "O2 Percent",
        "Fishtank",
        "O2%",
        "Tank",
        "Fish Tank",
        Tag.DataType.FLOAT,
        "%",
        "88",
        65,
        100,
        TagConfig.SimulationType.WAVE,
        phase=2.0,
    ),
    FluxolotTagSpec(
        "TANK_LOW_LEVEL_ALARM",
        "Low Level Alarm",
        "Fishtank",
        "low level alarm",
        "Tank",
        "Fish Tank",
        Tag.DataType.BOOL,
        "",
        "false",
        None,
        None,
        TagConfig.SimulationType.STATIC,
        update_rate_ms=5000,
        phase=2.3,
        trace=False,
    ),
    FluxolotTagSpec(
        "UV_LIGHT_STATUS",
        "On/Off Status",
        "Light",
        "on/off status",
        "Light",
        "UV Light",
        Tag.DataType.BOOL,
        "",
        "true",
        None,
        None,
        TagConfig.SimulationType.TOGGLE,
        update_rate_ms=3000,
        phase=2.6,
        trace=False,
    ),
    FluxolotTagSpec(
        "UV_LIGHT_RUNTIME_REMAINING",
        "Runtime Remaining",
        "Light",
        "timer",
        "Light",
        "UV Light",
        Tag.DataType.INT,
        "min",
        "480",
        0,
        720,
        TagConfig.SimulationType.RAMP,
        update_rate_ms=5000,
        phase=2.9,
    ),
    FluxolotTagSpec(
        "TREAT_FEEDER_RUN_STATUS",
        "Run Status",
        "Feeder",
        "run status",
        "Feeder",
        "Treat Feeder",
        Tag.DataType.BOOL,
        "",
        "false",
        None,
        None,
        TagConfig.SimulationType.TOGGLE,
        update_rate_ms=3000,
        phase=3.2,
        trace=False,
    ),
    FluxolotTagSpec(
        "TREAT_FEEDER_LEVEL",
        "Level",
        "Feeder",
        "level",
        "Feeder",
        "Treat Feeder",
        Tag.DataType.FLOAT,
        "%",
        "64",
        20,
        100,
        TagConfig.SimulationType.WAVE,
        update_rate_ms=5000,
        phase=3.5,
    ),
)


def ensure_fluxolot_fishtank(
    *,
    history_days: int = 30,
    history_interval_minutes: int = 60,
    history_batch_size: int = 5000,
) -> FluxolotFishtankResult:
    """Install or update the Fluxolot Fishtank fixture and seed deterministic history."""

    with transaction.atomic():
        endpoints, devices, field_tags = ensure_fluxolot_field_config()
        runtime_tags = ensure_fluxolot_runtime_config(field_tags)
        sample_count = seed_fluxolot_history(
            runtime_tags,
            history_days=history_days,
            history_interval_minutes=history_interval_minutes,
            batch_size=history_batch_size,
        )
    return FluxolotFishtankResult(endpoints, devices, field_tags, runtime_tags, sample_count)


def configure_fluxolot_fishtank_ignition(
    fx: Any,
    *,
    tag_provider: str = "default",
    tag_folder: str = FLUXOLOT_TAG_FOLDER,
    endpoint_urls: dict[str, str] | None = None,
    connection_names: list[str] | None = None,
    cleanup_existing: bool = True,
    collision_policy: str = "o",
) -> FieldIgnitionConfiguration:
    """Configure Ignition OPC UA connections and tags for both Fluxolot tanks."""

    endpoints, _devices, _field_tags = ensure_fluxolot_field_config()
    from flux.base.field_config import endpoint_config

    urls = endpoint_urls or {}
    config = {
        "endpoints": [
            endpoint_config(endpoint, endpoint_url=urls.get(endpoint.name))
            for endpoint in endpoints
        ]
    }
    return configure_field_agent_ignition(
        fx,
        config,
        tag_provider=tag_provider,
        tag_folder=tag_folder,
        connection_names=connection_names or fluxolot_connection_names(endpoints),
        cleanup_existing=cleanup_existing,
        collision_policy=collision_policy,
    )


def cleanup_fluxolot_fishtank_ignition(
    fx: Any,
    *,
    tag_provider: str = "default",
    tag_folder: str = FLUXOLOT_TAG_FOLDER,
    connection_names: list[str] | None = None,
) -> None:
    cleanup_field_agent_ignition(
        fx,
        tag_provider=tag_provider,
        tag_folder=tag_folder,
        connection_names=connection_names or fluxolot_connection_names(),
    )


def fluxolot_connection_names(endpoints: list[FieldEndpoint] | None = None) -> list[str]:
    if endpoints is None:
        names = [tank.endpoint_name for tank in FLUXOLOT_TANKS]
    else:
        names = [endpoint.name for endpoint in endpoints]
    return ["Flux Field %s" % name for name in names]


def write_fluxolot_live_csv(path: str | Path) -> int:
    runtime_tags = ensure_fluxolot_runtime_config()
    rows = fluxolot_live_csv_rows(runtime_tags)
    write_csv_rows(path, rows, fieldnames=fluxolot_live_csv_fields())
    return len(rows)


def write_fluxolot_live_scope_csv(
    path: str | Path,
    runtime_tags: list[RuntimeTag] | None = None,
    *,
    scope: str = FLUXOLOT_LIVE_SCOPE,
) -> Path:
    runtime_tags = runtime_tags or ensure_fluxolot_runtime_config()
    rows = []
    for card_order, (tank, group, kind, tags) in enumerate(live_card_groups(runtime_tags), start=1):
        row = {
            "Live Scope": scope,
            "Scope Name": FLUXOLOT_LIVE_SCOPE_NAME,
            "description": "Fluxolot Fishtank proof-of-status current state.",
            "ID (optional)": str(card_order),
            "Name": f"{tank.owner} {kind}",
            "group": group,
            "kind": kind,
            "display order (optional)": str(card_order),
        }
        for index, tag in enumerate(tags, start=1):
            row[f"Tag {index}"] = tag.full_path
            row[f"Tag {index} Label"] = tag.display_name
        rows.append(row)
    write_csv_rows(path, rows, fieldnames=wide_fieldnames(rows))
    return Path(path)


def write_fluxolot_trace_csv(path: str | Path) -> int:
    runtime_tags = ensure_fluxolot_runtime_config()
    samples = TagSample.objects.select_related("tag").filter(tag__in=runtime_tags).order_by("tag__display_name", "read_at")
    with open(path, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fluxolot_trace_csv_fields())
        writer.writeheader()
        rows = 0
        for sample in samples:
            writer.writerow(fluxolot_trace_csv_row(sample))
            rows += 1
    return rows


def write_fluxolot_trace_scope_csv(
    path: str | Path,
    runtime_tags: list[RuntimeTag] | None = None,
    *,
    scope: str = FLUXOLOT_TRACE_SCOPE,
) -> Path:
    runtime_tags = runtime_tags or ensure_fluxolot_runtime_config()
    numeric_tags = [tag for tag in runtime_tags if tag_spec_for_runtime_tag(tag).trace]
    row = {
        "Chart Scope": scope,
        "ID (optional)": "1",
        "Name": FLUXOLOT_LIVE_SCOPE_NAME,
        "display order (optional)": "1",
    }
    row.update({f"Tag {index}": tag.full_path for index, tag in enumerate(numeric_tags, start=1)})
    write_csv_rows(path, [row], fieldnames=list(row))
    return Path(path)


def ensure_fluxolot_live_scope(runtime_tags: list[RuntimeTag] | None = None):
    from flux.plane.services import ensure_series_for_full_path
    from flux.spot.models import LiveCardDefinition, LiveCardPointDefinition, LiveScope

    runtime_tags = runtime_tags or ensure_fluxolot_runtime_config()
    with transaction.atomic():
        scope, _created = LiveScope.objects.update_or_create(
            slug=FLUXOLOT_LIVE_SCOPE,
            defaults={
                "name": FLUXOLOT_LIVE_SCOPE_NAME,
                "description": "Fluxolot Fishtank proof-of-status current state.",
                "enabled": True,
            },
        )
        scope.cards.all().delete()
        for card_order, (tank, group, kind, tags) in enumerate(live_card_groups(runtime_tags), start=1):
            card = LiveCardDefinition.objects.create(
                scope=scope,
                title=f"{tank.owner} {kind}",
                group=group,
                kind=kind,
                sort_order=card_order,
                enabled=True,
            )
            for point_order, tag in enumerate(tags, start=1):
                LiveCardPointDefinition.objects.create(
                    card=card,
                    series=ensure_series_for_full_path(tag.full_path),
                    label=point_label_for_card(tag),
                    full_path=tag.full_path,
                    sort_order=point_order,
                    enabled=True,
                )
    return scope


def ensure_fluxolot_trace_profiles(runtime_tags: list[RuntimeTag] | None = None, *, cache_window_minutes: int = 10080):
    from flux.plane.services import ensure_series_for_full_path
    from flux.trace.models import TraceProfile, TraceSignal

    runtime_tags = runtime_tags or ensure_fluxolot_runtime_config()
    trace_tags_by_tank = {
        tank.key: [
            tag
            for tag in runtime_tags
            if tank_for_runtime_tag(tag).key == tank.key and tag_spec_for_runtime_tag(tag).trace
        ]
        for tank in FLUXOLOT_TANKS
    }
    profiles = []
    with transaction.atomic():
        for tank in FLUXOLOT_TANKS:
            trace_tags = trace_tags_by_tank[tank.key]
            profile, _created = TraceProfile.objects.update_or_create(
                key=fluxolot_trace_profile_key(tank),
                defaults={
                    "label": tank.display_name,
                    "enabled": True,
                    "cache_enabled": True,
                    "cache_window_minutes": cache_window_minutes,
                    "sync_interval_seconds": 60,
                    "history_provider": "Core Historian",
                },
            )
            for sort_order, tag in enumerate(trace_tags, start=1):
                spec = tag_spec_for_runtime_tag(tag)
                TraceSignal.objects.update_or_create(
                    profile=profile,
                    tag=tag,
                    defaults={
                        "label": tag.display_name,
                        "series": ensure_series_for_full_path(tag.full_path),
                        "unit": spec.units,
                        "axis_key": trace_axis_key(spec),
                        "axis_label": spec.kind,
                        "axis_unit": spec.units,
                        "range_min": spec.min_value,
                        "range_max": spec.max_value,
                        "sort_order": sort_order,
                        "default_visible": True,
                        "cache_enabled": True,
                    },
                )
            profile.signals.exclude(tag__in=trace_tags).delete()
            profiles.append(profile)
        TraceProfile.objects.filter(key=FLUXOLOT_TRACE_PROFILE).exclude(key__in=[profile.key for profile in profiles]).update(enabled=False)
    return profiles


def ensure_fluxolot_trace_profile(runtime_tags: list[RuntimeTag] | None = None):
    return ensure_fluxolot_trace_profiles(runtime_tags)[0]


def fluxolot_live_csv_fields() -> list[str]:
    return [
        "scope",
        "scope_name",
        "description",
        "card",
        "group",
        "kind",
        "card_order",
        "point",
        "full_path",
        "point_order",
    ]


def fluxolot_trace_csv_fields() -> list[str]:
    return [
        "full_path",
        "display_name",
        "asset_name",
        "engineering_units",
        "value",
        "quality_code",
        "value_timestamp",
        "read_at",
    ]


def fluxolot_live_csv_rows(runtime_tags: list[RuntimeTag] | None = None) -> list[dict[str, Any]]:
    runtime_tags = runtime_tags or ensure_fluxolot_runtime_config()
    rows = []
    for card_order, (tank, group, kind, tags) in enumerate(live_card_groups(runtime_tags), start=1):
        for point_order, tag in enumerate(tags, start=1):
            rows.append(
                {
                    "scope": FLUXOLOT_LIVE_SCOPE,
                    "scope_name": FLUXOLOT_LIVE_SCOPE_NAME,
                    "description": "Fluxolot Fishtank proof-of-status runtime tags",
                    "card": f"{tank.owner} {kind}",
                    "group": group,
                    "kind": kind,
                    "card_order": card_order,
                    "point": tag.display_name,
                    "full_path": tag.full_path,
                    "point_order": point_order,
                }
            )
    return rows


def fluxolot_trace_csv_row(sample: TagSample) -> dict[str, Any]:
    return {
        "full_path": sample.tag.full_path,
        "display_name": sample.tag.display_name,
        "asset_name": sample.tag.asset_name,
        "engineering_units": sample.tag.engineering_units,
        "value": sample.value,
        "quality_code": sample.quality_code,
        "value_timestamp": sample.value_timestamp.isoformat(),
        "read_at": sample.read_at.isoformat(),
    }


def ensure_fluxolot_field_config() -> tuple[list[FieldEndpoint], list[DeviceConfig], list[TagConfig]]:
    endpoints = []
    devices = []
    tags = []
    for tank in FLUXOLOT_TANKS:
        endpoint, _created = FieldEndpoint.objects.update_or_create(
            name=tank.endpoint_name,
            defaults={
                "endpoint_url": tank.endpoint_url,
                "application_uri": f"urn:flux:fluxolot-fishtank:{tank.key}",
                "product_uri": "urn:flux:fluxolot-fishtank",
                "namespace_uri": f"urn:flux:fluxolot-fishtank:{tank.key}",
                "enabled": True,
                "security_policy": "None",
                "status": FieldEndpoint.Status.DISABLED,
            },
        )
        endpoints.append(endpoint)
        device = upsert_device_config(
            namespace=f"endpoint:{endpoint.name}",
            name=tank.device_name,
            device_type="Fluxolot Fishtank Controller",
            endpoint=endpoint,
            browse_path=tank.owner,
            enabled=True,
            description=f"{tank.display_name} persistent verification fixture",
            config={
                "fixture": FLUXOLOT_FIXTURE,
                "persistent": True,
                "tank_key": tank.key,
                "owner": tank.owner,
                "cell": {"group": "Tank", "kind": "Fish Tank"},
            },
        )
        devices.append(device)
        active_names = {spec.name for spec in FLUXOLOT_TAGS}
        for spec in FLUXOLOT_TAGS:
            tag = upsert_tag_config(
                sim_device=device,
                provider=endpoint.name,
                tagpath=f"{tank.device_name}/{spec.name}",
                tag_name=spec.name,
                data_type=spec.data_type,
                update_rate_ms=spec.update_rate_ms,
                simulation_type=spec.simulation_type,
                min_value=spec.min_value,
                max_value=spec.max_value,
                variance=0.0,
                initial_value=spec.initial_value,
                enabled=True,
                materialized=True,
                description=spec.label,
                config={
                    "fixture": FLUXOLOT_FIXTURE,
                    "tank_key": tank.key,
                    "owner": tank.owner,
                    "label": spec.label,
                    "units": spec.units,
                    "type": spec.cell_type,
                    "instrument": spec.instrument,
                    "group": spec.group,
                    "kind": spec.kind,
                    "trace": spec.trace,
                    "cell": {"group": spec.group, "kind": spec.kind},
                },
            )
            tags.append(tag)
        disable_materialized_configs(device, active_names)
    return endpoints, devices, tags


def ensure_fluxolot_runtime_config(field_tags: list[TagConfig] | None = None) -> list[RuntimeTag]:
    if field_tags is None:
        _endpoints, _devices, field_tags = ensure_fluxolot_field_config()
    config = scheduler_config()
    schedule, _created = TagSchedule.objects.update_or_create(
        name=FLUXOLOT_SCHEDULE_NAME,
        defaults={"interval_seconds": config.hot_interval_seconds, "enabled": True},
    )
    runtime_tags = []
    for field_tag in sorted(field_tags, key=lambda tag: (tag.sim_device.base_device.name, tag.name)):
        tank = tank_for_device(field_tag.sim_device)
        spec = fluxolot_specs_by_name()[field_tag.name]
        runtime_tag, _created = RuntimeTag.objects.update_or_create(
            provider="default",
            path=fluxolot_runtime_path(tank, field_tag.name),
            defaults={
                "display_name": f"{tank.owner} {spec.label}",
                "asset_name": tank.display_name,
                "engineering_units": spec.units,
                "category": RuntimeTag.Category.SIMULATION,
                "schedule": schedule,
                "enabled": True,
            },
        )
        runtime_tags.append(runtime_tag)
    return assign_balancer_codes(runtime_tags, config=config)


def seed_fluxolot_history(
    runtime_tags: list[RuntimeTag] | None = None,
    *,
    history_days: int = 30,
    history_interval_minutes: int = 60,
    batch_size: int = 5000,
) -> int:
    runtime_tags = runtime_tags or ensure_fluxolot_runtime_config()
    history_days = max(history_days, 1)
    history_interval_minutes = max(history_interval_minutes, 1)
    end = timezone.now().replace(second=0, microsecond=0)
    start = end - timezone.timedelta(days=history_days)
    tag_ids = [tag.id for tag in runtime_tags]
    TagSample.objects.filter(tag_id__in=tag_ids).delete()

    total = 0
    samples = []
    current = start
    while current <= end:
        elapsed_minutes = int((current - start).total_seconds() // 60)
        for tag in runtime_tags:
            value = fluxolot_value(tag, elapsed_minutes)
            samples.append(
                TagSample(
                    tag=tag,
                    value=value,
                    quality_code="Good",
                    value_timestamp=current,
                    read_at=current,
                )
            )
            if len(samples) >= batch_size:
                TagSample.objects.bulk_create(samples, batch_size=batch_size)
                total += len(samples)
                samples = []
        current += timezone.timedelta(minutes=history_interval_minutes)
    if samples:
        TagSample.objects.bulk_create(samples, batch_size=batch_size)
        total += len(samples)

    now = timezone.now()
    latest_elapsed = history_days * 24 * 60
    for tag in runtime_tags:
        LatestTagValue.objects.update_or_create(
            tag=tag,
            defaults={
                "value": fluxolot_value(tag, latest_elapsed),
                "quality_code": "Good",
                "value_timestamp": end,
                "read_at": now,
            },
        )
    return total


def fluxolot_runtime_path(tank: FluxolotTankSpec, tag_name: str) -> str:
    return f"{FLUXOLOT_TAG_FOLDER}/{tank.device_name}_{tag_name}"


def fluxolot_trace_profile_key(tank: FluxolotTankSpec) -> str:
    return f"{FLUXOLOT_TRACE_PROFILE_PREFIX}-{tank.key}"


def fluxolot_specs_by_name() -> dict[str, FluxolotTagSpec]:
    return {spec.name: spec for spec in FLUXOLOT_TAGS}


def tank_for_device(device: DeviceConfig) -> FluxolotTankSpec:
    for tank in FLUXOLOT_TANKS:
        if tank.device_name == device.base_device.name:
            return tank
    raise ValueError(f"No Fluxolot tank spec for device {device.base_device.name!r}")


def tank_for_runtime_tag(tag: RuntimeTag) -> FluxolotTankSpec:
    for tank in FLUXOLOT_TANKS:
        if f"/{tank.device_name}_" in tag.path:
            return tank
    raise ValueError(f"No Fluxolot tank spec for runtime tag {tag.full_path!r}")


def tag_spec_for_runtime_tag(tag: RuntimeTag) -> FluxolotTagSpec:
    for spec in FLUXOLOT_TAGS:
        if tag.path.endswith("_" + spec.name):
            return spec
    raise ValueError(f"No Fluxolot tag spec for runtime tag {tag.full_path!r}")


def fluxolot_value(tag: RuntimeTag, elapsed_minutes: int) -> Any:
    tank = tank_for_runtime_tag(tag)
    spec = tag_spec_for_runtime_tag(tag)
    if spec.data_type == Tag.DataType.BOOL:
        if spec.simulation_type == TagConfig.SimulationType.STATIC:
            return spec.initial_value.lower() == "true"
        return ((elapsed_minutes // 180) + tank.sort_order + int(spec.phase * 10)) % 2 == 0
    if spec.data_type == Tag.DataType.INT:
        assert spec.max_value is not None
        cycle = int(spec.max_value) + 1
        return int(max(0, spec.max_value - ((elapsed_minutes + tank.sort_order * 17) % cycle)))
    if spec.data_type == Tag.DataType.STRING:
        return spec.initial_value
    assert spec.min_value is not None
    assert spec.max_value is not None
    midpoint = (spec.min_value + spec.max_value) / 2
    amplitude = (spec.max_value - spec.min_value) * 0.18
    day_fraction = elapsed_minutes / 1440
    value = midpoint + amplitude * math.sin((day_fraction * math.tau) + spec.phase + tank.phase_offset)
    return round(value, 3)


def live_card_groups(runtime_tags: list[RuntimeTag]) -> list[tuple[FluxolotTankSpec, str, str, list[RuntimeTag]]]:
    grouped: dict[tuple[str, str, str], list[RuntimeTag]] = {}
    for tag in runtime_tags:
        tank = tank_for_runtime_tag(tag)
        spec = tag_spec_for_runtime_tag(tag)
        grouped.setdefault((tank.key, spec.group, spec.kind), []).append(tag)
    rows = []
    for tank in FLUXOLOT_TANKS:
        for group, kind in (("Pump", "Recirculation Pump"), ("Tank", "Fish Tank"), ("Light", "UV Light"), ("Feeder", "Treat Feeder")):
            tags = sorted(grouped.get((tank.key, group, kind), []), key=lambda item: tag_spec_order(tag_spec_for_runtime_tag(item)))
            rows.append((tank, group, kind, tags))
    return rows


def point_label_for_card(tag: RuntimeTag) -> str:
    spec = tag_spec_for_runtime_tag(tag)
    return spec.label


def trace_axis_key(spec: FluxolotTagSpec) -> str:
    if spec.units == "%":
        return "percent"
    if spec.units == "psi":
        return "pressure"
    if spec.units == "degF":
        return "temperature"
    return "process"


def tag_spec_order(spec: FluxolotTagSpec) -> int:
    return list(FLUXOLOT_TAGS).index(spec)


def write_csv_rows(path: str | Path, rows: list[dict[str, Any]], *, fieldnames: list[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def wide_fieldnames(rows: list[dict[str, Any]]) -> list[str]:
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    return fieldnames
