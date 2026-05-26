from __future__ import annotations

from flux_build.hmi.models import HmiMapComponent, HmiMapProject, HmiMapScreen, HmiMapTagReference
from flux_mine.hmi.factorytalk import FactoryTalkProject


def hmi_map_project_from_factorytalk(project: FactoryTalkProject) -> HmiMapProject:
    return HmiMapProject(
        screens=tuple(
            HmiMapScreen(
                screen_key=screen.source_path or screen.name,
                name=screen.name,
                source_path=screen.source_path,
                screen_type=screen.screen_type,
                width=screen.width,
                height=screen.height,
                components=tuple(
                    HmiMapComponent(
                        component_key=component.component_path or component.name,
                        parent_key=component.parent_path,
                        name=component.name,
                        vendor_type=component.component_type,
                        bounds=component.bounds,
                        tag_references=tuple(
                            HmiMapTagReference(
                                original=reference.original,
                                shortcut=reference.shortcut,
                                scope=reference.scope,
                                base_tag=reference.base_tag,
                                member_path=reference.member_path,
                                raw_tag_path=reference.raw_tag_path,
                            )
                            for reference in component.tag_references
                        ),
                        global_object_reference=component.global_object_reference,
                        raw=component.raw,
                    )
                    for component in screen.components
                ),
            )
            for screen in project.screens
        ),
        source_path=project.source_path,
        source_sha256=project.source_sha256,
    )
