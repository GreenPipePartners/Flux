from __future__ import annotations

from typing import Any, Protocol


class FluxyLike(Protocol):
    tag: Any
    historian: Any


def delete_configured_tags(fx: FluxyLike, *, provider: str, folder_path: str) -> int:
    return delete_tag_branch(fx, provider=provider, folder_path=folder_path)


def delete_tag_branch(fx: FluxyLike, *, provider: str, folder_path: str) -> int:
    folder_path = folder_path.strip("/")
    if not provider or not folder_path:
        raise ValueError("provider and folder_path are required to delete simulated tags")
    fx.tag.delete_tags([f"[{provider}]{folder_path}"])
    return 1
