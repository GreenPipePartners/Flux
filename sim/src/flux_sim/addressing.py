from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol, TypedDict


class AddressFields(TypedDict, total=False):
    raw: str
    device: str
    member: str
    symbol: str
    scope: str
    local_member: str
    array_index: str
    register: str
    address: str


class AddressStrategy(Protocol):
    key: str

    def parse(self, opc_item_path: str) -> AddressFields:
        ...


@dataclass(frozen=True)
class GenericAddressStrategy:
    key: str = "generic"

    def parse(self, opc_item_path: str) -> AddressFields:
        device, member = split_opc_symbol(opc_item_path)
        return {"raw": opc_item_path, "device": device, "member": member}


@dataclass(frozen=True)
class LogixAddressStrategy:
    key: str = "logix"

    def parse(self, opc_item_path: str) -> AddressFields:
        device, member = split_opc_symbol(opc_item_path)
        result: AddressFields = {"raw": opc_item_path, "device": device, "symbol": member}
        if ":" in member:
            scope, local_member = member.split(":", 1)
            result["scope"] = scope
            result["local_member"] = local_member
        array_match = re.search(r"\[(\d+)\]", member)
        if array_match:
            result["array_index"] = array_match.group(1)
        return result


@dataclass(frozen=True)
class AcmAddressStrategy:
    key: str = "acm"

    def parse(self, opc_item_path: str) -> AddressFields:
        device, member = split_opc_symbol(opc_item_path)
        return {"raw": opc_item_path, "device": device, "member": member}


@dataclass(frozen=True)
class ModbusAddressStrategy:
    key: str = "modbus"

    def parse(self, opc_item_path: str) -> AddressFields:
        device, member = split_opc_symbol(opc_item_path)
        return {"raw": opc_item_path, "device": device, "register": member}


@dataclass(frozen=True)
class SiemensAddressStrategy:
    key: str = "siemens"

    def parse(self, opc_item_path: str) -> AddressFields:
        device, member = split_opc_symbol(opc_item_path)
        return {"raw": opc_item_path, "device": device, "address": member}


def strategy_for_key(key: str) -> AddressStrategy:
    strategies: dict[str, AddressStrategy] = {
        "acm": AcmAddressStrategy(),
        "generic": GenericAddressStrategy(),
        "logix": LogixAddressStrategy(),
        "modbus": ModbusAddressStrategy(),
        "siemens": SiemensAddressStrategy(),
    }
    return strategies.get(key, strategies["generic"])


def parse_address(strategy_key: str, opc_item_path: str) -> AddressFields:
    return strategy_for_key(strategy_key).parse(opc_item_path)


def split_opc_symbol(opc_item_path: str) -> tuple[str, str]:
    match = re.search(r";s=([^\[]+)", opc_item_path)
    symbol = match.group(1) if match else opc_item_path
    if "." not in symbol:
        return symbol, ""
    device, member = symbol.split(".", 1)
    return device, member
