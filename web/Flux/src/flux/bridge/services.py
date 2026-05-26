from __future__ import annotations

import os
from dataclasses import dataclass

from django.utils import timezone

from .models import IgnitionBridgeConfig


@dataclass(frozen=True)
class BridgeProbeResult:
    ok: bool
    message: str
    checked_at: object
    version: str = ""
    error: str = ""


def default_bridge_values() -> dict[str, str]:
    return {
        "base_url": os.getenv("FLUXY_BASE_URL", "http://localhost:8088/system/webdev/flux"),
        "token": os.getenv("FLUXY_TOKEN", ""),
    }


def bridge_config() -> IgnitionBridgeConfig:
    defaults = default_bridge_values()
    config, _created = IgnitionBridgeConfig.objects.get_or_create(
        name="default",
        defaults={"base_url": defaults["base_url"], "token": defaults["token"]},
    )
    return config


def update_bridge_config(
    *, base_url: str | None = None, token: str | None = None, clear_token: bool = False
) -> IgnitionBridgeConfig:
    config = bridge_config()
    if base_url:
        config.base_url = base_url
    if clear_token:
        config.token = ""
    elif token is not None:
        config.token = token
    config.last_test_ok = False
    config.last_test_message = "Connection has not been tested since the latest change."
    config.last_test_at = None
    config.save()
    return config


def fluxy_client(config: IgnitionBridgeConfig | None = None):
    import fluxy

    config = config or bridge_config()
    return fluxy.Fluxy(base_url=config.base_url, token=config.token or None)


def probe_bridge(config: IgnitionBridgeConfig | None = None) -> BridgeProbeResult:
    config = config or bridge_config()
    checked_at = timezone.now()
    try:
        version = fluxy_client(config).util.get_version(refresh=True)
    except Exception as exc:
        message = str(exc)[:255]
        return BridgeProbeResult(ok=False, message=message, checked_at=checked_at, error=message)
    version_text = str(version.version)
    return BridgeProbeResult(
        ok=True,
        message=f"Connected to Ignition {version_text}.",
        checked_at=checked_at,
        version=version_text,
    )


def persist_bridge_probe(config: IgnitionBridgeConfig, result: BridgeProbeResult) -> IgnitionBridgeConfig:
    config.last_test_ok = result.ok
    config.last_test_message = result.message[:255]
    config.last_test_at = result.checked_at
    config.save(update_fields=["last_test_ok", "last_test_message", "last_test_at", "updated_at"])
    return config


def test_bridge(config: IgnitionBridgeConfig | None = None) -> IgnitionBridgeConfig:
    config = config or bridge_config()
    return persist_bridge_probe(config, probe_bridge(config))
