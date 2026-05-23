from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from flux_build.targets.rockwell import (
    BUILTIN_TYPES,
    IGNORED_ROCKWELL_TYPES,
    BuiltinMember,
    builtin_type_named,
    ignition_data_type,
)
from flux_mine.plc.models import PlcController, PlcDataType, PlcMember, PlcProject, PlcTag
from flux_mine.reconcile.plc_hmi import member_tokens, resolve_member_path


@dataclass(frozen=True)
class BuildDiagnostic:
    severity: str
    code: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IgnitionProviderBuildResult:
    provider: dict[str, Any]
    diagnostics: tuple[BuildDiagnostic, ...] = ()


def build_ignition_provider(
    project: PlcProject,
    *,
    device_map: dict[str, str] | None = None,
    selected_tags: set[tuple[str, str, str]] | None = None,
) -> IgnitionProviderBuildResult:
    builder = IgnitionTagProviderBuilder(project, device_map=device_map or {}, selected_tags=selected_tags)
    return builder.build()


class IgnitionTagProviderBuilder:
    def __init__(
        self,
        project: PlcProject,
        *,
        device_map: dict[str, str],
        selected_tags: set[tuple[str, str, str]] | None,
    ) -> None:
        self.project = project
        self.device_map = device_map
        self.selected_tags = selected_tags
        self.diagnostics: list[BuildDiagnostic] = []

    def build(self) -> IgnitionProviderBuildResult:
        provider_tags = [self.types_folder()]
        for controller in self.project.controllers:
            controller_folder = self.controller_folder(controller)
            if controller_folder["tags"]:
                provider_tags.append(controller_folder)
        return IgnitionProviderBuildResult(
            provider={"name": "", "tagType": "Provider", "tags": provider_tags},
            diagnostics=tuple(self.diagnostics),
        )

    def types_folder(self) -> dict[str, Any]:
        types: list[dict[str, Any]] = []
        seen: dict[str, PlcDataType] = {}
        for controller in self.project.controllers:
            for data_type in controller.data_types:
                normalized = data_type.name.upper()
                existing = seen.get(normalized)
                if existing is not None:
                    self.diagnostics.append(
                        BuildDiagnostic(
                            severity="warning",
                            code="duplicate_udt_name",
                            message="Multiple PLC data types share a name; first definition was used",
                            context={"data_type": data_type.name, "controller": controller.name},
                        )
                    )
                    continue
                seen[normalized] = data_type
                udt_type = self.udt_type_definition(controller, data_type)
                if udt_type:
                    types.append(udt_type)

        for builtin in BUILTIN_TYPES:
            if builtin.name.upper() not in seen:
                types.append(self.builtin_type_definition(builtin.name, builtin.members))
        return {"name": "_types_", "tagType": "Folder", "tags": types}

    def udt_type_definition(self, controller: PlcController, data_type: PlcDataType) -> dict[str, Any] | None:
        if data_type.name.upper() in IGNORED_ROCKWELL_TYPES:
            self.skip("ignored_udt_type", "Skipped unsupported Rockwell type", controller, data_type.name)
            return None
        tags = []
        for member in data_type.members:
            tag = self.member_tag(controller, member, device_name="{DeviceName}", prefix="{TagPrefix}.", is_udt_def=True)
            if tag:
                tags.append(tag)
        return {
            "name": data_type.name,
            "tagType": "UdtType",
            "parameters": {
                "DeviceName": {"dataType": "String"},
                "TagPrefix": {"dataType": "String"},
            },
            "tags": tags,
        }

    def builtin_type_definition(self, name: str, members: tuple[BuiltinMember, ...]) -> dict[str, Any]:
        return {
            "name": name,
            "tagType": "UdtType",
            "parameters": {
                "DeviceName": {"dataType": "String"},
                "TagPrefix": {"dataType": "String"},
            },
            "tags": [
                self.atomic_tag(member.name, member.data_type, "{DeviceName}", f"{{TagPrefix}}.{member.name}")
                for member in members
            ],
        }

    def controller_folder(self, controller: PlcController) -> dict[str, Any]:
        tags: list[dict[str, Any]] = []
        program_folders: dict[str, dict[str, Any]] = {}
        for tag in controller.all_tags():
            if not self.should_include(controller, tag):
                continue
            ignition_tag = self.plc_tag(controller, tag)
            if not ignition_tag:
                continue
            if tag.scope == "Global":
                tags.append(ignition_tag)
            else:
                program = program_folders.setdefault(
                    tag.scope,
                    {"name": tag.scope, "tagType": "Folder", "tags": []},
                )
                program["tags"].append(ignition_tag)
        tags.extend(program_folders.values())
        return {"name": controller.name, "tagType": "Folder", "tags": tags}

    def should_include(self, controller: PlcController, tag: PlcTag) -> bool:
        if self.selected_tags is None:
            return True
        return (controller.name, tag.scope, tag.name) in self.selected_tags

    def plc_tag(self, controller: PlcController, tag: PlcTag) -> dict[str, Any] | None:
        data_type = tag.data_type
        base_path = tag.alias_for or tag.name
        if tag.is_alias:
            data_type = self.resolve_alias_type(controller, tag) or "BOOL"
            if data_type == "BOOL" and not self.resolve_alias_type(controller, tag):
                self.diagnostics.append(
                    BuildDiagnostic(
                        severity="warning",
                        code="alias_type_fallback",
                        message="Alias target type could not be resolved; Boolean fallback was used",
                        context={"controller": controller.name, "scope": tag.scope, "tag": tag.name, "alias_for": tag.alias_for},
                    )
                )
        logix_path = self.logix_path(tag.scope, base_path)
        return self.tag_for_type(
            controller,
            name=tag.name,
            data_type=data_type,
            device_name=self.device_name(controller),
            logix_path=logix_path,
            array_dimensions=tag.array_dimensions,
            documentation=tag.description,
            is_udt_def=False,
        )

    def member_tag(
        self,
        controller: PlcController,
        member: PlcMember,
        *,
        device_name: str,
        prefix: str,
        is_udt_def: bool,
    ) -> dict[str, Any] | None:
        if member.hidden and member.name.startswith("ZZZZZZ"):
            return None
        return self.tag_for_type(
            controller,
            name=member.name,
            data_type=member.data_type,
            device_name=device_name,
            logix_path=f"{prefix}{member.name}",
            array_dimensions=member.array_dimensions,
            documentation=member.description,
            is_udt_def=is_udt_def,
        )

    def tag_for_type(
        self,
        controller: PlcController,
        *,
        name: str,
        data_type: str,
        device_name: str,
        logix_path: str,
        array_dimensions: tuple[int, ...],
        documentation: str,
        is_udt_def: bool,
    ) -> dict[str, Any] | None:
        if "ZZZZZZ" in name or name.upper() == "N":
            return None
        if data_type.upper() in IGNORED_ROCKWELL_TYPES:
            self.skip("ignored_tag_type", "Skipped unsupported Rockwell tag type", controller, data_type, tag=name)
            return None

        ignition_type = ignition_data_type(data_type, is_array=bool(array_dimensions))
        if ignition_type:
            tag = self.atomic_tag(name, data_type, device_name, logix_path, is_array=bool(array_dimensions), documentation=documentation)
        else:
            tag = {
                "name": name,
                "tagType": "UdtInstance",
                "typeId": data_type,
                "parameters": {
                    "DeviceName": {"dataType": "String", "value": device_name},
                    "TagPrefix": {"dataType": "String", "value": logix_path},
                },
            }
            if is_udt_def:
                tag["parameters"]["DeviceName"]["value"] = {"bindType": "parameter", "binding": device_name}
                tag["parameters"]["TagPrefix"]["value"] = {"bindType": "parameter", "binding": f"{logix_path}."}
            if documentation:
                tag["documentation"] = documentation
        return tag

    def atomic_tag(
        self,
        name: str,
        data_type: str,
        device_name: str,
        logix_path: str,
        *,
        is_array: bool = False,
        documentation: str = "",
    ) -> dict[str, Any]:
        opc_item_path: str | dict[str, str]
        opc_path = f"ns=1;s=[{device_name}]{logix_path}"
        if "{" in device_name or "{" in logix_path:
            opc_item_path = {"bindType": "parameter", "binding": opc_path}
        else:
            opc_item_path = opc_path
        tag = {
            "name": name,
            "tagType": "AtomicTag",
            "dataType": ignition_data_type(data_type, is_array=is_array),
            "valueSource": "opc",
            "opcServer": "Ignition OPC UA Server",
            "opcItemPath": opc_item_path,
        }
        if documentation:
            tag["documentation"] = documentation
        return tag

    def resolve_alias_type(self, controller: PlcController, tag: PlcTag) -> str:
        target = tag.alias_for.strip()
        if not target:
            return ""
        base, member_path = split_alias_target(target)
        base_tag = controller.tag_named(tag.scope, base) or controller.global_tag_named(base)
        if base_tag is None:
            return "BOOL" if bit_alias_target(target) else ""
        if bit_alias_target(target):
            return "BOOL"
        if member_path:
            return resolve_member_path(controller, base_tag.data_type, member_path)
        return base_tag.data_type

    def device_name(self, controller: PlcController) -> str:
        return self.device_map.get(controller.name, controller.name)

    def logix_path(self, scope: str, base_path: str) -> str:
        return base_path if scope == "Global" else f"Program:{scope}.{base_path}"

    def skip(self, code: str, message: str, controller: PlcController, data_type: str, **context: Any) -> None:
        self.diagnostics.append(
            BuildDiagnostic(
                severity="info",
                code=code,
                message=message,
                context={"controller": controller.name, "data_type": data_type, **context},
            )
        )


def split_alias_target(target: str) -> tuple[str, str]:
    if not target:
        return "", ""
    first = member_tokens(target)
    if not first:
        return target, ""
    base = first[0]
    remainder = target[len(base) :].lstrip(".")
    return base, remainder


def bit_alias_target(target: str) -> bool:
    return bool(target and (target.rsplit(".", 1)[-1].isdigit() or re_colon_bit(target)))


def re_colon_bit(target: str) -> bool:
    parts = target.rsplit(".", 1)
    return len(parts) == 2 and parts[1].isdigit()
