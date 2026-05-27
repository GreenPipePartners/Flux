from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from flux_build.targets.logix_l5k import build_logix_l5k
from flux_build.targets.logix_l5x import build_logix_l5x
from flux_mine.plc.models import (
    PlcController,
    PlcProgram,
    PlcProject,
    PlcRoutine,
    PlcRung,
    PlcTag,
    PlcTask,
    parse_rll_instructions,
)


KIT_MARKER_RE = re.compile(r"fx_(?P<kind>tag|par|device)_(?P<key>[A-Za-z0-9_]+)")


class KitError(ValueError):
    """Raised when a kit template or instance cannot be expanded safely."""


@dataclass(frozen=True)
class KitInstance:
    name: str
    devices: dict[str, str]
    tags: dict[str, str]
    pars: tuple[str, ...]
    routine: str | None = None
    lbl: str | None = None

    def __post_init__(self) -> None:
        if bool(self.routine) == bool(self.lbl):
            raise KitError("KitInstance requires exactly one of routine or lbl")


@dataclass(frozen=True)
class DisplayDestination:
    name: str
    technology: Literal["perspective", "vision"]
    path: str
    width: int = 640
    height: int = 360


@dataclass(frozen=True)
class DisplayPlacement:
    instance: str
    x: int
    y: int
    width: int = 157
    height: int = 50


@dataclass(frozen=True)
class KitBuildResult:
    plc_project: PlcProject
    l5k_text: str
    l5x_bytes: bytes
    perspective_view: dict[str, object]
    vision_screen: dict[str, object]
    manifest: dict[str, object]


def build_hello_world_kit_package(
    *,
    instances: tuple[KitInstance, ...],
    perspective_destination: DisplayDestination,
    vision_destination: DisplayDestination,
    placements: tuple[DisplayPlacement, ...],
    controller_name: str = "hello_world_kit",
    program_name: str = "MainProgram",
    main_routine_name: str = "MainRoutine",
) -> KitBuildResult:
    validate_destinations(perspective_destination, vision_destination)
    validate_instances_and_placements(instances, placements)
    placement_by_instance = {placement.instance: placement for placement in placements}

    plc_project = build_hello_world_plc_project(
        instances=instances,
        controller_name=controller_name,
        program_name=program_name,
        main_routine_name=main_routine_name,
    )
    perspective_view = render_perspective_destination(
        instances=instances,
        destination=perspective_destination,
        placements=placement_by_instance,
    )
    vision_screen = render_vision_destination_manifest(
        instances=instances,
        destination=vision_destination,
        placements=placement_by_instance,
    )
    manifest = render_manifest(
        instances=instances,
        perspective_destination=perspective_destination,
        vision_destination=vision_destination,
        placements=placements,
        controller_name=controller_name,
        program_name=program_name,
        main_routine_name=main_routine_name,
    )
    return KitBuildResult(
        plc_project=plc_project,
        l5k_text=build_logix_l5k(plc_project).decode("utf-8"),
        l5x_bytes=build_logix_l5x(plc_project),
        perspective_view=perspective_view,
        vision_screen=vision_screen,
        manifest=manifest,
    )


def build_hello_world_plc_project(
    *,
    instances: tuple[KitInstance, ...],
    controller_name: str,
    program_name: str,
    main_routine_name: str,
) -> PlcProject:
    tags: list[PlcTag] = []
    main_rungs: list[PlcRung] = []
    routines: list[PlcRoutine] = []
    seen_tags: set[str] = set()

    for instance in instances:
        for tag in hello_world_tags(instance, scope=program_name):
            if tag.name in seen_tags:
                raise KitError(f"duplicate generated tag name {tag.name!r}")
            seen_tags.add(tag.name)
            tags.append(tag)

        if instance.routine:
            routines.append(hello_world_routine(instance, instance.routine))
            main_rungs.append(plc_rung(len(main_rungs), f"JSR({instance.routine},0);"))
        elif instance.lbl:
            for text in hello_world_body_rungs(instance):
                main_rungs.append(plc_rung(len(main_rungs), text))

    main_routine = PlcRoutine(
        name=main_routine_name,
        routine_type="RLL",
        rungs=tuple(main_rungs),
        raw={"Name": main_routine_name, "Type": "RLL"},
    )
    program = PlcProgram(
        name=program_name,
        main_routine_name=main_routine_name,
        tags=tuple(tags),
        routines=(main_routine, *routines),
        raw={"Name": program_name, "MainRoutineName": main_routine_name, "Disabled": "false", "UseAsFolder": "false"},
    )
    controller = PlcController(
        name=controller_name,
        processor_type="1756-L71",
        major_version=37,
        programs=(program,),
        tasks=(
            PlcTask(
                name="MainTask",
                task_type="CONTINUOUS",
                priority=10,
                rate=10,
                watchdog=500,
                scheduled_programs=(program_name,),
                raw={"Name": "MainTask", "Type": "CONTINUOUS", "Rate": "10", "Priority": "10", "Watchdog": "500"},
            ),
        ),
        raw={"Name": controller_name, "ProcessorType": "1756-L71", "MajorRev": "37", "MinorRev": "0"},
    )
    return PlcProject(controllers=(controller,))


def write_hello_world_kit_package(result: KitBuildResult, output_dir: str | Path) -> dict[str, Path]:
    root = Path(output_dir)
    plc_dir = root / "plc"
    perspective_dir = root / "com.inductiveautomation.perspective" / "views" / "kit_display"
    vision_dir = root / "flux_build_vision" / "screens"
    plc_dir.mkdir(parents=True, exist_ok=True)
    perspective_dir.mkdir(parents=True, exist_ok=True)
    vision_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "manifest": root / "kit_manifest.json",
        "l5k": plc_dir / "hello_world_kit_generated.L5K",
        "l5x": plc_dir / "hello_world_kit_generated.L5X",
        "perspective_view": perspective_dir / "view.json",
        "perspective_resource": perspective_dir / "resource.json",
        "vision_screen": vision_dir / "kit_display.json",
    }
    paths["manifest"].write_text(_json(result.manifest), encoding="utf-8")
    paths["l5k"].write_text(result.l5k_text, encoding="utf-8")
    paths["l5x"].write_bytes(result.l5x_bytes)
    paths["perspective_view"].write_text(_json(result.perspective_view), encoding="utf-8")
    paths["perspective_resource"].write_text(_json(perspective_resource()), encoding="utf-8")
    paths["vision_screen"].write_text(_json(result.vision_screen), encoding="utf-8")
    return paths


def validate_destinations(perspective: DisplayDestination, vision: DisplayDestination) -> None:
    if perspective.technology != "perspective":
        raise KitError("perspective_destination must use technology='perspective'")
    if vision.technology != "vision":
        raise KitError("vision_destination must use technology='vision'")


def validate_instances_and_placements(instances: tuple[KitInstance, ...], placements: tuple[DisplayPlacement, ...]) -> None:
    if len({instance.name for instance in instances}) != len(instances):
        raise KitError("kit instance names must be unique")
    placement_names = {placement.instance for placement in placements}
    missing_placements = [instance.name for instance in instances if instance.name not in placement_names]
    if missing_placements:
        raise KitError(f"missing display placement for kit instances: {', '.join(missing_placements)}")


def hello_world_tags(instance: KitInstance, *, scope: str) -> tuple[PlcTag, ...]:
    par_0 = par(instance, 0)
    par_1 = par(instance, 1)
    output = tag(instance, "hello")
    return (
        string_tag(par_0, value=par_0, scope=scope),
        bool_tag(f"{par_0}_latch", scope=scope),
        timer_tag(f"{par_0}_TON", scope=scope),
        string_tag(par_1, value=par_1, scope=scope),
        timer_tag(f"{par_1}_TON", scope=scope),
        string_tag(output, value="", scope=scope),
    )


def hello_world_routine(instance: KitInstance, routine_name: str) -> PlcRoutine:
    return PlcRoutine(
        name=routine_name,
        routine_type="RLL",
        rungs=tuple(plc_rung(index, text) for index, text in enumerate(hello_world_body_rungs(instance))),
        raw={"Name": routine_name, "Type": "RLL"},
    )


def hello_world_body_rungs(instance: KitInstance) -> tuple[str, ...]:
    return tuple(expand_kit_markers(rung, instance) for rung in HELLO_WORLD_RUNG_TEMPLATES)


def plc_rung(number: int, text: str) -> PlcRung:
    return PlcRung(
        number=number,
        rung_type="N",
        text=text,
        instructions=parse_rll_instructions(text),
        raw={"Number": str(number), "Type": "N"},
    )


def string_tag(name: str, *, value: str, scope: str) -> PlcTag:
    return PlcTag(
        name=name,
        data_type="STRING",
        scope=scope,
        tag_type="Base",
        constant=False,
        external_access="Read/Write",
        raw={
            "TagType": "Base",
            "DataType": "STRING",
            "Constant": "false",
            "ExternalAccess": "Read/Write",
            "data": (
                {"format": "L5K", "text": string_l5k_payload(value)},
                {"format": "String", "attributes": {"Length": str(len(value))}, "text": f"'{value}'"},
            ),
        },
    )


def bool_tag(name: str, *, scope: str) -> PlcTag:
    return PlcTag(
        name=name,
        data_type="BOOL",
        scope=scope,
        tag_type="Base",
        radix="Decimal",
        constant=False,
        external_access="Read/Write",
        raw={
            "TagType": "Base",
            "DataType": "BOOL",
            "Radix": "Decimal",
            "Constant": "false",
            "ExternalAccess": "Read/Write",
            "data": (
                {"format": "L5K", "text": "0"},
                {"format": "Decorated", "children": ('<DataValue DataType="BOOL" Radix="Decimal" Value="0" />',)},
            ),
        },
    )


def timer_tag(name: str, *, scope: str) -> PlcTag:
    return PlcTag(
        name=name,
        data_type="TIMER",
        scope=scope,
        tag_type="Base",
        constant=False,
        external_access="Read/Write",
        raw={
            "TagType": "Base",
            "DataType": "TIMER",
            "Constant": "false",
            "ExternalAccess": "Read/Write",
            "data": (
                {"format": "L5K", "text": "[0,1000,0]"},
                {"format": "Decorated", "children": (timer_structure_xml(),)},
            ),
        },
    )


def expand_kit_markers(text: str, instance: KitInstance) -> str:
    def replace(match: re.Match[str]) -> str:
        kind = match.group("kind")
        key = match.group("key")
        if kind == "tag":
            return tag(instance, key)
        if kind == "device":
            return device(instance, f"device_{key}")
        if kind == "par":
            index_text, _, suffix = key.partition("_")
            if not index_text.isdigit():
                raise KitError(f"invalid parameter placeholder fx_par_{key}")
            value = par(instance, int(index_text))
            return f"{value}_{suffix}" if suffix else value
        raise KitError(f"unsupported kit marker {match.group(0)!r}")

    rendered = KIT_MARKER_RE.sub(replace, text)
    if "fx_" in rendered:
        raise KitError(f"unresolved kit marker in {rendered!r}")
    return rendered


def render_perspective_destination(
    *,
    instances: tuple[KitInstance, ...],
    destination: DisplayDestination,
    placements: dict[str, DisplayPlacement],
) -> dict[str, object]:
    return {
        "custom": {},
        "params": {},
        "props": {"defaultSize": {"width": destination.width, "height": destination.height}},
        "root": {
            "type": "ia.container.coord",
            "meta": {"name": destination.name},
            "props": {"mode": "percent"},
            "children": [perspective_label(instance, placements[instance.name]) for instance in instances],
        },
    }


def perspective_label(instance: KitInstance, placement: DisplayPlacement) -> dict[str, object]:
    return {
        "type": "ia.display.label",
        "meta": {"name": f"{instance.name}_label"},
        "position": placement_dict(placement),
        "propConfig": {
            "props.text": {
                "binding": {
                    "type": "tag",
                    "config": {"mode": "direct", "fallbackDelay": 2.5, "tagPath": display_tag_path(instance)},
                }
            }
        },
    }


def render_vision_destination_manifest(
    *,
    instances: tuple[KitInstance, ...],
    destination: DisplayDestination,
    placements: dict[str, DisplayPlacement],
) -> dict[str, object]:
    return {
        "schema": "flux.build.kit.vision_destination.v1",
        "note": "Vision binary window/template emission is not implemented; this manifest is the placement contract.",
        "name": destination.name,
        "path": destination.path,
        "coordinateContainer": {"width": destination.width, "height": destination.height},
        "objects": [
            {
                "name": f"{instance.name}_label",
                "template": "hello_world_display",
                "tagPath": display_tag_path(instance),
                "position": placement_dict(placements[instance.name]),
            }
            for instance in instances
        ],
    }


def render_manifest(
    *,
    instances: tuple[KitInstance, ...],
    perspective_destination: DisplayDestination,
    vision_destination: DisplayDestination,
    placements: tuple[DisplayPlacement, ...],
    controller_name: str,
    program_name: str,
    main_routine_name: str,
) -> dict[str, object]:
    return {
        "schema": "flux.build.kit.package.v1",
        "kit": "hello_world_display",
        "controller": controller_name,
        "program": program_name,
        "mainRoutine": main_routine_name,
        "instances": [
            {
                "name": instance.name,
                "devices": instance.devices,
                "tags": instance.tags,
                "pars": list(instance.pars),
                "routine": instance.routine,
                "lbl": instance.lbl,
                "displayTagPath": display_tag_path(instance),
            }
            for instance in instances
        ],
        "destinations": {
            "perspective": destination_dict(perspective_destination),
            "vision": destination_dict(vision_destination),
        },
        "placements": [placement_dict(placement) | {"instance": placement.instance} for placement in placements],
    }


def default_hello_world_kit_instances() -> tuple[KitInstance, ...]:
    return (
        KitInstance(
            name="hello_world",
            devices={"device_01": "hello_plc"},
            tags={"hello": "hello_world"},
            pars=("hello", "world"),
            routine="hello_world_cycle",
        ),
        KitInstance(
            name="foo_bar",
            devices={"device_01": "hello_plc"},
            tags={"hello": "foo_bar"},
            pars=("foo", "bar"),
            lbl="foo_bar_inline",
        ),
        KitInstance(
            name="baz_bob",
            devices={"device_01": "hello_plc"},
            tags={"hello": "baz_bob"},
            pars=("baz", "bob"),
            lbl="baz_bob_inline",
        ),
    )


def default_hello_world_kit_placements() -> tuple[DisplayPlacement, ...]:
    return (
        DisplayPlacement(instance="hello_world", x=18, y=24),
        DisplayPlacement(instance="foo_bar", x=18, y=94),
        DisplayPlacement(instance="baz_bob", x=18, y=164),
    )


def default_perspective_destination() -> DisplayDestination:
    return DisplayDestination(
        name="hello_world_kit_perspective_screen",
        technology="perspective",
        path="generated/hello_world_kit",
    )


def default_vision_destination() -> DisplayDestination:
    return DisplayDestination(
        name="hello_world_kit_vision_screen",
        technology="vision",
        path="generated/hello_world_kit",
    )


def build_default_hello_world_kit_package() -> KitBuildResult:
    return build_hello_world_kit_package(
        instances=default_hello_world_kit_instances(),
        perspective_destination=default_perspective_destination(),
        vision_destination=default_vision_destination(),
        placements=default_hello_world_kit_placements(),
    )


def display_tag_path(instance: KitInstance) -> str:
    return f"[{device(instance, 'device_01')}]{tag(instance, 'hello')}"


def par(instance: KitInstance, index: int) -> str:
    try:
        return instance.pars[index]
    except IndexError as exc:
        raise KitError(f"missing parameter fx_par_{index} for kit instance {instance.name!r}") from exc


def tag(instance: KitInstance, key: str) -> str:
    try:
        return instance.tags[key]
    except KeyError as exc:
        raise KitError(f"missing tag pointer fx_tag_{key} for kit instance {instance.name!r}") from exc


def device(instance: KitInstance, key: str) -> str:
    try:
        return instance.devices[key]
    except KeyError as exc:
        raise KitError(f"missing device pointer fx_{key} for kit instance {instance.name!r}") from exc


def string_l5k_payload(value: str) -> str:
    if len(value) > 82:
        raise KitError("STRING literals longer than 82 characters are not supported by this kit slice")
    return f"[{len(value)},'{value}{'$00' * (82 - len(value))}'\n\t\t\t\t]"


def timer_structure_xml() -> str:
    return (
        '<Structure DataType="TIMER">'
        '<DataValueMember Name="PRE" DataType="DINT" Radix="Decimal" Value="1000" />'
        '<DataValueMember Name="ACC" DataType="DINT" Radix="Decimal" Value="0" />'
        '<DataValueMember Name="EN" DataType="BOOL" Value="0" />'
        '<DataValueMember Name="TT" DataType="BOOL" Value="0" />'
        '<DataValueMember Name="DN" DataType="BOOL" Value="0" />'
        "</Structure>"
    )


def destination_dict(destination: DisplayDestination) -> dict[str, object]:
    return {
        "name": destination.name,
        "technology": destination.technology,
        "path": destination.path,
        "width": destination.width,
        "height": destination.height,
    }


def placement_dict(placement: DisplayPlacement) -> dict[str, int]:
    return {"x": placement.x, "y": placement.y, "width": placement.width, "height": placement.height}


def perspective_resource() -> dict[str, object]:
    return {
        "scope": "G",
        "version": 1,
        "restricted": False,
        "overridable": True,
        "files": ["view.json"],
        "attributes": {},
    }


def _json(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


HELLO_WORLD_RUNG_TEMPLATES = (
    "XIO(fx_par_0_latch)TON(fx_par_0_TON,?,?);",
    "XIC(fx_par_0_TON.DN)OTL(fx_par_0_latch);",
    "XIC(fx_par_0_latch)TON(fx_par_1_TON,?,?);",
    "XIC(fx_par_1_TON.DN)OTU(fx_par_0_latch);",
    "[XIO(fx_par_0_latch) COP(fx_par_0,fx_tag_hello,1) ,XIC(fx_par_0_latch) COP(fx_par_1,fx_tag_hello,1) ];",
)


__all__ = [
    "DisplayDestination",
    "DisplayPlacement",
    "KitBuildResult",
    "KitError",
    "KitInstance",
    "build_default_hello_world_kit_package",
    "build_hello_world_kit_package",
    "build_hello_world_plc_project",
    "default_hello_world_kit_instances",
    "default_hello_world_kit_placements",
    "default_perspective_destination",
    "default_vision_destination",
    "expand_kit_markers",
    "write_hello_world_kit_package",
]
