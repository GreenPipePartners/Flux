from __future__ import annotations

from dataclasses import dataclass


DATA_TYPE_MAPPING = {
    "BOOL": "Boolean",
    "BIT": "Boolean",
    "SINT": "Int1",
    "INT": "Int2",
    "DINT": "Int4",
    "REAL": "Float4",
    "STRING": "String",
}


IGNORED_ROCKWELL_TYPES = {
    "SERIAL_PORT_CONTROL",
    "AXIS_CIP_DRIVE",
    "MOTION_GROUP",
    "MOTION_INSTRUCTION",
    "ADD",
    "DIV",
    "MOV",
    "ALM",
    "FAL",
    "SELECT_ENHANCED",
    "SCALE",
    "AXIS_SERVO",
}


@dataclass(frozen=True)
class BuiltinMember:
    name: str
    data_type: str


@dataclass(frozen=True)
class BuiltinType:
    name: str
    members: tuple[BuiltinMember, ...]


BUILTIN_TYPES = (
    BuiltinType(
        "TIMER",
        (
            BuiltinMember("PRE", "DINT"),
            BuiltinMember("ACC", "DINT"),
            BuiltinMember("EN", "BOOL"),
            BuiltinMember("TT", "BOOL"),
            BuiltinMember("DN", "BOOL"),
        ),
    ),
    BuiltinType(
        "COUNTER",
        (
            BuiltinMember("PRE", "DINT"),
            BuiltinMember("ACC", "DINT"),
            BuiltinMember("CU", "BOOL"),
            BuiltinMember("CD", "BOOL"),
            BuiltinMember("DN", "BOOL"),
            BuiltinMember("OV", "BOOL"),
            BuiltinMember("UN", "BOOL"),
        ),
    ),
    BuiltinType(
        "CONTROL",
        (
            BuiltinMember("LEN", "DINT"),
            BuiltinMember("POS", "DINT"),
            BuiltinMember("EN", "BOOL"),
            BuiltinMember("EU", "BOOL"),
            BuiltinMember("DN", "BOOL"),
            BuiltinMember("EM", "BOOL"),
            BuiltinMember("ER", "BOOL"),
            BuiltinMember("UL", "BOOL"),
            BuiltinMember("IN", "BOOL"),
            BuiltinMember("FD", "BOOL"),
        ),
    ),
    BuiltinType(
        "MESSAGE",
        (
            BuiltinMember("ERR", "DINT"),
            BuiltinMember("EN", "BOOL"),
            BuiltinMember("ST", "BOOL"),
            BuiltinMember("DN", "BOOL"),
            BuiltinMember("ER", "BOOL"),
            BuiltinMember("EW", "BOOL"),
        ),
    ),
    BuiltinType(
        "CONNECTION_STATUS",
        (
            BuiltinMember("RunMode", "BOOL"),
            BuiltinMember("ConnectionFaulted", "BOOL"),
        ),
    ),
    BuiltinType(
        "PID",
        (
            BuiltinMember("SP", "REAL"),
            BuiltinMember("KP", "REAL"),
            BuiltinMember("KI", "REAL"),
            BuiltinMember("KD", "REAL"),
            BuiltinMember("BIAS", "REAL"),
            BuiltinMember("MAXS", "REAL"),
            BuiltinMember("MINS", "REAL"),
            BuiltinMember("DB", "REAL"),
            BuiltinMember("SO", "REAL"),
            BuiltinMember("MAXI", "REAL"),
            BuiltinMember("MINI", "REAL"),
            BuiltinMember("UPD", "REAL"),
            BuiltinMember("OUT", "REAL"),
            BuiltinMember("PV", "REAL"),
            BuiltinMember("ERR", "REAL"),
        ),
    ),
)


def ignition_data_type(rockwell_type: str, *, is_array: bool = False) -> str:
    ignition_type = DATA_TYPE_MAPPING.get(rockwell_type.upper(), "")
    if ignition_type and is_array:
        return f"{ignition_type}Array"
    return ignition_type


def builtin_type_named(name: str) -> BuiltinType | None:
    normalized = name.upper()
    for builtin in BUILTIN_TYPES:
        if builtin.name.upper() == normalized:
            return builtin
    return None
