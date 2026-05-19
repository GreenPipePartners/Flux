from __future__ import annotations

from datetime import datetime
from typing import Any

from .base import TagModeConfig, TagModeResult


class ImmediateTagMode:
    def value_to_write(self, target_value: Any, *, now: datetime, config: TagModeConfig) -> TagModeResult:
        return TagModeResult(value=target_value)
