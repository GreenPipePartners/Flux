from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, replace
from typing import Any, Iterable

from flux_sim.reconstruction import SimProviderModel


@dataclass(frozen=True)
class SimulatedOpcTag:
    opc_server: str
    opc_item_path: str
    source_tag_path: str
    data_type: str = ""
    value: Any = None
    quality: str = "Good"
    sample_index: int = 0

    @property
    def key(self) -> tuple[str, str]:
        return self.opc_server, self.opc_item_path


@dataclass(frozen=True)
class SimulatedReadResult:
    opc_server: str
    opc_item_path: str
    value: Any
    quality: str
    source_tag_path: str = ""


class SimulatedOpcServer:
    def __init__(self, tags: Iterable[SimulatedOpcTag] = ()):
        self._tags: dict[tuple[str, str], SimulatedOpcTag] = {tag.key: tag for tag in tags}

    @classmethod
    def from_provider_model(
        cls,
        model: SimProviderModel,
        *,
        include_unresolved: bool = False,
        default_opc_server: str = "",
    ) -> "SimulatedOpcServer":
        tags: list[SimulatedOpcTag] = []
        for request in model.requests:
            if getattr(request, "value_source", "") != "opc":
                continue
            if not include_unresolved and not getattr(request, "resolved", True):
                continue
            item_path = str(getattr(request, "payload", "") or "")
            if not item_path:
                continue
            opc_server = str(getattr(request, "opc_server", "") or default_opc_server or model.provider_name)
            data_type = str(getattr(request, "data_type", "") or "")
            source_tag_path = str(getattr(request, "tag_path", "") or "")
            tags.append(
                SimulatedOpcTag(
                    opc_server=opc_server,
                    opc_item_path=item_path,
                    source_tag_path=source_tag_path,
                    data_type=data_type,
                    value=default_value_for_data_type(data_type, item_path),
                )
            )
        return cls(dedupe_tags(tags))

    @property
    def tag_count(self) -> int:
        return len(self._tags)

    def tags(self) -> tuple[SimulatedOpcTag, ...]:
        return tuple(self._tags.values())

    def read(self, opc_server: str, opc_item_path: str) -> SimulatedReadResult:
        tag = self._tags[(opc_server, opc_item_path)]
        return SimulatedReadResult(
            opc_server=tag.opc_server,
            opc_item_path=tag.opc_item_path,
            value=tag.value,
            quality=tag.quality,
            source_tag_path=tag.source_tag_path,
        )

    def read_many(self, requests: Iterable[tuple[str, str]]) -> tuple[SimulatedReadResult, ...]:
        return tuple(self.read(opc_server, opc_item_path) for opc_server, opc_item_path in requests)

    def write(self, opc_server: str, opc_item_path: str, value: Any, *, quality: str = "Good") -> None:
        tag = self._tags[(opc_server, opc_item_path)]
        self._tags[tag.key] = replace(tag, value=value, quality=quality)

    def tick(self, samples: int = 1) -> None:
        for _sample in range(samples):
            self._tags = {
                key: replace(
                    tag,
                    value=next_value_for_tag(tag),
                    sample_index=tag.sample_index + 1,
                    quality="Good",
                )
                for key, tag in self._tags.items()
            }

    def snapshot(self) -> dict[str, dict[str, Any]]:
        return {
            f"{server}|{item_path}": {
                "opcServer": tag.opc_server,
                "opcItemPath": tag.opc_item_path,
                "sourceTagPath": tag.source_tag_path,
                "dataType": tag.data_type,
                "value": tag.value,
                "quality": tag.quality,
                "sampleIndex": tag.sample_index,
            }
            for (server, item_path), tag in sorted(self._tags.items())
        }

    def to_field_agent_config(
        self,
        *,
        endpoint_name: str = "flux-sim",
        endpoint_url: str = "opc.tcp://localhost:4840/flux/sim",
        namespace_uri: str = "urn:flux:sim",
    ) -> dict[str, Any]:
        devices: dict[str, list[SimulatedOpcTag]] = {}
        for tag in self.tags():
            devices.setdefault(device_name_for_item_path(tag.opc_item_path), []).append(tag)
        return {
            "endpoints": [
                {
                    "name": endpoint_name,
                    "endpoint_url": endpoint_url,
                    "namespace_uri": namespace_uri,
                    "devices": [
                        {
                            "name": device_name,
                            "device_type": "simulated-opc",
                            "browse_path": server_group_for_device(device_tags),
                            "tags": [field_agent_tag_config(tag) for tag in sorted(device_tags, key=lambda item: item.opc_item_path)],
                        }
                        for device_name, device_tags in sorted(devices.items())
                    ],
                }
            ]
        }


def dedupe_tags(tags: Iterable[SimulatedOpcTag]) -> tuple[SimulatedOpcTag, ...]:
    deduped: dict[tuple[str, str], SimulatedOpcTag] = {}
    for tag in tags:
        deduped.setdefault(tag.key, tag)
    return tuple(deduped.values())


def default_value_for_data_type(data_type: str, seed: str = "") -> Any:
    normalized = data_type.lower()
    if normalized in {"boolean", "bool"}:
        return False
    if normalized.startswith("int"):
        return stable_int(seed) % 100
    if normalized.startswith("float") or normalized in {"double", "number"}:
        return float(stable_int(seed) % 1000) / 10.0
    return ""


def next_value_for_tag(tag: SimulatedOpcTag) -> Any:
    normalized = tag.data_type.lower()
    next_index = tag.sample_index + 1
    if normalized in {"boolean", "bool"}:
        return bool(next_index % 2)
    if normalized.startswith("int"):
        current = int(tag.value or 0)
        return (current + 1) % 32768
    if normalized.startswith("float") or normalized in {"double", "number"}:
        baseline = float(tag.value or 0.0)
        wave = math.sin(next_index / 10.0)
        return round(baseline + wave, 4)
    return tag.value


def stable_int(value: str) -> int:
    return int(hashlib.sha1(value.encode("utf-8")).hexdigest()[:8], 16)


def device_name_for_item_path(opc_item_path: str) -> str:
    marker = ";s="
    if marker in opc_item_path:
        identifier = opc_item_path.split(marker, 1)[1]
    else:
        identifier = opc_item_path
    return identifier.split(".", 1)[0].strip() or "default"


def field_agent_tag_config(tag: SimulatedOpcTag) -> dict[str, Any]:
    return {
        "name": field_tag_name(tag),
        "node_id": tag.opc_item_path,
        "browse_name": field_tag_name(tag),
        "opc_item_path": tag.opc_item_path,
        "source_tag_path": tag.source_tag_path,
        "data_type": field_agent_data_type(tag.data_type),
        "update_rate_ms": 1000,
        "simulation_type": "wave" if field_agent_data_type(tag.data_type) == "float" else "static",
        "initial_value": str(tag.value),
    }


def field_tag_name(tag: SimulatedOpcTag) -> str:
    base = tag.source_tag_path.rsplit("/", 1)[-1] if tag.source_tag_path else tag.opc_item_path.rsplit(".", 1)[-1]
    digest = hashlib.sha1(tag.opc_item_path.encode("utf-8")).hexdigest()[:8]
    return f"{sanitize_name(base)}_{digest}"


def sanitize_name(value: str) -> str:
    clean = "".join(character if character.isalnum() or character == "_" else "_" for character in value)
    return clean.strip("_") or "Tag"


def field_agent_data_type(data_type: str) -> str:
    normalized = data_type.lower()
    if normalized in {"boolean", "bool"}:
        return "bool"
    if normalized.startswith("int"):
        return "int"
    if normalized.startswith("float") or normalized in {"double", "number"}:
        return "float"
    return "string"


def server_group_for_device(tags: list[SimulatedOpcTag]) -> str:
    servers = sorted({tag.opc_server for tag in tags if tag.opc_server})
    return servers[0] if len(servers) == 1 else "mixed"
