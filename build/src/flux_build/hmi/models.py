from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class HmiMapTagReference:
    original: str
    shortcut: str = ""
    scope: str = "Global"
    base_tag: str = ""
    member_path: str = ""
    raw_tag_path: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "original": self.original,
            "shortcut": self.shortcut,
            "scope": self.scope,
            "base_tag": self.base_tag,
            "member_path": self.member_path,
            "raw_tag_path": self.raw_tag_path,
        }


@dataclass(frozen=True)
class HmiMapComponent:
    component_key: str
    parent_key: str = ""
    name: str = ""
    vendor_type: str = ""
    category: str = "primitive.unknown"
    symbol: str = "?"
    bounds: dict[str, float] = field(default_factory=dict)
    tag_references: tuple[HmiMapTagReference, ...] = ()
    global_object_reference: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "component_key": self.component_key,
            "parent_key": self.parent_key,
            "name": self.name,
            "vendor_type": self.vendor_type,
            "category": self.category,
            "symbol": self.symbol,
            "bounds": self.bounds,
            "tag_references": [reference.as_dict() for reference in self.tag_references],
            "global_object_reference": self.global_object_reference,
            "raw": self.raw,
        }


@dataclass(frozen=True)
class HmiMapScreen:
    screen_key: str
    name: str
    source_path: str = ""
    screen_type: str = "display"
    width: float | None = None
    height: float | None = None
    components: tuple[HmiMapComponent, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "screen_key": self.screen_key,
            "name": self.name,
            "source_path": self.source_path,
            "screen_type": self.screen_type,
            "width": self.width,
            "height": self.height,
            "components": [component.as_dict() for component in self.components],
        }


@dataclass(frozen=True)
class HmiMapProject:
    screens: tuple[HmiMapScreen, ...] = ()
    source_path: str = ""
    source_sha256: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "screen_count": len(self.screens),
            "component_count": sum(len(screen.components) for screen in self.screens),
            "screens": [screen.as_dict() for screen in self.screens],
        }


@dataclass(frozen=True)
class HmiMapDiagnostic:
    severity: str
    code: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HmiMapBuildResult:
    project: HmiMapProject
    svg_by_screen: dict[str, str] = field(default_factory=dict)
    diagnostics: tuple[HmiMapDiagnostic, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "project": self.project.as_dict(),
            "diagnostics": [diagnostic.__dict__ for diagnostic in self.diagnostics],
        }
