from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import re
from typing import Any

from django.db.models import Q

from flux.base.models import Tag
from flux.sim.models import FieldEndpoint
from flux.sim.models import TagNode, TagProvider, TagSelection
from flux.base.services import path_effectively_selected
from flux.sim.field_bridge import field_data_type
from flux.sim.kernel_sync import cleanup_empty_runtime_devices, delete_materialized_configs_for_source_paths, upsert_device_config, upsert_tag_config
from flux.sim.models import DeviceConfig, TagConfig


DEFAULT_SELECTION_SENTINEL = "__flux_sim_defaults__"
DEFAULT_REHYDRATED_TAG_GROUP = "Default"
PARAMETER_PATTERN = re.compile(r"\{([^{}]+)\}")


@dataclass(frozen=True)
class RehydrationConfigureOperation:
    base_path: str
    tag_configs: list[dict[str, Any]]


@dataclass(frozen=True)
class RehydrationPlan:
    source_provider: str
    target_provider: str
    tag_base_path: str
    tag_configs: list[dict[str, Any]]
    selected_node_count: int
    udt_dependency_count: int

    @property
    def tag_count(self) -> int:
        return count_config_nodes(self.tag_configs)


@dataclass(frozen=True)
class RehydrationBackingResult:
    endpoint_count: int
    device_count: int
    tag_count: int
    skipped_count: int


@dataclass(frozen=True)
class RehydrationDeleteResult:
    tag_branch_count: int
    backing_tag_count: int


def build_rehydration_plan(
    source_provider: str,
    *,
    target_provider: str | None = None,
    selected_paths: list[str] | None = None,
    opc_server_map: dict[str, str] | None = None,
) -> RehydrationPlan:
    target_provider = target_provider or source_provider
    provider = TagProvider.objects.get(name=source_provider)
    selected_nodes = selected_rehydration_nodes(provider, selected_paths=selected_paths)
    udt_nodes = udt_dependency_nodes(provider, selected_nodes)
    nodes = sorted(
        {node.path: node for node in [*udt_nodes, *selected_nodes]}.values(),
        key=lambda node: (node.depth, node.sort_order, node.id),
    )
    tag_configs = build_config_forest(
        nodes,
        source_provider=source_provider,
        target_provider=target_provider,
        opc_server_map=opc_server_map or {},
    )
    return RehydrationPlan(
        source_provider=source_provider,
        target_provider=target_provider,
        tag_base_path=tag_base_path_for_provider(target_provider),
        tag_configs=tag_configs,
        selected_node_count=len(selected_nodes),
        udt_dependency_count=len(udt_nodes),
    )


def apply_rehydration_plan(fx: Any, plan: RehydrationPlan, *, collision_policy: str = "o") -> Any:
    results = []
    for operation in rehydration_configure_operations(plan):
        results.append(
            fx.tag.configure(operation.tag_configs, base_path=operation.base_path, collision_policy=collision_policy)
        )
    return results


def delete_rehydrated_paths(fx: Any, *, provider: str, paths: list[str]) -> RehydrationDeleteResult:
    cleaned_paths = sorted({path.strip("/") for path in paths if path.strip("/")})
    if not cleaned_paths:
        return RehydrationDeleteResult(tag_branch_count=0, backing_tag_count=0)
    fx.tag.delete_tags([f"[{provider}]{path}" for path in cleaned_paths])
    return RehydrationDeleteResult(
        tag_branch_count=len(cleaned_paths),
        backing_tag_count=delete_rehydration_backing_tags(cleaned_paths),
    )


def materialize_rehydration_backing(
    source_provider: str,
    *,
    selected_paths: list[str] | None = None,
) -> RehydrationBackingResult:
    provider = TagProvider.objects.get(name=source_provider)
    selected_nodes = selected_rehydration_nodes(provider, selected_paths=selected_paths)
    backing_specs = backing_tag_specs(provider, selected_nodes)

    endpoints_by_name: dict[str, FieldEndpoint] = {}
    devices_by_key: dict[tuple[int, str], DeviceConfig] = {}
    active_names_by_device: dict[int, set[str]] = {}
    desired_tags: list[dict[str, Any]] = []
    skipped_count = 0
    for spec in backing_specs:
        endpoint = endpoints_by_name.get(spec["endpoint_name"])
        if endpoint is None:
            endpoint = FieldEndpoint.objects.update_or_create(
                name=spec["endpoint_name"],
                defaults={
                    "enabled": True,
                    "security_policy": "None",
                    "namespace_uri": "urn:flux:field:sim",
                },
            )[0]
            endpoints_by_name[endpoint.name] = endpoint
        key = (endpoint.id, spec["device_name"])
        device = devices_by_key.get(key)
        if device is None:
            device = upsert_device_config(
                namespace=f"endpoint:{endpoint.name}",
                name=spec["device_name"],
                device_type="Rehydrated UDT Backing",
                endpoint=endpoint,
                browse_path=source_provider,
                enabled=True,
                description="Materialized for Flux.sim rehydrated UDT backing",
            )
            devices_by_key[key] = device
        if spec["node_id"] != f"ns=2;s={device.base_device.name}.{spec['tag_name']}":
            skipped_count += 1
            continue
        desired_tags.append(
            {
                "device": device,
                "name": spec["tag_name"],
                "data_type": field_data_type(spec["data_type"]),
                "simulation_type": default_simulation_type(spec["data_type"]),
                "initial_value": bounded_text(spec.get("initial_value") or ""),
                "enabled": True,
                "description": spec["source_path"],
                "config": {"rehydrated_source_path": spec["source_path"], "expected_node_id": spec["node_id"]},
            }
        )
        active_names_by_device.setdefault(device.id, set()).add(spec["tag_name"])
    upsert_field_tags(desired_tags)
    disable_stale_rehydration_tags(active_names_by_device)
    return RehydrationBackingResult(
        endpoint_count=len(endpoints_by_name),
        device_count=len(devices_by_key),
        tag_count=len(backing_specs) - skipped_count,
        skipped_count=skipped_count,
    )


def upsert_field_tags(desired_tags: list[dict[str, Any]]) -> None:
    if not desired_tags:
        return
    for desired in desired_tags:
        upsert_tag_config(
            sim_device=desired["device"],
            provider=desired["device"].browse_path,
            tagpath=desired["description"],
            tag_name=desired["name"],
            data_type=desired["data_type"],
            simulation_type=desired["simulation_type"],
            initial_value=desired["initial_value"],
            enabled=desired["enabled"],
            materialized=True,
            description=desired["description"],
            config=desired["config"],
        )


def disable_stale_rehydration_tags(active_names_by_device: dict[int, set[str]]) -> None:
    for device_id, active_names in active_names_by_device.items():
        TagConfig.objects.filter(sim_device_id=device_id, materialized=True, config__has_key="rehydrated_source_path").exclude(
            tag_name__in=active_names
        ).update(materialized=False)


def delete_rehydration_backing_tags(paths: list[str]) -> int:
    query = Q()
    for path in paths:
        query |= Q(base_tag__description=path) | Q(base_tag__description__startswith=f"{path}/")
    if not query:
        return 0
    tag_configs = TagConfig.objects.filter(query, materialized=True, config__has_key="rehydrated_source_path")
    source_paths = list(tag_configs.values_list("base_tag__tagpath", flat=True))
    if not source_paths:
        return 0
    providers = set(tag_configs.values_list("base_tag__provider", flat=True))
    for provider in providers:
        delete_materialized_configs_for_source_paths(provider, source_paths)
    deleted_count = len(source_paths)
    cleanup_empty_rehydration_devices()
    return deleted_count


def cleanup_empty_rehydration_devices() -> None:
    cleanup_empty_runtime_devices()


def backing_tag_specs(provider: TagProvider, selected_nodes: list[TagNode]) -> list[dict[str, Any]]:
    specs: dict[tuple[str, str, str], dict[str, Any]] = {}
    selected_udt_instances = [node for node in selected_nodes if node.tag_type == "UdtInstance" and node.type_id]
    for instance in selected_udt_instances:
        type_path = normalize_type_id(instance.type_id)
        type_node = TagNode.objects.filter(provider=provider, path=type_path).first()
        if type_node is None:
            continue
        parameters = merged_parameters(type_node.parameters, instance.parameters)
        opc_server = str(parameter_scalar(parameters.get("OPC_Server")) or "")
        opc_device = str(parameter_scalar(parameters.get("OPC_Device")) or instance.name)
        opc_prefix = str(parameter_scalar(parameters.get("OPC_Prefix")) or "ns=2;s=")
        if not opc_server or not opc_device:
            continue
        for member in TagNode.objects.filter(provider=provider, path__startswith=type_path + "/", tag_type="AtomicTag"):
            raw = member.raw_config or {}
            if raw.get("valueSource") != "opc":
                continue
            node_id = resolved_opc_item_path(raw.get("opcItemPath"), parameters, member.name, opc_prefix, opc_device)
            if not node_id:
                continue
            tag_name = field_tag_name_for_node_id(node_id, opc_device)
            if not tag_name:
                continue
            source_path = f"{instance.path}/{member.path.removeprefix(type_path).strip('/')}"
            key = (opc_server, opc_device, tag_name)
            specs[key] = {
                "endpoint_name": endpoint_name_for_opc_server(opc_server),
                "device_name": opc_device,
                "tag_name": tag_name,
                "node_id": node_id,
                "data_type": member.data_type or str(raw.get("dataType") or ""),
                "initial_value": member.value,
                "source_path": source_path,
            }
    return list(specs.values())


def merged_parameters(type_parameters: Any, instance_parameters: Any) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if isinstance(type_parameters, dict):
        merged.update(type_parameters)
    if isinstance(instance_parameters, dict):
        merged.update(instance_parameters)
    return merged


def parameter_scalar(value: Any) -> Any:
    if isinstance(value, dict):
        return value.get("value")
    return value


def resolved_opc_item_path(raw_value: Any, parameters: dict[str, Any], tag_name: str, opc_prefix: str, opc_device: str) -> str:
    template = raw_value.get("binding") if isinstance(raw_value, dict) else raw_value
    if not isinstance(template, str):
        return f"{opc_prefix}{opc_device}.{tag_name}"
    values = {key: str(parameter_scalar(value) or "") for key, value in parameters.items()}
    values.setdefault("OPC_Prefix", opc_prefix)
    values.setdefault("OPC_Device", opc_device)
    values["TagName"] = tag_name
    resolved = PARAMETER_PATTERN.sub(lambda match: resolve_parameter_token(match.group(1), values), template)
    if "{" in resolved or "}" in resolved:
        return ""
    return resolved


def resolve_parameter_token(token: str, values: dict[str, str]) -> str:
    token = token.strip()
    if token in values:
        return values[token]
    match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)([+-]\d+)", token)
    if not match:
        return ""
    base_value = values.get(match.group(1), "")
    try:
        return str(int(float(base_value)) + int(match.group(2)))
    except ValueError:
        return ""


def field_tag_name_for_node_id(node_id: str, device_name: str) -> str:
    prefix = f"ns=2;s={device_name}."
    if not node_id.startswith(prefix):
        return ""
    return node_id.removeprefix(prefix)


def endpoint_name_for_opc_server(opc_server: str) -> str:
    return "Flux sim %s Server" % opc_server


def default_simulation_type(data_type: str) -> str:
    normalized = field_data_type(data_type)
    if normalized == Tag.DataType.BOOL:
        return TagConfig.SimulationType.TOGGLE
    if normalized in {Tag.DataType.INT, Tag.DataType.FLOAT}:
        return TagConfig.SimulationType.WAVE
    return TagConfig.SimulationType.STATIC


def bounded_text(value: Any) -> str:
    text = str(value or "")
    return text[:255]


def rehydration_configure_operations(plan: RehydrationPlan) -> list[RehydrationConfigureOperation]:
    types_root = next((config for config in plan.tag_configs if config.get("name") == "_types_"), None)
    normal_roots = [config for config in plan.tag_configs if config.get("name") != "_types_"]
    operations: list[RehydrationConfigureOperation] = []
    if types_root is not None:
        operations.append(
            RehydrationConfigureOperation(
                base_path=plan.tag_base_path,
                tag_configs=[{"name": "_types_", "tagType": "Folder"}],
            )
        )
        type_children = list(types_root.get("tags") or [])
        if type_children:
            operations.append(
                RehydrationConfigureOperation(
                    base_path=f"{plan.tag_base_path}_types_",
                    tag_configs=type_children,
                )
            )
    if normal_roots:
        operations.append(RehydrationConfigureOperation(base_path=plan.tag_base_path, tag_configs=normal_roots))
    return operations


def selected_rehydration_nodes(provider: TagProvider, *, selected_paths: list[str] | None = None) -> list[TagNode]:
    if selected_paths is not None:
        prefixes = sorted({path.strip("/") for path in selected_paths if path.strip("/")})
        if not prefixes:
            return []
        return list(
            TagNode.objects.filter(provider=provider)
            .exclude(path="")
            .exclude(path="_types_")
            .exclude(path__startswith="_types_/")
            .filter(path__in=selected_path_closure(provider, prefixes))
            .order_by("depth", "sort_order", "id")
        )

    selections = list(
        TagSelection.objects.filter(provider=provider, purpose=TagSelection.Purpose.SIM).exclude(
            path=DEFAULT_SELECTION_SENTINEL
        )
    )
    enabled_prefixes = [selection.path for selection in selections if selection.enabled]
    if not enabled_prefixes:
        return []

    nodes: list[TagNode] = []
    candidate_paths = selected_path_closure(provider, enabled_prefixes)
    for node in (
        TagNode.objects.filter(provider=provider)
        .filter(path__in=candidate_paths)
        .exclude(path="")
        .exclude(path="_types_")
        .exclude(path__startswith="_types_/")
        .order_by("depth", "sort_order", "id")
    ):
        if path_effectively_selected(node.path, selections) or enabled_selection_descends_from(node.path, selections):
            nodes.append(node)
    return nodes


def selected_path_closure(provider: TagProvider, prefixes: list[str]) -> set[str]:
    paths: set[str] = set()
    ancestry_paths = {ancestor for prefix in prefixes for ancestor in path_ancestors_including_self(prefix)}
    query = Q(path__in=ancestry_paths)
    for prefix in prefixes:
        query |= Q(path=prefix) | Q(path__startswith=prefix + "/")
    for path in (
        TagNode.objects.filter(provider=provider)
        .exclude(path="")
        .exclude(path="_types_")
        .exclude(path__startswith="_types_/")
        .filter(query)
        .values_list("path", flat=True)
    ):
        paths.add(path)
    return paths


def enabled_selection_descends_from(path: str, selections: list[TagSelection]) -> bool:
    return any(selection.enabled and selection.path.startswith(path + "/") for selection in selections)


def udt_dependency_nodes(provider: TagProvider, selected_nodes: list[TagNode]) -> list[TagNode]:
    pending = [normalize_type_id(node.type_id) for node in selected_nodes if node.tag_type == "UdtInstance" and node.type_id]
    seen_types: set[str] = set()
    dependency_paths: set[str] = set()
    while pending:
        type_path = pending.pop()
        if not type_path or type_path in seen_types:
            continue
        seen_types.add(type_path)
        for path in path_ancestors_including_self(type_path):
            dependency_paths.add(path)
        descendants = list(
            TagNode.objects.filter(provider=provider).filter(path=type_path).union(
                TagNode.objects.filter(provider=provider, path__startswith=type_path + "/")
            )
        )
        for node in descendants:
            dependency_paths.add(node.path)
            if node.tag_type == "UdtInstance" and node.type_id:
                pending.append(normalize_type_id(node.type_id))
    if not dependency_paths:
        return []
    return list(TagNode.objects.filter(provider=provider, path__in=dependency_paths).order_by("depth", "sort_order", "id"))


def build_config_forest(
    nodes: list[TagNode], *, source_provider: str, target_provider: str, opc_server_map: dict[str, str]
) -> list[dict[str, Any]]:
    configs_by_path: dict[str, dict[str, Any]] = {}
    roots: list[dict[str, Any]] = []
    node_paths = {node.path for node in nodes}
    for node in nodes:
        config = rehydrated_node_config(
            node,
            source_provider=source_provider,
            target_provider=target_provider,
            opc_server_map=opc_server_map,
        )
        configs_by_path[node.path] = config
        parent_path = node.path.rsplit("/", 1)[0] if "/" in node.path else ""
        if parent_path and parent_path in node_paths:
            configs_by_path[parent_path].setdefault("tags", []).append(config)
        else:
            roots.append(config)
    return roots


def rehydrated_node_config(
    node: TagNode, *, source_provider: str, target_provider: str, opc_server_map: dict[str, str]
) -> dict[str, Any]:
    config = deepcopy(node.raw_config or {})
    config.setdefault("name", node.name)
    config.setdefault("tagType", node.tag_type)
    if node.tag_type == "UdtInstance" and config.get("typeId"):
        config["typeId"] = target_type_id(str(config["typeId"]), source_provider, target_provider)
    rewrite_opc_server_fields(config, opc_server_map)
    rewrite_tag_group(config)
    return config


def rewrite_tag_group(config: dict[str, Any]) -> None:
    if "tagGroup" in config:
        config["tagGroup"] = DEFAULT_REHYDRATED_TAG_GROUP


def rewrite_opc_server_fields(config: dict[str, Any], opc_server_map: dict[str, str]) -> None:
    if "opcServer" in config:
        config["opcServer"] = rewritten_opc_server_value(config["opcServer"], opc_server_map)
    parameters = config.get("parameters")
    if isinstance(parameters, dict) and "OPC_Server" in parameters:
        parameters["OPC_Server"] = rewritten_parameter_value(parameters["OPC_Server"], opc_server_map)


def rewritten_parameter_value(value: Any, opc_server_map: dict[str, str]) -> Any:
    if isinstance(value, dict):
        rewritten = dict(value)
        if "value" in rewritten:
            rewritten["value"] = rewritten_opc_server_value(rewritten["value"], opc_server_map)
        return rewritten
    return rewritten_opc_server_value(value, opc_server_map)


def rewritten_opc_server_value(value: Any, opc_server_map: dict[str, str]) -> Any:
    if not isinstance(value, str):
        return value
    return opc_server_map.get(value, default_field_connection_name(value)) if value else value


def default_field_connection_name(opc_server: str) -> str:
    if opc_server.startswith("Flux Field "):
        return opc_server
    return "Flux Field Flux_sim_%s_Server" % safe_name(opc_server)


def target_type_id(type_id: str, source_provider: str, target_provider: str) -> str:
    if source_provider == target_provider and type_id.strip().startswith("["):
        return type_id
    type_path = normalize_type_id(type_id)
    return f"[{target_provider}]{type_path}"


def normalize_type_id(type_id: str) -> str:
    path = type_id.strip()
    if "]" in path:
        path = path.split("]", 1)[1]
    path = path.strip("/")
    if path and not path.startswith("_types_/") and path != "_types_":
        path = f"_types_/{path}"
    return path


def path_ancestors_including_self(path: str) -> list[str]:
    parts = [part for part in path.split("/") if part]
    return ["/".join(parts[:index]) for index in range(1, len(parts) + 1)]


def tag_base_path_for_provider(tag_provider: str) -> str:
    if tag_provider.startswith("[") and tag_provider.endswith("]"):
        return tag_provider
    return "[%s]" % tag_provider


def count_config_nodes(configs: list[dict[str, Any]]) -> int:
    return sum(1 + count_config_nodes(list(config.get("tags") or [])) for config in configs)


def safe_name(value: str) -> str:
    return "".join(character if character.isalnum() or character in "-_" else "_" for character in value)
