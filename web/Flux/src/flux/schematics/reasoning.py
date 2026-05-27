from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .models import Circuit
from .models import Component
from .models import SchematicSystem
from .models import SourceTerminal
from .models import Terminal


MAX_TRACE_DEPTH = 32
MAX_TRACE_PATHS = 8


@dataclass(frozen=True)
class TraceStep:
    node: str
    label: str
    condition: str = ""


@dataclass(frozen=True)
class TerminalTrace:
    circuit: str
    component: str
    terminal: str
    potential: str
    conditions: tuple[str, ...]
    steps: tuple[TraceStep, ...]


def explain_component_energization(system: SchematicSystem, component_reference: str) -> dict:
    component = system.components.get(reference=component_reference)
    traces: list[TerminalTrace] = []
    for participation in component.circuit_participations.select_related("circuit", "role").order_by(
        "circuit__sort_order",
        "sort_order",
    ):
        circuit = participation.circuit
        for link in participation.role.terminal_links.select_related("terminal").order_by("sort_order", "terminal__key"):
            if not link.interface_key:
                continue
            traces.extend(trace_terminal_from_source(circuit, link.terminal, link.interface_key))

    return {
        "component": component.reference,
        "name": component.name,
        "template": component.template.key,
        "terminal_traces": [terminal_trace_payload(trace) for trace in traces],
        "component_relations": component_relation_payloads(component),
    }


def trace_terminal_from_source(circuit: Circuit, terminal: Terminal, potential_key: str) -> list[TerminalTrace]:
    source_terminal = circuit.source.terminals.filter(key=potential_key).first()
    if source_terminal is None:
        return []

    graph = build_circuit_graph(circuit)
    start = source_node(source_terminal.id)
    target = terminal_node(terminal.id)
    queue = deque([(start, [TraceStep(start, source_terminal_label(source_terminal), source_condition(circuit))], tuple())])
    paths: list[TerminalTrace] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()

    while queue and len(paths) < MAX_TRACE_PATHS:
        node, steps, conditions = queue.popleft()
        if len(steps) > MAX_TRACE_DEPTH:
            continue
        if node == target:
            paths.append(
                TerminalTrace(
                    circuit=circuit.name,
                    component=terminal.component.reference,
                    terminal=terminal.key,
                    potential=potential_key,
                    conditions=conditions,
                    steps=tuple(steps),
                )
            )
            continue

        seen_key = (node, conditions)
        if seen_key in seen:
            continue
        seen.add(seen_key)

        for next_node, label, condition in graph.get(node, []):
            next_conditions = append_condition(conditions, condition)
            queue.append((next_node, [*steps, TraceStep(next_node, label, condition)], next_conditions))

    return paths


def build_circuit_graph(circuit: Circuit) -> dict[str, list[tuple[str, str, str]]]:
    graph: dict[str, list[tuple[str, str, str]]] = {}

    for source_connection in circuit.source_connections.select_related("source_terminal", "net"):
        condition = source_condition(circuit)
        add_edge(
            graph,
            source_node(source_connection.source_terminal_id),
            net_node(source_connection.net_id),
            f"source feeds net {source_connection.net.key}",
            condition,
        )

    for net_terminal in circuit.net_terminals.select_related("net", "terminal__component"):
        add_edge(
            graph,
            net_node(net_terminal.net_id),
            terminal_node(net_terminal.terminal_id),
            f"net {net_terminal.net.key} reaches {net_terminal.terminal}",
            net_terminal.condition_key,
        )
        add_edge(
            graph,
            terminal_node(net_terminal.terminal_id),
            net_node(net_terminal.net_id),
            f"{net_terminal.terminal} is on net {net_terminal.net.key}",
            net_terminal.condition_key,
        )

    for participant in circuit.participants.select_related("role"):
        for continuity in participant.role.continuities.select_related("from_terminal", "to_terminal"):
            add_edge(
                graph,
                terminal_node(continuity.from_terminal_id),
                terminal_node(continuity.to_terminal_id),
                f"{participant.component.reference}.{continuity.from_terminal.key}->{continuity.to_terminal.key}",
                continuity.condition_key,
            )

    return graph


def add_edge(graph: dict[str, list[tuple[str, str, str]]], from_node: str, to_node: str, label: str, condition: str) -> None:
    graph.setdefault(from_node, []).append((to_node, label, condition))


def append_condition(conditions: tuple[str, ...], condition: str) -> tuple[str, ...]:
    if not condition or condition in conditions:
        return conditions
    return (*conditions, condition)


def source_condition(circuit: Circuit) -> str:
    if circuit.source.producer_role_id:
        return circuit.source.producer_role.metadata.get("source_condition", "")
    return ""


def terminal_trace_payload(trace: TerminalTrace) -> dict:
    return {
        "circuit": trace.circuit,
        "component": trace.component,
        "terminal": trace.terminal,
        "potential": trace.potential,
        "conditions": list(trace.conditions),
        "steps": [
            {
                "node": step.node,
                "label": step.label,
                "condition": step.condition,
            }
            for step in trace.steps
        ],
    }


def component_relation_payloads(component: Component) -> list[dict]:
    return [
        {
            "key": relation.key,
            "type": relation.relation_type,
            "source_role": relation.source_role.key,
            "target_role": relation.target_role.key,
            "condition": relation.condition_key,
            "effect": relation.effect_key,
        }
        for relation in component.internal_relations.select_related("source_role", "target_role").order_by("key")
    ]


def source_terminal_label(source_terminal: SourceTerminal) -> str:
    return f"source {source_terminal.source.name}.{source_terminal.key}"


def source_node(source_terminal_id: int) -> str:
    return f"source:{source_terminal_id}"


def net_node(net_id: int) -> str:
    return f"net:{net_id}"


def terminal_node(terminal_id: int) -> str:
    return f"terminal:{terminal_id}"
