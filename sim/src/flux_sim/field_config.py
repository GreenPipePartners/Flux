from __future__ import annotations

from pathlib import Path
from typing import Any

from flux_sim.reconstruction import (
    ExpressionInterface,
    build_sim_provider_model,
    load_ignition_expression_interface,
    load_imported_provider_tree,
)
from flux_sim.runtime import SimulatedOpcServer


def build_field_agent_config(
    database_path: str | Path,
    *,
    provider_name: str,
    expression_interface: ExpressionInterface | None = None,
    endpoint_url: str = "opc.tcp://localhost:4840/flux/sim",
    namespace_uri: str = "urn:flux:sim",
    include_unresolved: bool = False,
) -> dict[str, Any]:
    interface = expression_interface or load_ignition_expression_interface()
    tree = load_imported_provider_tree(database_path, provider_name)
    model = build_sim_provider_model(tree, expression_interface=interface)
    server = SimulatedOpcServer.from_provider_model(model, include_unresolved=include_unresolved)
    return server.to_field_agent_config(
        endpoint_name=provider_name,
        endpoint_url=endpoint_url,
        namespace_uri=namespace_uri,
    )
