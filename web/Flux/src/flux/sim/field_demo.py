from __future__ import annotations

from dataclasses import dataclass

from flux.base.models import Tag
from flux.sim.models import FieldEndpoint
from flux.sim.kernel_sync import disable_materialized_configs, upsert_device_config, upsert_tag_config
from flux.sim.models import TagConfig


DEMO_ENDPOINT_NAME = "local-sim"
DEMO_ENDPOINT_URL = "opc.tcp://localhost:4840/flux/field"
DEMO_TAG_FOLDER = "FluxLiveDemo"


@dataclass(frozen=True)
class DemoTag:
    name: str
    data_type: str
    update_rate_ms: int
    simulation_type: str
    min_value: float | None = None
    max_value: float | None = None
    variance: float = 0.0
    initial_value: str = ""
    label: str = ""
    units: str = ""


@dataclass(frozen=True)
class DemoDevice:
    name: str
    equipment_type: str
    tags: tuple[DemoTag, ...]


DEMO_DEVICES = (
    DemoDevice(
        name="DemoWell_01",
        equipment_type="Well",
        tags=(
            DemoTag("TUBING_PRESSURE", Tag.DataType.FLOAT, 1000, TagConfig.SimulationType.WAVE, 250, 900, 0.25, "525", "Tubing Pressure", "psi"),
            DemoTag("CASING_PRESSURE", Tag.DataType.FLOAT, 1000, TagConfig.SimulationType.WAVE, 400, 1200, 0.35, "740", "Casing Pressure", "psi"),
            DemoTag("LOAD_FACTOR", Tag.DataType.FLOAT, 5000, TagConfig.SimulationType.WAVE, 0, 100, 0.1, "65", "Load Factor", "%"),
            DemoTag("STATUS", Tag.DataType.STRING, 3000, TagConfig.SimulationType.STATIC, initial_value="RUN", label="Status"),
        ),
    ),
    DemoDevice(
        name="DemoWell_02",
        equipment_type="Well",
        tags=(
            DemoTag("TUBING_PRESSURE", Tag.DataType.FLOAT, 1000, TagConfig.SimulationType.WAVE, 180, 760, 0.2, "420", "Tubing Pressure", "psi"),
            DemoTag("CASING_PRESSURE", Tag.DataType.FLOAT, 1000, TagConfig.SimulationType.WAVE, 350, 980, 0.3, "610", "Casing Pressure", "psi"),
            DemoTag("LOAD_FACTOR", Tag.DataType.FLOAT, 5000, TagConfig.SimulationType.WAVE, 0, 100, 0.1, "48", "Load Factor", "%"),
            DemoTag("STATUS", Tag.DataType.STRING, 3000, TagConfig.SimulationType.STATIC, initial_value="IDLE", label="Status"),
        ),
    ),
    DemoDevice(
        name="DemoMeter_01",
        equipment_type="Meter",
        tags=(
            DemoTag("FLOW_RATE", Tag.DataType.FLOAT, 1000, TagConfig.SimulationType.WAVE, 0, 5000, 1.0, "2400", "Flow Rate", "mcf/d"),
            DemoTag("VOLUME_TODAY", Tag.DataType.FLOAT, 5000, TagConfig.SimulationType.RAMP, 0, 25000, 0, "1000", "Volume Today", "mcf"),
            DemoTag("LINE_PRESSURE", Tag.DataType.FLOAT, 1000, TagConfig.SimulationType.WAVE, 200, 900, 0.25, "510", "Line Pressure", "psi"),
        ),
    ),
    DemoDevice(
        name="DemoMeter_02",
        equipment_type="Meter",
        tags=(
            DemoTag("FLOW_RATE", Tag.DataType.FLOAT, 1000, TagConfig.SimulationType.WAVE, 0, 4200, 0.8, "1800", "Flow Rate", "mcf/d"),
            DemoTag("VOLUME_TODAY", Tag.DataType.FLOAT, 5000, TagConfig.SimulationType.RAMP, 0, 18000, 0, "750", "Volume Today", "mcf"),
            DemoTag("LINE_PRESSURE", Tag.DataType.FLOAT, 1000, TagConfig.SimulationType.WAVE, 150, 740, 0.2, "430", "Line Pressure", "psi"),
        ),
    ),
    DemoDevice(
        name="DemoTank_01",
        equipment_type="Tank",
        tags=(
            DemoTag("LEVEL", Tag.DataType.FLOAT, 1000, TagConfig.SimulationType.WAVE, 0, 100, 0.05, "55", "Level", "%"),
            DemoTag("VOLUME", Tag.DataType.FLOAT, 5000, TagConfig.SimulationType.WAVE, 0, 500, 0.1, "275", "Volume", "bbl"),
            DemoTag("HIGH_LEVEL_ALARM", Tag.DataType.BOOL, 10000, TagConfig.SimulationType.TOGGLE, initial_value="false", label="High Level Alarm"),
        ),
    ),
    DemoDevice(
        name="DemoTank_02",
        equipment_type="Tank",
        tags=(
            DemoTag("LEVEL", Tag.DataType.FLOAT, 1000, TagConfig.SimulationType.WAVE, 0, 100, 0.05, "37", "Level", "%"),
            DemoTag("VOLUME", Tag.DataType.FLOAT, 5000, TagConfig.SimulationType.WAVE, 0, 500, 0.1, "185", "Volume", "bbl"),
            DemoTag("HIGH_LEVEL_ALARM", Tag.DataType.BOOL, 10000, TagConfig.SimulationType.TOGGLE, initial_value="false", label="High Level Alarm"),
        ),
    ),
)


def ensure_demo_field_config() -> tuple[FieldEndpoint, list[TagConfig]]:
    endpoint, _created = FieldEndpoint.objects.update_or_create(
        name=DEMO_ENDPOINT_NAME,
        defaults={
            "endpoint_url": DEMO_ENDPOINT_URL,
            "application_uri": "urn:flux:field",
            "product_uri": "urn:flux:field",
            "namespace_uri": "urn:flux:field:sim",
            "enabled": True,
            "security_policy": "None",
        },
    )
    tags: list[TagConfig] = []
    for demo_device in DEMO_DEVICES:
        device = upsert_device_config(
            namespace=f"endpoint:{endpoint.name}",
            name=demo_device.name,
            device_type=demo_device.equipment_type,
            endpoint=endpoint,
            browse_path="Pad Overview",
            enabled=True,
            description=f"Flux Spot demo {demo_device.equipment_type.lower()}",
        )
        active_names = {tag.name for tag in demo_device.tags}
        for demo_tag in demo_device.tags:
            tag = upsert_tag_config(
                sim_device=device,
                provider=endpoint.name,
                tagpath=f"{demo_device.name}/{demo_tag.name}",
                tag_name=demo_tag.name,
                data_type=demo_tag.data_type,
                update_rate_ms=demo_tag.update_rate_ms,
                simulation_type=demo_tag.simulation_type,
                min_value=demo_tag.min_value,
                max_value=demo_tag.max_value,
                variance=demo_tag.variance,
                initial_value=demo_tag.initial_value,
                enabled=True,
                materialized=True,
                description=demo_tag.label,
            )
            tags.append(tag)
        disable_materialized_configs(device, active_names)
    return endpoint, tags


def demo_tag_metadata() -> dict[tuple[str, str], DemoTag]:
    return {(device.name, tag.name): tag for device in DEMO_DEVICES for tag in device.tags}
