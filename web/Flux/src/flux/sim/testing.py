from __future__ import annotations

from typing import Any

from flux.base.models import Tag
from flux.sim.models import FieldEndpoint
from flux.sim.models import SimDriver, SimServer, TagNode, TagProvider
from flux.sim.kernel_sync import upsert_device_config, upsert_tag_config
from flux.sim.models import DeviceConfig, TagConfig


def create_device_config(
    *,
    endpoint: FieldEndpoint | None = None,
    provider: TagProvider | None = None,
    provider_name: str = "Tag_02",
    name: str = "RTU_01",
    device_type: str = "OPC UA",
    driver: SimDriver | None = None,
    sim_server: SimServer | None = None,
    browse_path: str | None = None,
    mode: str = DeviceConfig.Mode.STANDARD,
    response_delay_ms: int = 0,
    enabled: bool = True,
    source_status: str = "",
    source_detail: str = "",
    config: dict[str, Any] | None = None,
) -> DeviceConfig:
    if provider is None and endpoint is None:
        provider, _created = TagProvider.objects.get_or_create(
            name=provider_name,
            defaults={"sim_server": sim_server},
        )
    if provider is not None and sim_server is not None and provider.sim_server_id != sim_server.id:
        provider.sim_server = sim_server
        provider.save(update_fields=["sim_server"])
    if driver is None:
        driver, _created = SimDriver.objects.get_or_create(
            key="opc_ua",
            defaults={"label": device_type, "strategy_key": "acm"},
        )
    namespace = f"endpoint:{endpoint.name}" if endpoint is not None else f"provider:{provider.name}"
    return upsert_device_config(
        namespace=namespace,
        name=name,
        device_type=device_type,
        endpoint=endpoint,
        source_provider=provider,
        sim_server=sim_server or (provider.sim_server if provider is not None else None),
        driver=driver,
        browse_path=browse_path if browse_path is not None else (provider.name if provider is not None else "Devices"),
        mode=mode,
        response_delay_ms=response_delay_ms,
        source_status=source_status,
        source_detail=source_detail,
        enabled=enabled,
        config=config or {},
    )


def create_tag_config(
    *,
    device: DeviceConfig,
    name: str = "PV",
    data_type: str = Tag.DataType.FLOAT,
    source_path: str | None = None,
    update_rate_ms: int = 1000,
    simulation_type: str = TagConfig.SimulationType.RAMP,
    min_value: float | None = None,
    max_value: float | None = None,
    variance: float = 0.0,
    initial_value: str = "",
    source_tag_node: TagNode | None = None,
    value_source: str = "",
    opc_server: str = "",
    opc_item_path: str = "",
    behavior: str = TagConfig.Behavior.IMMEDIATE,
    address_strategy: str = "generic",
    address: dict[str, Any] | None = None,
    mode_config: dict[str, Any] | None = None,
    enabled: bool = True,
    materialized: bool = False,
    description: str = "",
    config: dict[str, Any] | None = None,
) -> TagConfig:
    provider = device.source_provider.name if device.source_provider_id else device.endpoint.name
    tagpath = source_path or f"{device.base_device.name}/{name}"
    metadata = dict(config or {})
    if value_source:
        metadata["value_source"] = value_source
    if opc_server:
        metadata["opc_server"] = opc_server
    if opc_item_path:
        metadata["opc_item_path"] = opc_item_path
    return upsert_tag_config(
        sim_device=device,
        provider=provider,
        tagpath=tagpath,
        tag_name=name,
        data_type=data_type,
        update_rate_ms=update_rate_ms,
        simulation_type=simulation_type,
        min_value=min_value,
        max_value=max_value,
        variance=variance,
        initial_value=initial_value,
        source_tag_node=source_tag_node,
        source_path=tagpath,
        behavior=behavior,
        address_strategy=address_strategy,
        address=address or {},
        mode_config=mode_config,
        enabled=enabled,
        materialized=materialized,
        description=description or tagpath,
        config=metadata,
    )
