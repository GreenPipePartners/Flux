from __future__ import annotations

import copy
import time
from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class IgnitionConfigureResult:
    tag_provider: str
    tag_folder: str
    opc_server: str
    endpoint_url: str
    tag_count: int
    batches: int

    @property
    def folder_path(self) -> str:
        if not self.tag_folder:
            return f"[{self.tag_provider}]"
        return f"[{self.tag_provider}]{self.tag_folder}"


def configure_ignition_from_field_config(
    fx: Any,
    field_config: dict[str, Any],
    *,
    tag_provider: str = "default",
    tag_folder: str = "FluxSim",
    opc_server: str = "Flux Sim",
    endpoint_url: str | None = None,
    collision_policy: str = "o",
    batch_size: int = 1000,
    limit: int | None = None,
    ensure_connection: bool = True,
    wait_connected: bool = True,
    connect_timeout_seconds: float = 45.0,
) -> IgnitionConfigureResult:
    endpoint = first_endpoint(field_config)
    selected_endpoint_url = endpoint_url or endpoint.get("endpoint_url") or endpoint.get("endpointUrl")
    if not selected_endpoint_url:
        raise ValueError("FieldAgent config endpoint is missing endpoint_url")

    tags = list(ignition_tag_configs(field_config, opc_server=opc_server, tag_provider=tag_provider, limit=limit))
    if limit is not None and not has_preserved_ignition_tree(field_config):
        tags = tags[:limit]

    if ensure_connection:
        ensure_opcua_connection(fx, opc_server, selected_endpoint_url)
    if wait_connected:
        wait_for_opc_connected(fx, opc_server, timeout_seconds=connect_timeout_seconds)

    preserved_tree = has_preserved_ignition_tree(field_config)
    if preserved_tree:
        type_tags, runtime_tags = split_preserved_tree_tags(tags)
        batches = 0
        for batch in chunked(type_tags, batch_size):
            fx.tag.configure(
                batch,
                base_path=f"[{tag_provider}]",
                collision_policy=collision_policy,
            )
            batches += 1
        if tag_folder:
            fx.tag.configure(
                [{"name": tag_folder, "tagType": "Folder", "tags": []}],
                base_path=f"[{tag_provider}]",
                collision_policy=collision_policy,
            )
        runtime_base_path = f"[{tag_provider}]{tag_folder}" if tag_folder else f"[{tag_provider}]"
        for batch in chunked(runtime_tags, batch_size):
            fx.tag.configure(
                batch,
                base_path=runtime_base_path,
                collision_policy=collision_policy,
            )
            batches += 1
        return IgnitionConfigureResult(
            tag_provider=tag_provider,
            tag_folder=tag_folder,
            opc_server=opc_server,
            endpoint_url=str(selected_endpoint_url),
            tag_count=len(tags),
            batches=batches,
        )

    if not preserved_tree:
        fx.tag.configure(
            [{"name": tag_folder, "tagType": "Folder", "tags": []}],
            base_path=f"[{tag_provider}]",
            collision_policy=collision_policy,
        )
    batches = 0
    for batch in chunked(tags, batch_size):
        fx.tag.configure(
            batch,
            base_path=f"[{tag_provider}]{tag_folder}",
            collision_policy=collision_policy,
        )
        batches += 1

    return IgnitionConfigureResult(
        tag_provider=tag_provider,
        tag_folder=tag_folder,
        opc_server=opc_server,
        endpoint_url=str(selected_endpoint_url),
        tag_count=len(tags),
        batches=batches,
    )


def ignition_tag_configs(
    field_config: dict[str, Any], *, opc_server: str = "", tag_provider: str = "default", limit: int | None = None
) -> Iterable[dict[str, Any]]:
    preserved_tags = field_config.get("ignition", {}).get("tags")
    if isinstance(preserved_tags, list):
        yield from tree_preserving_ignition_tag_configs(
            field_config, opc_server=opc_server, tag_provider=tag_provider, limit=limit
        )
        return
    for endpoint in field_config.get("endpoints") or []:
        for device in endpoint.get("devices") or []:
            for tag in device.get("tags") or []:
                yield ignition_tag_config(tag, opc_server=opc_server)


def tree_preserving_ignition_tag_configs(
    field_config: dict[str, Any], *, opc_server: str = "", tag_provider: str = "default", limit: int | None = None
) -> Iterable[dict[str, Any]]:
    tags = field_config.get("ignition", {}).get("tags") or []
    selected_paths = selected_source_tag_paths(field_config, limit=limit)
    field_tags = field_tags_by_source_path(field_config)
    for tag in tags:
        if not isinstance(tag, dict):
            continue
        selected_tag = prune_ignition_tag_tree(tag, selected_paths) if selected_paths is not None else tag
        if selected_tag is not None:
            yield rewrite_ignition_tag_config(
                selected_tag,
                opc_server=opc_server,
                field_tags=field_tags,
                tag_provider=tag_provider,
            )


def split_preserved_tree_tags(tags: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    type_tags = []
    runtime_tags = []
    for tag in tags:
        name = str(tag.get("name") or "")
        if name.lower() == "_types_":
            type_tags.append(tag)
        else:
            runtime_tags.append(tag)
    return type_tags, runtime_tags


def has_preserved_ignition_tree(field_config: dict[str, Any]) -> bool:
    return isinstance(field_config.get("ignition", {}).get("tags"), list)


def selected_source_tag_paths(field_config: dict[str, Any], *, limit: int | None) -> set[str] | None:
    configured_paths = field_config.get("ignition", {}).get("selected_source_paths")
    if isinstance(configured_paths, list):
        paths = [str(path) for path in configured_paths]
        if limit is not None:
            paths = paths[:limit]
        return set(paths)
    if limit is None:
        return None
    paths: list[str] = []
    for endpoint in field_config.get("endpoints") or []:
        for device in endpoint.get("devices") or []:
            for tag in device.get("tags") or []:
                source_path = str(tag.get("source_tag_path") or "")
                if source_path:
                    paths.append(source_path)
                    if len(paths) >= limit:
                        return set(paths)
    return set(paths)


def prune_ignition_tag_tree(tag: dict[str, Any], selected_paths: set[str], parent_path: str = "") -> dict[str, Any] | None:
    name = str(tag.get("name") or "")
    path = join_tag_path(parent_path, name)
    if path == "_types_":
        return tag
    children = []
    for child in tag.get("tags") or []:
        if isinstance(child, dict):
            pruned_child = prune_ignition_tag_tree(child, selected_paths, path)
            if pruned_child is not None:
                children.append(pruned_child)
    keep = bool(children) or any(source_path == path or source_path.startswith(path + "/") for source_path in selected_paths)
    if not keep:
        return None
    result = copy.deepcopy(tag)
    if children:
        result["tags"] = children
    else:
        result.pop("tags", None)
    return result


def field_tags_by_source_path(field_config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    tags = {}
    for endpoint in field_config.get("endpoints") or []:
        for device in endpoint.get("devices") or []:
            for tag in device.get("tags") or []:
                source_path = str(tag.get("source_tag_path") or "")
                if source_path:
                    tags[source_path] = tag
    return tags


def rewrite_ignition_tag_config(
    tag: dict[str, Any],
    *,
    opc_server: str = "",
    field_tags: dict[str, dict[str, Any]] | None = None,
    tag_provider: str = "default",
) -> dict[str, Any]:
    config = copy.deepcopy(tag)
    rewrite_opc_bindings(config, opc_server=opc_server, field_tags=field_tags or {}, tag_provider=tag_provider)
    return config


def rewrite_opc_bindings(
    config: dict[str, Any],
    *,
    opc_server: str = "",
    field_tags: dict[str, dict[str, Any]],
    tag_provider: str = "default",
    parent_path: str = "",
) -> None:
    path = join_tag_path(parent_path, str(config.get("name") or ""))
    config.pop("tagGroup", None)
    if "typeId" in config:
        config["typeId"] = rewrite_type_id(str(config.get("typeId") or ""), tag_provider=tag_provider)
    field_tag = field_tags.get(path)
    if field_tag is not None and str(config.get("valueSource") or "") == "opc":
        config["opcServer"] = opc_server
        config["opcItemPath"] = str(field_tag.get("node_id") or field_tag.get("opc_item_path") or "")
    if not opc_server:
        return
    parameters = config.get("parameters")
    if isinstance(parameters, dict):
        for key, value in parameters.items():
            if normalized_parameter_name(str(key)) in {"opcserver", "opcservername"}:
                parameters[key] = rewritten_parameter_value(value, opc_server)
    opc_server_value = config.get("opcServer")
    if "opcServer" in config and (isinstance(opc_server_value, str) or opc_server_value is None):
        config["opcServer"] = opc_server
    for child in config.get("tags") or []:
        if isinstance(child, dict):
            rewrite_opc_bindings(
                child,
                opc_server=opc_server,
                field_tags=field_tags,
                tag_provider=tag_provider,
                parent_path=path,
            )


def normalized_parameter_name(name: str) -> str:
    return "".join(character for character in name.lower() if character.isalnum())


def join_tag_path(parent_path: str, name: str) -> str:
    if not parent_path:
        return name
    if not name:
        return parent_path
    return f"{parent_path}/{name}"


def rewrite_type_id(type_id: str, *, tag_provider: str) -> str:
    marker = "_types_/"
    if marker in type_id:
        return f"[{tag_provider}]_types_/{type_id.split(marker, 1)[1].strip('/')}"
    return type_id


def rewritten_parameter_value(value: Any, opc_server: str) -> Any:
    if isinstance(value, dict):
        result = dict(value)
        result["value"] = opc_server
        result.setdefault("dataType", "String")
        return result
    return {"dataType": "String", "value": opc_server}


def ignition_tag_config(field_tag: dict[str, Any], *, opc_server: str = "") -> dict[str, Any]:
    return {
        "name": str(field_tag["name"]),
        "tagType": "AtomicTag",
        "valueSource": "opc",
        "dataType": ignition_data_type(str(field_tag.get("data_type") or "string")),
        "opcServer": opc_server,
        "opcItemPath": str(field_tag.get("node_id") or field_tag.get("opc_item_path") or ""),
    }


def ensure_opcua_connection(fx: Any, opc_server: str, endpoint_url: str) -> None:
    try:
        fx.opcua.remove_connection(opc_server)
    except Exception:
        pass
    try:
        fx.opcua.add_connection(
            opc_server,
            "Flux Sim OPC UA simulator",
            endpoint_url,
            endpoint_url,
            security_policy="None",
            security_mode="None",
            settings={
                "ENABLED": True,
                "DISCOVERYURL": endpoint_url,
                "ENDPOINTURL": endpoint_url,
                "SECURITYPOLICY": "None",
                "SECURITYMODE": "None",
                "CERTIFICATEVALIDATIONENABLED": False,
                "CONNECTTIMEOUT": 5000,
                "ACKNOWLEDGETIMEOUT": 5000,
                "REQUESTTIMEOUT": 5000,
                "SESSIONTIMEOUT": 60000,
            },
        )
    except Exception:
        fx.scripting.run_function_file("opcua_connection", "remove", opc_server, endpoint_url, target_directory="field")
        fx.scripting.run_function_file("opcua_connection", "add", opc_server, endpoint_url, target_directory="field")


def wait_for_opc_connected(fx: Any, opc_server: str, *, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_state = None
    while time.monotonic() < deadline:
        servers = fx.opc.get_servers(include_disabled=True)
        if opc_server in servers:
            last_state = fx.opc.get_server_state(opc_server)
            if last_state and "CONNECT" in last_state.upper():
                return
        time.sleep(1)
    raise TimeoutError(f"OPC server {opc_server!r} did not connect; last_state={last_state!r}")


def first_endpoint(field_config: dict[str, Any]) -> dict[str, Any]:
    endpoints = field_config.get("endpoints") or []
    if not endpoints:
        raise ValueError("FieldAgent config has no endpoints")
    return dict(endpoints[0])


def ignition_data_type(data_type: str) -> str:
    return {
        "bool": "Boolean",
        "boolean": "Boolean",
        "int": "Int4",
        "integer": "Int4",
        "float": "Float8",
        "double": "Float8",
        "string": "String",
    }.get(data_type.lower(), "String")


def chunked(items: list[dict[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
    if size < 1:
        raise ValueError("batch_size must be at least 1")
    for index in range(0, len(items), size):
        yield items[index : index + size]
