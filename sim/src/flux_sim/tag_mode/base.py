from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


class TagModeKind:
    IMMEDIATE = "immediate"
    SLOW_RESPONSE = "slow_response"
    IGNORES_WRITE = "ignores_write"
    WRITE_TO_OTHER_TAG_RESPONSE = "write_to_other_tag_response"


@dataclass(frozen=True)
class TagModeWrite:
    tag_path: str
    value: Any


@dataclass(frozen=True)
class TagModeConfig:
    kind: str = TagModeKind.IMMEDIATE
    response_delay_seconds: int = 0
    last_value: Any = None
    pending_value: Any = None
    pending_apply_at: datetime | None = None
    mode_config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TagModeResult:
    value: Any
    pending_value: Any = None
    pending_apply_at: datetime | None = None
    side_writes: tuple[TagModeWrite, ...] = ()


class TagModeStrategy(Protocol):
    def value_to_write(self, target_value: Any, *, now: datetime, config: TagModeConfig) -> TagModeResult:
        ...
