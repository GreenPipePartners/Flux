from __future__ import annotations

from datetime import datetime
from typing import Any

from .base import TagModeConfig, TagModeKind, TagModeResult, TagModeStrategy
from .ignore_write import IgnoreWriteTagMode
from .immediate import ImmediateTagMode
from .slow_response import SlowResponseTagMode
from .write_to_other_tag_response import WriteToOtherTagResponseMode


def mode_for_kind(kind: str) -> TagModeStrategy:
    if kind == TagModeKind.IGNORES_WRITE:
        return IgnoreWriteTagMode()
    if kind == TagModeKind.SLOW_RESPONSE:
        return SlowResponseTagMode()
    if kind == TagModeKind.WRITE_TO_OTHER_TAG_RESPONSE:
        return WriteToOtherTagResponseMode()
    return ImmediateTagMode()


def value_to_write(target_value: Any, *, now: datetime, config: TagModeConfig) -> TagModeResult:
    return mode_for_kind(config.kind).value_to_write(target_value, now=now, config=config)
