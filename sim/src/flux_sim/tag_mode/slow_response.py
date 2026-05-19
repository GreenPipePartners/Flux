from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .base import TagModeConfig, TagModeResult


class SlowResponseTagMode:
    def value_to_write(self, target_value: Any, *, now: datetime, config: TagModeConfig) -> TagModeResult:
        delay_seconds = max(int(config.response_delay_seconds), 0)
        if delay_seconds == 0:
            return TagModeResult(value=target_value)
        if config.pending_apply_at is not None and config.pending_apply_at <= now:
            return TagModeResult(value=config.pending_value)
        current_value = config.last_value
        if current_value is None:
            return TagModeResult(value=target_value)
        if current_value == target_value:
            return TagModeResult(value=current_value)
        if config.pending_value != target_value:
            return TagModeResult(
                value=current_value,
                pending_value=target_value,
                pending_apply_at=now + timedelta(seconds=delay_seconds),
            )
        return TagModeResult(value=current_value, pending_value=config.pending_value, pending_apply_at=config.pending_apply_at)
