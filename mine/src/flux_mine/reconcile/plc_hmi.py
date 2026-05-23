from __future__ import annotations

import re
from dataclasses import dataclass

from flux_mine.hmi.tag_refs import HmiTagReference
from flux_mine.plc.models import PlcController, PlcDataType, PlcProject, PlcTag


@dataclass(frozen=True)
class ReconcileResult:
    status: str
    confidence: float
    message: str
    controller_name: str = ""
    scope: str = ""
    base_tag: str = ""
    member_path: str = ""
    data_type: str = ""
    alias_for: str = ""

    @property
    def matched(self) -> bool:
        return self.status in {"exact", "member", "alias"}


def reconcile_hmi_tag_reference(
    reference: HmiTagReference,
    project: PlcProject,
    shortcut_map: dict[str, str] | None = None,
) -> ReconcileResult:
    shortcut_map = shortcut_map or {}
    controller_name = shortcut_map.get(reference.shortcut, reference.shortcut)
    controller = project.controller_named(controller_name)
    if controller is None:
        return ReconcileResult(
            status="missing_controller",
            confidence=0.0,
            message=f"No PLC controller matched shortcut {reference.shortcut!r}",
            controller_name=controller_name,
            scope=reference.scope,
            base_tag=reference.base_tag,
            member_path=reference.member_path,
        )

    tag = controller.tag_named(reference.scope, reference.base_tag)
    if tag is None:
        return ReconcileResult(
            status="missing_tag",
            confidence=0.0,
            message="Controller matched but base tag was not found",
            controller_name=controller.name,
            scope=reference.scope,
            base_tag=reference.base_tag,
            member_path=reference.member_path,
        )

    if tag.is_alias:
        return ReconcileResult(
            status="alias",
            confidence=0.9 if not reference.member_path else 0.75,
            message="Matched an alias tag; target should be resolved before build output",
            controller_name=controller.name,
            scope=tag.scope,
            base_tag=tag.name,
            member_path=reference.member_path,
            data_type=tag.data_type,
            alias_for=tag.alias_for,
        )

    if not reference.member_path:
        return ReconcileResult(
            status="exact",
            confidence=1.0,
            message="Matched controller, scope, and base tag",
            controller_name=controller.name,
            scope=tag.scope,
            base_tag=tag.name,
            data_type=tag.data_type,
        )

    resolved_type = resolve_member_path(controller, tag.data_type, reference.member_path)
    if resolved_type:
        return ReconcileResult(
            status="member",
            confidence=0.95,
            message="Matched base tag and traversed UDT member path",
            controller_name=controller.name,
            scope=tag.scope,
            base_tag=tag.name,
            member_path=reference.member_path,
            data_type=resolved_type,
        )

    return ReconcileResult(
        status="missing_member",
        confidence=0.35,
        message="Base tag matched but member path could not be traversed",
        controller_name=controller.name,
        scope=tag.scope,
        base_tag=tag.name,
        member_path=reference.member_path,
        data_type=tag.data_type,
    )


def resolve_member_path(controller: PlcController, data_type_name: str, member_path: str) -> str:
    current_type_name = data_type_name
    current_member_type = data_type_name
    for token in member_tokens(member_path):
        data_type = controller.data_type_named(current_type_name)
        if data_type is None:
            return ""
        member = data_type.member_named(token)
        if member is None:
            return ""
        current_member_type = member.data_type
        current_type_name = member.data_type
    return current_member_type


def member_tokens(member_path: str) -> list[str]:
    cleaned = member_path.strip().lstrip(".")
    if not cleaned:
        return []
    tokens: list[str] = []
    for token in cleaned.split("."):
        token = re.sub(r"\[[^\]]+\]", "", token).strip()
        if token:
            tokens.append(token)
    return tokens
