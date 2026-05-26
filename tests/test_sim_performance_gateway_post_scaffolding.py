from __future__ import annotations

import ast
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class SyncOperation:
    handler: str
    operation: str
    line: int
    reason: str


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SIM_VIEWS = PROJECT_ROOT / "web" / "Flux" / "src" / "flux" / "sim" / "views.py"

HEAVY_SYNC_OPERATION_REASONS = {
    "import_provider_json_bytes": "provider JSON import runs inside the request/response path",
    "fluxy.Fluxy": "live gateway client is constructed inside the request/response path",
    "import_provider_from_fluxy": "live provider import pulls gateway data before the POST returns",
    "delete_tag_branch": "gateway tag deletion runs before the POST returns",
    "delete_rehydrated_paths": "gateway rehydrated branch deletion runs before the POST returns",
    "materialize_rehydration_backing": "rehydration backing rows are materialized inside the POST",
    "build_rehydration_plan": "rehydration config forest is built inside the POST",
    "apply_rehydration_plan": "gateway tag configure calls run before the POST returns",
}


def test_sim_post_handlers_do_not_run_heavy_gateway_or_rehydration_work_inline():
    """POSTs enqueue work and return without gateway IO or rehydration work."""

    assert sim_post_handler_sync_operations() == []


def test_sim_post_handler_sync_work_inventory_stays_empty():
    """Report handler names if heavy sync work is reintroduced."""

    inventory = defaultdict(list)
    for operation in sim_post_handler_sync_operations():
        inventory[operation.handler].append(operation.operation)

    assert dict(inventory) == {}


def sim_post_handler_sync_operations() -> list[SyncOperation]:
    tree = ast.parse(SIM_VIEWS.read_text(encoding="utf-8"), filename=str(SIM_VIEWS))
    operations: list[SyncOperation] = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or not is_require_post_handler(node):
            continue
        calls = sorted(
            (child for child in ast.walk(node) if isinstance(child, ast.Call)),
            key=lambda child: (child.lineno, child.col_offset),
        )
        for call in calls:
            operation = call_name(call.func)
            if operation in HEAVY_SYNC_OPERATION_REASONS:
                operations.append(
                    SyncOperation(
                        handler=node.name,
                        operation=operation,
                        line=call.lineno,
                        reason=HEAVY_SYNC_OPERATION_REASONS[operation],
                    )
                )
    return operations


def is_require_post_handler(node: ast.FunctionDef) -> bool:
    return any(call_name(decorator) == "require_POST" for decorator in node.decorator_list)


def call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    if isinstance(node, ast.Call):
        return call_name(node.func)
    return ""
