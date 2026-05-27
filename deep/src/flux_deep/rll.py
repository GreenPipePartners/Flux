from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Iterable


CONTACT_INSTRUCTIONS = {"XIC", "XIO"}
ACTION_INSTRUCTIONS = {"TON", "OTL", "OTU", "COP"}


@dataclass(frozen=True)
class RllInstruction:
    mnemonic: str
    operands: tuple[str, ...]
    source: str = ""

    @classmethod
    def from_row_payload(
        cls, mnemonic: str, operands: Iterable[str], raw: dict[str, Any] | None = None
    ) -> "RllInstruction":
        return cls(mnemonic=mnemonic.upper(), operands=tuple(operands), source=str((raw or {}).get("source", "")))


@dataclass(frozen=True)
class RllNetwork:
    instructions: tuple[RllInstruction, ...]


@dataclass(frozen=True)
class RllRung:
    networks: tuple[RllNetwork, ...]

    @classmethod
    def from_text_and_instructions(cls, text: str, instructions: Iterable[RllInstruction]) -> "RllRung":
        instruction_list = tuple(instructions)
        branches = split_rung_networks(text)
        if len(branches) == 1:
            return cls((RllNetwork(instruction_list),))

        remaining = list(instruction_list)
        networks: list[RllNetwork] = []
        for branch in branches:
            branch_instructions: list[RllInstruction] = []
            for instruction in list(remaining):
                if instruction.source and instruction.source in branch:
                    branch_instructions.append(instruction)
                    remaining.remove(instruction)
            networks.append(RllNetwork(tuple(branch_instructions)))

        if remaining:
            networks.append(RllNetwork(tuple(remaining)))
        return cls(tuple(networks))


@dataclass(frozen=True)
class RllProgram:
    rungs: tuple[RllRung, ...]

    def scan(self, state: "RllState", *, scan_ms: int) -> None:
        if scan_ms <= 0:
            raise ValueError("scan_ms must be positive")
        for rung in self.rungs:
            for network in rung.networks:
                execute_network(network, state, scan_ms=scan_ms)


@dataclass
class TimerValue:
    pre: int = 0
    acc: int = 0
    en: bool = False
    tt: bool = False
    dn: bool = False

    def scan(self, *, enabled: bool, scan_ms: int) -> None:
        if not enabled:
            self.en = False
            self.tt = False
            self.dn = False
            self.acc = 0
            return
        self.en = True
        self.acc = min(self.acc + scan_ms, self.pre)
        self.dn = self.acc >= self.pre
        self.tt = not self.dn


@dataclass
class RllState:
    values: dict[str, Any] = field(default_factory=dict)

    def read_bool(self, operand: str) -> bool:
        base, member = split_operand_path(operand)
        value = self.values.get(base)
        if isinstance(value, TimerValue):
            return bool(getattr(value, member.lower(), False))
        if member and isinstance(value, int) and member.isdigit():
            return bool(value & (1 << int(member)))
        return bool(value)

    def write_bool(self, operand: str, value: bool) -> None:
        base, member = split_operand_path(operand)
        if member:
            target = self.values.get(base)
            if isinstance(target, TimerValue) and hasattr(target, member.lower()):
                setattr(target, member.lower(), value)
                return
            raise ValueError(f"Unsupported boolean member write: {operand}")
        self.values[base] = value

    def timer(self, operand: str) -> TimerValue:
        base, member = split_operand_path(operand)
        if member:
            raise ValueError(f"Timer instruction requires a base timer tag: {operand}")
        value = self.values.get(base)
        if not isinstance(value, TimerValue):
            raise ValueError(f"Tag is not a timer: {base}")
        return value

    def copy_value(self, source: str, destination: str) -> None:
        source_base, source_member = split_operand_path(source)
        destination_base, destination_member = split_operand_path(destination)
        if source_member or destination_member:
            raise ValueError("COP member paths are not supported in the first Deep RLL subset")
        self.values[destination_base] = copy.deepcopy(self.values[source_base])


@dataclass(frozen=True)
class TagSeed:
    name: str
    data_type: str
    raw: dict[str, Any]


def initial_state_from_tags(tags: Iterable[TagSeed]) -> RllState:
    state = RllState()
    for tag in tags:
        state.values[tag.name] = initial_value(tag)
    return state


def initial_value(tag: TagSeed) -> Any:
    data_type = tag.data_type.upper()
    l5k = l5k_payload(tag.raw)
    if data_type == "BOOL":
        return str(l5k).strip() in {"1", "true", "True"}
    if data_type in {"DINT", "INT", "SINT"}:
        return int(str(l5k or "0").strip())
    if data_type == "STRING":
        string_payload = string_payload_text(tag.raw)
        if string_payload is not None:
            return unquoted(string_payload)
        return string_from_l5k(str(l5k))
    if data_type == "TIMER":
        parts = l5k_array(str(l5k))
        return TimerValue(pre=int(parts[1]) if len(parts) > 1 else 0, acc=int(parts[2]) if len(parts) > 2 else 0)
    return l5k


def execute_network(network: RllNetwork, state: RllState, *, scan_ms: int) -> None:
    power = True
    for instruction in network.instructions:
        mnemonic = instruction.mnemonic.upper()
        if mnemonic == "XIC":
            power = power and state.read_bool(instruction.operands[0])
        elif mnemonic == "XIO":
            power = power and not state.read_bool(instruction.operands[0])
        elif mnemonic == "TON":
            state.timer(instruction.operands[0]).scan(enabled=power, scan_ms=scan_ms)
        elif mnemonic == "OTL" and power:
            state.write_bool(instruction.operands[0], True)
        elif mnemonic == "OTU" and power:
            state.write_bool(instruction.operands[0], False)
        elif mnemonic == "COP" and power:
            state.copy_value(instruction.operands[0], instruction.operands[1])
        elif mnemonic not in CONTACT_INSTRUCTIONS | ACTION_INSTRUCTIONS:
            raise ValueError(f"Unsupported RLL instruction: {instruction.mnemonic}")


def split_rung_networks(text: str) -> tuple[str, ...]:
    stripped = text.strip().rstrip(";").strip()
    if not stripped.startswith("[") or not stripped.endswith("]"):
        return (stripped,)
    networks: list[str] = []
    depth = 0
    start = 0
    body = stripped[1:-1]
    for index, char in enumerate(body):
        if char == "(":
            depth += 1
        elif char == ")" and depth:
            depth -= 1
        elif char == "," and depth == 0:
            networks.append(body[start:index].strip())
            start = index + 1
    networks.append(body[start:].strip())
    return tuple(network for network in networks if network)


def split_operand_path(operand: str) -> tuple[str, str]:
    cleaned = operand.strip()
    if "." not in cleaned:
        return cleaned, ""
    base, member = cleaned.split(".", 1)
    return base, member


def l5k_payload(raw: dict[str, Any]) -> str:
    for payload in raw.get("data", []):
        if str(payload.get("format", "")).lower() == "l5k":
            return str(payload.get("text", "")).strip()
    source = str(raw.get("source", ""))
    if ":=" in source:
        return source.split(":=", 1)[1].strip().rstrip(";")
    return ""


def string_payload_text(raw: dict[str, Any]) -> str | None:
    for payload in raw.get("data", []):
        if str(payload.get("format", "")).lower() == "string":
            return str(payload.get("text", "")).strip()
    return None


def l5k_array(value: str) -> tuple[str, ...]:
    stripped = value.strip().strip("[]")
    return tuple(part.strip().strip("'") for part in stripped.split(",") if part.strip())


def string_from_l5k(value: str) -> str:
    parts = l5k_array(value)
    if len(parts) < 2:
        return ""
    length = int(parts[0])
    return parts[1].replace("$00", "")[:length]


def unquoted(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] == "'":
        return stripped[1:-1]
    return stripped
