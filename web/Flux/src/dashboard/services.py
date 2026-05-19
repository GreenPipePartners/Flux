from __future__ import annotations

import os
import socket
from dataclasses import dataclass

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from flux.base.models import FieldEndpoint, FieldTag
from flux.base.runtime import LatestTagValue, RuntimeTag, TagSample
from flux.sim.demo import parse_fluxy_timestamp

from .models import IgnitionBridgeConfig


@dataclass(frozen=True)
class ReadinessItem:
    label: str
    state: str
    detail: str
    action_label: str = ""
    action_url: str = ""


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


def fluxy_client():
    import fluxy

    config = bridge_config()
    return fluxy.Fluxy(base_url=config.base_url, token=config.token or None)


def test_bridge() -> IgnitionBridgeConfig:
    config = bridge_config()
    try:
        version = fluxy_client().util.get_version(refresh=True)
    except Exception as exc:
        config.last_test_ok = False
        config.last_test_message = str(exc)[:255]
    else:
        config.last_test_ok = True
        config.last_test_message = f"Connected to Ignition {version.version}."
    config.last_test_at = timezone.now()
    config.save(update_fields=["last_test_ok", "last_test_message", "last_test_at", "updated_at"])
    return config


def port_is_open(host: str, port: int, timeout: float = 0.15) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def stale_tag_item(tag: RuntimeTag, reason: str, age_seconds: int | None) -> dict[str, object]:
    return {
        "tag": tag,
        "reason": reason,
        "age_seconds": age_seconds,
        "admin_url": reverse("admin:runtime_runtimetag_change", args=[tag.id]),
    }


def interface_runtime_tags():
    return (
        RuntimeTag.objects.select_related("latest_value", "schedule")
        .filter(enabled=True)
        .exclude(category=RuntimeTag.Category.TRACE_STRESS)
        .order_by("asset_name", "display_name")
    )


def excluded_interface_runtime_tag_count() -> int:
    return RuntimeTag.objects.filter(enabled=True, category=RuntimeTag.Category.TRACE_STRESS).count()


def dashboard_runtime_state(tags) -> dict[str, object]:
    now = timezone.now()
    stale_after_seconds = settings.STALE_AFTER_SECONDS
    stale_count = 0
    bad_quality_count = 0
    online_count = 0
    last_read_at = None
    stale_tag_items = []

    for tag in tags:
        value = getattr(tag, "latest_value", None)
        if value is None:
            stale_count += 1
            stale_tag_items.append(stale_tag_item(tag, "No read recorded", None))
            continue
        if last_read_at is None or value.read_at > last_read_at:
            last_read_at = value.read_at
        if value.quality_code.lower() != "good":
            bad_quality_count += 1
            stale_count += 1
            stale_tag_items.append(stale_tag_item(tag, "Bad quality: %s" % value.quality_code, 0))
            continue
        if value.is_stale(now, stale_after_seconds):
            stale_count += 1
            stale_tag_items.append(
                stale_tag_item(
                    tag,
                    "Last read older than %ss" % stale_after_seconds,
                    int((now - value.read_at).total_seconds()),
                )
            )
        else:
            online_count += 1

    return {
        "online_count": online_count,
        "stale_count": stale_count,
        "bad_quality_count": bad_quality_count,
        "stale_after_seconds": stale_after_seconds,
        "tag_count": len(tags),
        "last_read_at": last_read_at,
        "stale_tag_items": stale_tag_items,
    }


def dashboard_readiness(state: dict[str, object]) -> list[ReadinessItem]:
    tag_count = state["tag_count"]
    online_count = state["online_count"]
    stale_count = state["stale_count"]
    bad_quality_count = state["bad_quality_count"]
    enabled_field_endpoints = FieldEndpoint.objects.filter(enabled=True).count()
    enabled_field_tags = FieldTag.objects.filter(enabled=True, device__endpoint__enabled=True).count()
    field_agent_online = port_is_open("localhost", 4840)

    return [
        ReadinessItem(
            "Runtime config",
            "ok" if tag_count else "error",
            "%s runtime tags configured" % tag_count,
            "Configure tags" if not tag_count else "",
            "/admin/runtime/runtimetag/" if not tag_count else "",
        ),
        ReadinessItem(
            "Latest reads",
            "ok" if online_count and not stale_count and not bad_quality_count else "warning" if online_count else "error",
            "%s online, %s stale, %s bad quality" % (online_count, stale_count, bad_quality_count),
            "Live view",
            "/live/",
        ),
        ReadinessItem(
            "FieldAgent",
            "ok" if field_agent_online else "error",
            "OPC UA port 4840 is %s; %s enabled field tags"
            % ("listening" if field_agent_online else "not listening", enabled_field_tags),
            "Field config",
            "/field/config.json",
        ),
        ReadinessItem(
            "Field config",
            "ok" if enabled_field_endpoints and enabled_field_tags else "warning",
            "%s enabled endpoints, %s enabled tags" % (enabled_field_endpoints, enabled_field_tags),
            "Sim setup",
            "/sim/",
        ),
    ]


def field_device_status() -> dict[str, object]:
    endpoints = list(FieldEndpoint.objects.prefetch_related("devices__tags", "heartbeats").order_by("name"))
    now = timezone.now()
    endpoint_items = []
    enabled_endpoint_count = 0
    running_endpoint_count = 0
    enabled_device_count = 0
    enabled_tag_count = 0
    latest_seen_at = None

    for endpoint in endpoints:
        devices = list(endpoint.devices.all())
        heartbeats = list(endpoint.heartbeats.all())
        latest_heartbeat = max((heartbeat.last_seen_at for heartbeat in heartbeats), default=None)
        seen_at = endpoint.last_seen_at or latest_heartbeat
        if seen_at is not None and (latest_seen_at is None or seen_at > latest_seen_at):
            latest_seen_at = seen_at
        if endpoint.enabled:
            enabled_endpoint_count += 1
        if endpoint.enabled and endpoint.status == FieldEndpoint.Status.RUNNING:
            running_endpoint_count += 1
        endpoint_enabled_devices = [device for device in devices if device.enabled]
        endpoint_enabled_tag_count = sum(tag.enabled for device in endpoint_enabled_devices for tag in device.tags.all())
        enabled_device_count += len(endpoint_enabled_devices)
        enabled_tag_count += endpoint_enabled_tag_count
        age_seconds = int((now - seen_at).total_seconds()) if seen_at else None
        endpoint_items.append(
            {
                "endpoint": endpoint,
                "enabled_device_count": len(endpoint_enabled_devices),
                "enabled_tag_count": endpoint_enabled_tag_count,
                "latest_seen_at": seen_at,
                "age_seconds": age_seconds,
                "online": endpoint.enabled and endpoint.status == FieldEndpoint.Status.RUNNING,
            }
        )

    return {
        "endpoint_count": len(endpoints),
        "enabled_endpoint_count": enabled_endpoint_count,
        "running_endpoint_count": running_endpoint_count,
        "enabled_device_count": enabled_device_count,
        "enabled_tag_count": enabled_tag_count,
        "latest_seen_at": latest_seen_at,
        "endpoint_items": endpoint_items,
    }


def refresh_runtime_tags(tags: list[RuntimeTag]) -> int:
    if not tags:
        return 0
    fx = fluxy_client()
    values = fx.tag.read_blocking([tag.full_path for tag in tags])
    now = timezone.now()
    for tag, value in zip(tags, values, strict=True):
        value_timestamp = parse_fluxy_timestamp(value.timestamp) or now
        LatestTagValue.objects.update_or_create(
            tag=tag,
            defaults={
                "value": value.value,
                "quality_code": value.quality,
                "value_timestamp": value_timestamp,
                "read_at": now,
            },
        )
        TagSample.objects.create(
            tag=tag,
            value=value.value,
            quality_code=value.quality,
            value_timestamp=value_timestamp,
            read_at=now,
        )
    return len(tags)
