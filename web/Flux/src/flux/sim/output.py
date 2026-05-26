from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from django.db import transaction

from flux.base.models import Tag
from flux.sim.models import SimDriver, SimServer, TagNode, TagProvider, TagSelection
from flux.sim.kernel_sync import upsert_device_config, upsert_tag_config
from flux.sim.models import TagConfig

from .field_bridge import materialize_sim_device, materialize_sim_server_endpoint
from .provider_tree import selected_source_paths


SIM_OUTPUT_DEVICE_DESCRIPTION_PREFIX = "Materialized from sim.device catalog"
SIM_OUTPUT_DEFAULT_SELECTION_PATH = "__flux_sim_defaults__"


@dataclass(frozen=True)
class SimOutputConfigField:
    name: str
    label: str
    input_type: str = "number"
    step: str = "any"


@dataclass(frozen=True)
class SimOutputModeStrategy:
    value: str
    label: str
    symbol: str
    simulation_type: str
    compatible_data_types: tuple[str, ...] = ()
    config_fields: tuple[SimOutputConfigField, ...] = ()
    include_range_defaults: bool = False
    profile_strategy: str = ""


NUMERIC_FIELD_TYPES = (Tag.DataType.FLOAT, Tag.DataType.INT)
ALL_FIELD_TYPES = (*NUMERIC_FIELD_TYPES, Tag.DataType.BOOL, Tag.DataType.STRING)
RANGE_FIELDS = (
    SimOutputConfigField("min_value", "Min"),
    SimOutputConfigField("max_value", "Max"),
)

SIM_OUTPUT_MODE_STRATEGIES = (
    SimOutputModeStrategy(
        "estimate_live",
        "Estimate from Live",
        "~>",
        TagConfig.SimulationType.STATIC,
        ALL_FIELD_TYPES,
    ),
    SimOutputModeStrategy(
        "estimate_history",
        "Estimate Polynomial with History",
        "x^2",
        TagConfig.SimulationType.WAVE,
        NUMERIC_FIELD_TYPES,
        include_range_defaults=True,
        profile_strategy="polynomial2",
    ),
    SimOutputModeStrategy(
        "random",
        "Random",
        "?*",
        TagConfig.SimulationType.RANDOM_WALK,
        NUMERIC_FIELD_TYPES,
        include_range_defaults=True,
    ),
    SimOutputModeStrategy(
        "random_range",
        "Random Range",
        "R[]",
        TagConfig.SimulationType.RANDOM_WALK,
        NUMERIC_FIELD_TYPES,
        RANGE_FIELDS,
        include_range_defaults=True,
    ),
    SimOutputModeStrategy(
        "sin_range",
        "Sin Range",
        "~^~",
        TagConfig.SimulationType.WAVE,
        NUMERIC_FIELD_TYPES,
        RANGE_FIELDS,
        include_range_defaults=True,
    ),
    SimOutputModeStrategy(
        "bool_random",
        "Bool Random",
        "?01",
        TagConfig.SimulationType.TOGGLE,
        (Tag.DataType.BOOL,),
    ),
    SimOutputModeStrategy(
        "static",
        "Static Initial Value",
        "==",
        TagConfig.SimulationType.STATIC,
        ALL_FIELD_TYPES,
        (SimOutputConfigField("initial_value", "Value", "text", ""),),
    ),
)
SIM_OUTPUT_MODE_BY_VALUE = {strategy.value: strategy for strategy in SIM_OUTPUT_MODE_STRATEGIES}
SIM_OUTPUT_MODE_CHOICES = tuple((strategy.value, strategy.label) for strategy in SIM_OUTPUT_MODE_STRATEGIES)
SIM_OUTPUT_MODE_LABELS = dict(SIM_OUTPUT_MODE_CHOICES)
SIM_OUTPUT_MODE_OPTIONS = tuple(
    {"value": strategy.value, "label": strategy.label, "symbol": strategy.symbol}
    for strategy in SIM_OUTPUT_MODE_STRATEGIES
)
DEFAULT_MODE_BY_TYPE_GROUP = {
    "numeric": "sin_range",
    "boolean": "bool_random",
    "text": "static",
}


@dataclass(frozen=True)
class SimOutputTagPlan:
    path: str
    name: str
    device_name: str
    data_type: str
    action: str
    mode: str


@dataclass(frozen=True)
class SimOutputPlan:
    provider_name: str
    selected_count: int
    create_count: int
    keep_count: int
    disable_count: int
    unmappable_count: int
    tags: list[SimOutputTagPlan]


@dataclass(frozen=True)
class SimOutputApplyResult:
    provider_name: str
    created_count: int
    updated_count: int
    disabled_count: int
    unmappable_count: int


def selected_output_plan(provider_name: str) -> SimOutputPlan:
    provider = TagProvider.objects.filter(name=provider_name).first()
    if provider is None:
        return SimOutputPlan(provider_name, 0, 0, 0, 0, 0, [])

    selected_paths = selected_source_paths(provider_name)
    nodes = selected_tag_nodes(provider, selected_paths)
    selection_configs = selection_mode_configs_by_path(provider)
    default_modes = provider_default_modes(provider)
    existing_paths = set(materialized_output_tags(provider_name).values_list("source_path", flat=True))
    tag_plans: list[SimOutputTagPlan] = []
    unmappable_count = 0
    for path in selected_paths:
        node = nodes.get(path)
        if node is None or not device_name_for_node(node):
            unmappable_count += 1
            continue
        tag_plans.append(
            SimOutputTagPlan(
                path=path,
                name=node.name,
                device_name=device_name_for_node(node),
                data_type=node.data_type,
                action="keep" if path in existing_paths else "create",
                mode=effective_mode_config_for_path(path, selection_configs, node, default_mode_by_type=default_modes)["simulation_mode"],
            )
        )
    selected_path_set = set(selected_paths)
    disable_count = materialized_output_tags(provider_name).exclude(source_path__in=selected_path_set).filter(enabled=True).count()
    return SimOutputPlan(
        provider_name=provider_name,
        selected_count=len(selected_paths),
        create_count=sum(1 for tag in tag_plans if tag.action == "create"),
        keep_count=sum(1 for tag in tag_plans if tag.action == "keep"),
        disable_count=disable_count,
        unmappable_count=unmappable_count,
        tags=tag_plans,
    )


def apply_selected_output(
    provider_name: str,
    *,
    mode_by_path: dict[str, str] | None = None,
    mode_config_by_path: dict[str, dict[str, Any]] | None = None,
    default_mode_by_type: dict[str, str] | None = None,
) -> SimOutputApplyResult:
    mode_by_path = mode_by_path or {}
    mode_config_by_path = mode_config_by_path or {}
    provider = TagProvider.objects.get(name=provider_name)
    default_mode_by_type = normalize_default_modes(default_mode_by_type or provider_default_modes(provider))
    selected_paths = selected_source_paths(provider_name)
    nodes = selected_tag_nodes(provider, selected_paths)
    selection_configs = selection_mode_configs_by_path(provider)
    sim_server = sim_server_for_nodes(provider, list(nodes.values()))
    endpoint = materialize_sim_server_endpoint(sim_server=sim_server)
    driver = default_opc_driver()
    created_count = 0
    updated_count = 0
    unmappable_count = 0
    selected_path_set = set(selected_paths)

    with transaction.atomic():
        tags_by_device: dict[int, list[TagConfig]] = {}
        for path in selected_paths:
            node = nodes.get(path)
            device_name = device_name_for_node(node) if node is not None else ""
            if node is None or not device_name:
                unmappable_count += 1
                continue
            sim_device = upsert_device_config(
                namespace=f"provider:{provider.name}",
                name=device_name,
                device_type=driver.label,
                source_provider=provider,
                sim_server=sim_server,
                driver=driver,
                browse_path=provider.name,
                enabled=True,
                description=f"Selected sim output for {provider.name}",
                config={"source": "selected_sim_output", "opc_server_name": node.opc_server},
            )
            override_config = mode_config_by_path.get(path)
            if override_config is None and mode_by_path.get(path):
                override_config = {"simulation_mode": mode_by_path[path]}
            mode_config = effective_mode_config_for_path(
                path,
                selection_configs,
                node,
                override_config=override_config,
                default_mode_by_type=default_mode_by_type,
            )
            created = not TagConfig.objects.filter(
                sim_device=sim_device,
                base_tag__provider=provider.name,
                base_tag__tagpath=path,
            ).exists()
            sim_tag = upsert_tag_config(
                sim_device=sim_device,
                provider=provider.name,
                tagpath=path,
                tag_name=node.name,
                data_type=node.data_type,
                source_tag_node=node,
                source_path=path,
                simulation_type=mode_config["simulation_type"],
                min_value=mode_config.get("min_value"),
                max_value=mode_config.get("max_value"),
                initial_value=mode_config.get("initial_value", ""),
                address_strategy="opc_item_path",
                address={"opc_item_path": node.opc_item_path},
                mode_config=mode_config,
                enabled=True,
                materialized=False,
                description=path,
                config={"value_source": node.value_source, "opc_server": node.opc_server, "opc_item_path": node.opc_item_path},
            )
            if created:
                created_count += 1
            else:
                updated_count += 1
            tags_by_device.setdefault(sim_device.id, []).append(sim_tag)

        disabled_tags = materialized_output_tags(provider_name).exclude(source_path__in=selected_path_set).filter(enabled=True)
        disabled_count = disabled_tags.update(enabled=False, materialized=False)
        for tags in tags_by_device.values():
            materialize_sim_device(tags[0].sim_device, enabled_tags=tags, endpoint=endpoint)

    return SimOutputApplyResult(provider_name, created_count, updated_count, disabled_count, unmappable_count)


def selected_tag_nodes(provider: TagProvider, selected_paths: list[str]) -> dict[str, TagNode]:
    nodes = TagNode.objects.filter(provider=provider, path__in=selected_paths, tag_type="AtomicTag").exclude(path="")
    return {node.path: hydrate_output_node_metadata(node) for node in nodes}


def hydrate_output_node_metadata(node: TagNode) -> TagNode:
    inherited = inherited_udt_definition_node(node)
    if inherited is not None:
        node.data_type = node.data_type or inherited.data_type
        node.value_source = node.value_source or inherited.value_source
        node.opc_server = node.opc_server or inherited.opc_server
        node.opc_item_path = node.opc_item_path or inherited.opc_item_path
        node.value = node.value if node.value is not None else inherited.value
    node.data_type = node.data_type or inferred_ignition_data_type(node.value)
    return node


def inherited_udt_definition_node(row: TagNode) -> TagNode | None:
    udt_ancestor = nearest_udt_instance_ancestor(row)
    if udt_ancestor is None or not udt_ancestor.type_id:
        return None
    type_path = tag_type_definition_path(udt_ancestor.type_id)
    if not type_path:
        return None
    relative_path = row.path.removeprefix(udt_ancestor.path).strip("/")
    if not relative_path:
        return None
    return TagNode.objects.filter(provider_id=row.provider_id, path=f"{type_path}/{relative_path}").first()


def nearest_udt_instance_ancestor(row: TagNode) -> TagNode | None:
    parent = row.parent
    while parent is not None:
        if parent.tag_type == "UdtInstance":
            return parent
        parent = parent.parent
    return None


def tag_type_definition_path(type_id: str) -> str:
    path = type_id.strip()
    if "]" in path:
        path = path.split("]", 1)[1]
    if path and not path.startswith("_types_/") and path != "_types_":
        path = f"_types_/{path}"
    return path.strip("/")


def inferred_ignition_data_type(value: Any) -> str:
    if isinstance(value, bool):
        return "Boolean"
    if isinstance(value, int):
        return "Int4"
    if isinstance(value, float):
        return "Float8"
    if isinstance(value, str) and value.strip().startswith('{"columns"'):
        return "DataSet"
    return ""


def selection_mode_configs_by_path(provider: TagProvider) -> dict[str, dict[str, Any]]:
    return {
        selection.path: dict(selection.config or {})
        for selection in provider.selections.filter(enabled=True)
    }


def selection_modes_by_path(provider: TagProvider) -> dict[str, str]:
    return {
        selection.path: str((selection.config or {}).get("simulation_mode") or "")
        for selection in provider.selections.filter(enabled=True)
    }


def effective_mode_for_path(path: str, mode_by_prefix: dict[str, str], node: TagNode) -> str:
    matches = [prefix for prefix in mode_by_prefix if path == prefix or path.startswith(prefix + "/")]
    if not matches:
        return default_sim_output_mode(node)
    return valid_mode(mode_by_prefix[max(matches, key=len)], node)


def effective_mode_config_for_path(
    path: str,
    config_by_prefix: dict[str, dict[str, Any]],
    node: TagNode,
    *,
    override_config: dict[str, Any] | None = None,
    default_mode_by_type: dict[str, str] | None = None,
) -> dict[str, Any]:
    if override_config:
        return simulation_mode_config(str(override_config.get("simulation_mode") or ""), node, override_config)
    config = config_by_prefix.get(path)
    if not config or not config.get("simulation_mode"):
        return simulation_mode_config(default_mode_for_node(node, default_mode_by_type), node)
    return simulation_mode_config(str(config.get("simulation_mode") or ""), node, config)


def materialized_output_tags(provider_name: str):
    return TagConfig.objects.filter(
        materialized=True,
        sim_device__source_provider__name=provider_name,
    )


def sim_server_for_nodes(provider: TagProvider, nodes: list[TagNode]) -> SimServer:
    if provider.sim_server_id:
        return provider.sim_server
    opc_server = next((node.opc_server for node in nodes if node.opc_server), "")
    if not opc_server:
        return SimServer.objects.get_or_create(name="Flux sim OPC-UA Server")[0]
    sim_server, _created = SimServer.objects.get_or_create(
        name=f"Flux sim {opc_server} Server",
        defaults={
            "endpoint_url": f"opc.tcp://0.0.0.0:4840/flux/sim/{safe_name(opc_server)}",
            "application_uri": f"urn:flux:sim:{safe_name(opc_server).lower()}",
            "product_uri": "urn:flux:sim",
            "namespace_uri": f"urn:flux:sim:{safe_name(opc_server).lower()}",
            "enabled": True,
            "security_policy": "None",
            "description": f"Inferred from selected imported opcServer={opc_server}",
        },
    )
    provider.sim_server = sim_server
    provider.save(update_fields=["sim_server"])
    return sim_server


def default_opc_driver() -> SimDriver:
    return SimDriver.objects.get_or_create(
        key="opc_ua",
        defaults={"label": "OPC UA", "strategy_key": "acm"},
    )[0]


def valid_mode(mode: str | None, node: TagNode) -> str:
    return valid_mode_for_data_type(mode, node.data_type, value=node.value, tag_type=node.tag_type)


def valid_mode_for_data_type(
    mode: str | None,
    data_type: str,
    *,
    value: Any = None,
    tag_type: str = "AtomicTag",
) -> str:
    strategy = SIM_OUTPUT_MODE_BY_VALUE.get(str(mode or ""))
    if strategy is not None and strategy_is_compatible_with_value(strategy, data_type, value, tag_type=tag_type):
        return strategy.value
    return default_sim_output_mode_for_data_type(data_type, value)


def strategy_is_compatible(strategy: SimOutputModeStrategy, data_type: str, *, tag_type: str = "AtomicTag") -> bool:
    return strategy_is_compatible_with_value(strategy, data_type, None, tag_type=tag_type)


def strategy_is_compatible_with_value(
    strategy: SimOutputModeStrategy,
    data_type: str,
    value: Any = None,
    *,
    tag_type: str = "AtomicTag",
) -> bool:
    if tag_type != "AtomicTag":
        return True
    if not strategy.compatible_data_types:
        return True
    return field_data_type(data_type, value) in strategy.compatible_data_types


def default_sim_output_mode(node: TagNode) -> str:
    return default_sim_output_mode_for_data_type(node.data_type, node.value)


def default_sim_output_mode_for_data_type(data_type: str, value: Any = None) -> str:
    field_type = field_data_type(data_type, value)
    if field_type == Tag.DataType.BOOL:
        return "bool_random"
    if field_type in {Tag.DataType.FLOAT, Tag.DataType.INT}:
        return "sin_range"
    return "static"


def default_mode_for_node(node: TagNode, default_mode_by_type: dict[str, str] | None = None) -> str:
    defaults = normalize_default_modes(default_mode_by_type)
    group = type_group_for_field_type(field_data_type(node.data_type, node.value))
    return defaults[group]


def normalize_default_modes(default_mode_by_type: dict[str, str] | None = None) -> dict[str, str]:
    provided = default_mode_by_type or {}
    return {
        group: valid_default_mode(group, provided.get(group) or fallback)
        for group, fallback in DEFAULT_MODE_BY_TYPE_GROUP.items()
    }


def valid_default_mode(type_group: str, mode: str) -> str:
    field_type = field_type_for_type_group(type_group)
    if field_type is None:
        return DEFAULT_MODE_BY_TYPE_GROUP["text"]
    strategy = SIM_OUTPUT_MODE_BY_VALUE.get(mode)
    if strategy is not None and field_type in strategy.compatible_data_types:
        return strategy.value
    return DEFAULT_MODE_BY_TYPE_GROUP[type_group]


def field_type_for_type_group(type_group: str) -> str | None:
    return {
        "numeric": Tag.DataType.FLOAT,
        "boolean": Tag.DataType.BOOL,
        "text": Tag.DataType.STRING,
    }.get(type_group)


def type_group_for_field_type(field_type: str) -> str:
    if field_type in {Tag.DataType.FLOAT, Tag.DataType.INT}:
        return "numeric"
    if field_type == Tag.DataType.BOOL:
        return "boolean"
    return "text"


def default_mode_groups(default_mode_by_type: dict[str, str] | None = None) -> tuple[dict[str, Any], ...]:
    defaults = normalize_default_modes(default_mode_by_type)
    groups = (
        ("numeric", "Numeric Tags", "Float and integer values"),
        ("boolean", "Boolean Tags", "True/false values"),
        ("text", "Text/Unknown Tags", "Strings, datasets, and unknown values"),
    )
    return tuple(
        {
            "type_group": group,
            "name": f"default_mode_{group}",
            "label": label,
            "description": description,
            "selected_mode": defaults[group],
            "options": mode_options_for_type_group(group, defaults[group]),
        }
        for group, label, description in groups
    )


def mode_options_for_type_group(type_group: str, selected_mode: str) -> tuple[dict[str, Any], ...]:
    field_type = field_type_for_type_group(type_group)
    return tuple(
        {
            "value": strategy.value,
            "label": strategy.label,
            "symbol": strategy.symbol,
            "selected": strategy.value == selected_mode,
        }
        for strategy in SIM_OUTPUT_MODE_STRATEGIES
        if field_type is not None and field_type in strategy.compatible_data_types
    )


def default_modes_from_post(post: Any) -> dict[str, str]:
    return normalize_default_modes(
        {
            group: str(post.get(f"default_mode_{group}") or "")
            for group in DEFAULT_MODE_BY_TYPE_GROUP
        }
    )


def provider_default_modes(provider: TagProvider | str | None) -> dict[str, str]:
    if provider is None:
        return normalize_default_modes()
    provider_name = provider.name if isinstance(provider, TagProvider) else provider
    selection = TagSelection.objects.filter(
        provider__name=provider_name,
        purpose=TagSelection.Purpose.SIM,
        path=SIM_OUTPUT_DEFAULT_SELECTION_PATH,
    ).first()
    return normalize_default_modes(dict(selection.config or {}) if selection is not None else None)


def save_provider_default_modes(provider_name: str, default_mode_by_type: dict[str, str]) -> dict[str, str]:
    defaults = normalize_default_modes(default_mode_by_type)
    provider = TagProvider.objects.get(name=provider_name)
    TagSelection.objects.update_or_create(
        provider=provider,
        purpose=TagSelection.Purpose.SIM,
        path=SIM_OUTPUT_DEFAULT_SELECTION_PATH,
        defaults={"enabled": False, "config": defaults},
    )
    return defaults


def simulation_mode_config(mode: str, node: TagNode, user_config: dict[str, Any] | None = None) -> dict[str, Any]:
    user_config = user_config or {}
    mode = valid_mode(mode or str(user_config.get("simulation_mode") or ""), node)
    strategy = SIM_OUTPUT_MODE_BY_VALUE[mode]
    config: dict[str, Any] = {
        "simulation_mode": mode,
        "simulation_mode_label": strategy.label,
        "simulation_type": strategy.simulation_type,
        "initial_value": config_initial_value(user_config, node),
    }
    if strategy.include_range_defaults:
        min_value, max_value = config_range(user_config, node)
        config["min_value"] = min_value
        config["max_value"] = max_value
    if strategy.profile_strategy:
        config["profile_strategy"] = strategy.profile_strategy
    return config


def simulation_type_for_mode(mode: str, node: TagNode) -> str:
    return SIM_OUTPUT_MODE_BY_VALUE[valid_mode(mode, node)].simulation_type


def config_range(user_config: dict[str, Any], node: TagNode) -> tuple[float, float]:
    default_min, default_max = default_range(node)
    min_value = config_float(user_config.get("min_value"), default_min if default_min is not None else 0.0)
    max_value = config_float(user_config.get("max_value"), default_max if default_max is not None else 100.0)
    if max_value <= min_value:
        max_value = min_value + 1.0
    return min_value, max_value


def config_float(value: Any, default: float) -> float:
    if value in (None, ""):
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def config_initial_value(user_config: dict[str, Any], node: TagNode) -> str:
    if "initial_value" in user_config:
        return str(user_config.get("initial_value") or "")
    return initial_value(node)


def selection_config_from_post(mode: str, raw_config: str | dict[str, Any] | None) -> dict[str, Any]:
    config: dict[str, Any] = {}
    if isinstance(raw_config, dict):
        config.update(raw_config)
    elif raw_config:
        try:
            parsed = json.loads(raw_config)
        except ValueError:
            parsed = {}
        if isinstance(parsed, dict):
            config.update(parsed)
    config["simulation_mode"] = mode or str(config.get("simulation_mode") or "")
    return normalize_selection_config(config)


def normalize_selection_config(config: dict[str, Any]) -> dict[str, Any]:
    mode = str(config.get("simulation_mode") or "estimate_live")
    if mode not in SIM_OUTPUT_MODE_BY_VALUE:
        mode = "estimate_live"
    strategy = SIM_OUTPUT_MODE_BY_VALUE[mode]
    normalized: dict[str, Any] = {"simulation_mode": mode}
    for field in strategy.config_fields:
        value = config.get(field.name)
        if value not in (None, ""):
            normalized[field.name] = value
    return normalized


def hydrate_sim_output_tree(nodes: list[Any]) -> None:
    for node in nodes:
        hydrate_sim_output_node(node)


def hydrate_sim_output_node(node: Any) -> None:
    config = dict(getattr(node, "simulation_config", {}) or {})
    raw_mode = str(config.get("simulation_mode") or getattr(node, "simulation_mode", ""))
    mode = ""
    if raw_mode:
        mode = valid_mode_for_data_type(
            raw_mode,
            getattr(node, "data_type", ""),
            value=getattr(node, "value", None),
            tag_type=getattr(node, "tag_type", ""),
        )
    node.simulation_mode = mode
    node.mode_options = mode_options_for_tree_node(node, config, mode)
    for child in getattr(node, "children_list", []):
        hydrate_sim_output_node(child)


def mode_options_for_tree_node(node: Any, config: dict[str, Any], active_mode: str) -> list[dict[str, Any]]:
    data_type = getattr(node, "data_type", "")
    value = getattr(node, "value", None)
    tag_type = getattr(node, "tag_type", "")
    if tag_type != "AtomicTag" or not getattr(node, "simulation_eligible", False):
        return []
    options = []
    for strategy in SIM_OUTPUT_MODE_STRATEGIES:
        if not strategy_is_compatible_with_value(strategy, data_type, value, tag_type=tag_type):
            continue
        options.append(
            {
                "value": strategy.value,
                "label": strategy.label,
                "symbol": strategy.symbol,
                "active": strategy.value == active_mode,
                "fields": mode_config_fields(strategy, node, config),
            }
        )
    return options


def mode_config_fields(strategy: SimOutputModeStrategy, node: Any, config: dict[str, Any]) -> list[dict[str, Any]]:
    values = simulation_mode_config(strategy.value, node, config)
    return [
        {
            "name": field.name,
            "label": field.label,
            "input_type": field.input_type,
            "step": field.step,
            "value": values.get(field.name, ""),
        }
        for field in strategy.config_fields
    ]


def default_range(node: TagNode) -> tuple[float | None, float | None]:
    field_type = field_data_type(node.data_type, node.value)
    if field_type == Tag.DataType.BOOL or field_type == Tag.DataType.STRING:
        return None, None
    value = numeric_initial_value(node)
    if value is None:
        return (0.0, 100.0) if field_type == Tag.DataType.FLOAT else (0, 100)
    spread = max(abs(value) * 0.1, 1.0)
    return value - spread, value + spread


def numeric_initial_value(node: TagNode) -> float | None:
    if isinstance(node.value, bool) or not isinstance(node.value, int | float):
        return None
    return float(node.value)


def initial_value(node: TagNode) -> str:
    if node.value is None:
        return ""
    return str(node.value).lower() if isinstance(node.value, bool) else str(node.value)


def device_name_for_node(node: TagNode | None) -> str:
    if node is None:
        return ""
    for key in ("OPC_Device", "OPCDevice", "Device", "device"):
        value = parameter_value((node.parameters or {}).get(key))
        if value:
            return value
    ancestor = node.parent
    while ancestor is not None:
        for key in ("OPC_Device", "OPCDevice", "Device", "device"):
            value = parameter_value((ancestor.parameters or {}).get(key))
            if value:
                return value
        if ancestor.tag_type == "UdtInstance" and ancestor.name:
            return ancestor.name
        ancestor = ancestor.parent
    match = re.search(r";s=([^\.\[]+)", node.opc_item_path)
    if match:
        return match.group(1)
    parts = [part for part in node.path.split("/") if part]
    return parts[-2] if len(parts) >= 2 else ""


def parameter_value(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("value") or "").strip()
    return str(value or "").strip()


def field_data_type(data_type: str, value: Any = None) -> str:
    normalized = data_type.lower()
    if "bool" in normalized:
        return Tag.DataType.BOOL
    if "float" in normalized or "double" in normalized:
        return Tag.DataType.FLOAT
    if "int" in normalized:
        return Tag.DataType.INT
    if isinstance(value, bool):
        return Tag.DataType.BOOL
    if isinstance(value, int):
        return Tag.DataType.INT
    if isinstance(value, float):
        return Tag.DataType.FLOAT
    return Tag.DataType.STRING


def safe_name(value: str) -> str:
    cleaned = "".join(character if character.isalnum() or character in "-_" else "_" for character in value.strip())
    return cleaned or "server"
