from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class HmiTagReference:
    original: str
    shortcut: str
    scope: str
    base_tag: str
    member_path: str = ""
    raw_tag_path: str = ""

    @property
    def is_program_scoped(self) -> bool:
        return self.scope != "Global"


def parse_hmi_tag_reference(value: str) -> HmiTagReference:
    original = value.strip()
    path = unwrap_factorytalk_reference(original)
    match = re.match(r"^\[(?P<shortcut>[^\]]+)\](?P<body>.*)$", path)
    if not match:
        raise ValueError(f"HMI tag reference does not start with a shortcut: {value}")
    shortcut = match.group("shortcut").strip()
    body = match.group("body").strip()
    scope = "Global"
    if body.startswith("Program:"):
        program, _, remainder = body.partition(".")
        scope = program.replace("Program:", "", 1)
        body = remainder
    base_tag, member_path = split_base_and_member(body)
    if not base_tag:
        raise ValueError(f"HMI tag reference is missing a base tag: {value}")
    return HmiTagReference(
        original=original,
        shortcut=shortcut,
        scope=scope,
        base_tag=base_tag,
        member_path=member_path,
        raw_tag_path=body,
    )


def extract_hmi_tag_references(text: str) -> tuple[HmiTagReference, ...]:
    references: list[HmiTagReference] = []
    seen: set[str] = set()
    for candidate in factorytalk_reference_candidates(text):
        try:
            reference = parse_hmi_tag_reference(candidate)
        except ValueError:
            continue
        key = reference.original
        if key in seen:
            continue
        seen.add(key)
        references.append(reference)
    return tuple(references)


def factorytalk_reference_candidates(text: str) -> tuple[str, ...]:
    if not text or "[" not in text or "]" not in text:
        return ()
    candidates: list[str] = []
    for match in re.finditer(r"\{[^{}]*\[[^\]]+\][^{}]*\}", text):
        candidates.append(match.group(0))
    for match in re.finditer(r"(?<![\w{])\[[^\]]+\][A-Za-z0-9_:.\[\],]+", text):
        candidates.append(match.group(0))
    return tuple(candidates)


def unwrap_factorytalk_reference(value: str) -> str:
    path = value.strip()
    if path.startswith("{") and path.endswith("}"):
        path = path[1:-1].strip()
    if "::" in path:
        path = path.split("::", 1)[1].strip()
    return path


def split_base_and_member(path: str) -> tuple[str, str]:
    for index, char in enumerate(path):
        if char == "." or char == "[":
            return path[:index], path[index:].lstrip(".")
    return path, ""
