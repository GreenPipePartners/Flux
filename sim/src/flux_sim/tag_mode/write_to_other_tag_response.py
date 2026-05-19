from __future__ import annotations

from datetime import datetime
from typing import Any

from .base import TagModeConfig, TagModeResult, TagModeWrite


class WriteToOtherTagResponseMode:
    def value_to_write(self, target_value: Any, *, now: datetime, config: TagModeConfig) -> TagModeResult:
        mode_config = config.mode_config or {}
        response_tag_path = str(mode_config.get("response_tag_path") or "").strip()
        if not response_tag_path:
            return TagModeResult(value=target_value)
        trigger_value = mode_config.get("trigger_value")
        if trigger_value is not None and target_value != trigger_value:
            return TagModeResult(value=target_value)
        return TagModeResult(
            value=target_value,
            side_writes=(TagModeWrite(tag_path=response_tag_path, value=mode_config.get("response_value")),),
        )
