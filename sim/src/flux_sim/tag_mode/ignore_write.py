from __future__ import annotations

from datetime import datetime
from typing import Any

from .base import TagModeConfig, TagModeResult


class IgnoreWriteTagMode:
    def value_to_write(self, target_value: Any, *, now: datetime, config: TagModeConfig) -> TagModeResult:
        if config.last_value is None:
            return TagModeResult(value=target_value)
        return TagModeResult(value=config.last_value)
