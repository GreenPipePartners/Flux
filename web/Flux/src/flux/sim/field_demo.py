from __future__ import annotations

from dataclasses import dataclass

from flux.base.models import FieldDevice, FieldEndpoint, FieldTag


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
            DemoTag("TUBING_PRESSURE", FieldTag.DataType.FLOAT, 1000, FieldTag.SimulationType.WAVE, 250, 900, 0.25, "525", "Tubing Pressure", "psi"),
            DemoTag("CASING_PRESSURE", FieldTag.DataType.FLOAT, 1000, FieldTag.SimulationType.WAVE, 400, 1200, 0.35, "740", "Casing Pressure", "psi"),
            DemoTag("LOAD_FACTOR", FieldTag.DataType.FLOAT, 5000, FieldTag.SimulationType.WAVE, 0, 100, 0.1, "65", "Load Factor", "%"),
            DemoTag("STATUS", FieldTag.DataType.STRING, 3000, FieldTag.SimulationType.STATIC, initial_value="RUN", label="Status"),
        ),
    ),
    DemoDevice(
        name="DemoWell_02",
        equipment_type="Well",
        tags=(
            DemoTag("TUBING_PRESSURE", FieldTag.DataType.FLOAT, 1000, FieldTag.SimulationType.WAVE, 180, 760, 0.2, "420", "Tubing Pressure", "psi"),
            DemoTag("CASING_PRESSURE", FieldTag.DataType.FLOAT, 1000, FieldTag.SimulationType.WAVE, 350, 980, 0.3, "610", "Casing Pressure", "psi"),
            DemoTag("LOAD_FACTOR", FieldTag.DataType.FLOAT, 5000, FieldTag.SimulationType.WAVE, 0, 100, 0.1, "48", "Load Factor", "%"),
            DemoTag("STATUS", FieldTag.DataType.STRING, 3000, FieldTag.SimulationType.STATIC, initial_value="IDLE", label="Status"),
        ),
    ),
    DemoDevice(
        name="DemoMeter_01",
        equipment_type="Meter",
        tags=(
            DemoTag("FLOW_RATE", FieldTag.DataType.FLOAT, 1000, FieldTag.SimulationType.WAVE, 0, 5000, 1.0, "2400", "Flow Rate", "mcf/d"),
            DemoTag("VOLUME_TODAY", FieldTag.DataType.FLOAT, 5000, FieldTag.SimulationType.RAMP, 0, 25000, 0, "1000", "Volume Today", "mcf"),
            DemoTag("LINE_PRESSURE", FieldTag.DataType.FLOAT, 1000, FieldTag.SimulationType.WAVE, 200, 900, 0.25, "510", "Line Pressure", "psi"),
        ),
    ),
    DemoDevice(
        name="DemoMeter_02",
        equipment_type="Meter",
        tags=(
            DemoTag("FLOW_RATE", FieldTag.DataType.FLOAT, 1000, FieldTag.SimulationType.WAVE, 0, 4200, 0.8, "1800", "Flow Rate", "mcf/d"),
            DemoTag("VOLUME_TODAY", FieldTag.DataType.FLOAT, 5000, FieldTag.SimulationType.RAMP, 0, 18000, 0, "750", "Volume Today", "mcf"),
            DemoTag("LINE_PRESSURE", FieldTag.DataType.FLOAT, 1000, FieldTag.SimulationType.WAVE, 150, 740, 0.2, "430", "Line Pressure", "psi"),
        ),
    ),
    DemoDevice(
        name="DemoTank_01",
        equipment_type="Tank",
        tags=(
            DemoTag("LEVEL", FieldTag.DataType.FLOAT, 1000, FieldTag.SimulationType.WAVE, 0, 100, 0.05, "55", "Level", "%"),
            DemoTag("VOLUME", FieldTag.DataType.FLOAT, 5000, FieldTag.SimulationType.WAVE, 0, 500, 0.1, "275", "Volume", "bbl"),
            DemoTag("HIGH_LEVEL_ALARM", FieldTag.DataType.BOOL, 10000, FieldTag.SimulationType.TOGGLE, initial_value="false", label="High Level Alarm"),
        ),
    ),
    DemoDevice(
        name="DemoTank_02",
        equipment_type="Tank",
        tags=(
            DemoTag("LEVEL", FieldTag.DataType.FLOAT, 1000, FieldTag.SimulationType.WAVE, 0, 100, 0.05, "37", "Level", "%"),
            DemoTag("VOLUME", FieldTag.DataType.FLOAT, 5000, FieldTag.SimulationType.WAVE, 0, 500, 0.1, "185", "Volume", "bbl"),
            DemoTag("HIGH_LEVEL_ALARM", FieldTag.DataType.BOOL, 10000, FieldTag.SimulationType.TOGGLE, initial_value="false", label="High Level Alarm"),
        ),
    ),
)


def ensure_demo_field_config() -> tuple[FieldEndpoint, list[FieldTag]]:
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
    tags: list[FieldTag] = []
    for demo_device in DEMO_DEVICES:
        device, _created = FieldDevice.objects.update_or_create(
            endpoint=endpoint,
            name=demo_device.name,
            defaults={
                "device_type": demo_device.equipment_type,
                "browse_path": "Pad Overview",
                "enabled": True,
                "description": f"Flux Live demo {demo_device.equipment_type.lower()}",
            },
        )
        for demo_tag in demo_device.tags:
            tag, _created = FieldTag.objects.update_or_create(
                device=device,
                name=demo_tag.name,
                defaults={
                    "data_type": demo_tag.data_type,
                    "update_rate_ms": demo_tag.update_rate_ms,
                    "simulation_type": demo_tag.simulation_type,
                    "min_value": demo_tag.min_value,
                    "max_value": demo_tag.max_value,
                    "variance": demo_tag.variance,
                    "initial_value": demo_tag.initial_value,
                    "enabled": True,
                    "description": demo_tag.label,
                },
            )
            tags.append(tag)
    return endpoint, tags


def demo_tag_metadata() -> dict[tuple[str, str], DemoTag]:
    return {(device.name, tag.name): tag for device in DEMO_DEVICES for tag in device.tags}
