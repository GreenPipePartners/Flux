from __future__ import annotations

import os
import socket
from dataclasses import dataclass

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from flux.base.models import FieldEndpoint, FieldTag
from flux.base.runtime import RuntimeTag
from flux.opt.services import sample_runtime_tags
from flux.serve.models import ServeHeartbeat, ServeServiceSnapshot
from flux.serve.monitor import service_snapshot_status
from flux.serve.server_commands import request_sim_server_start, request_sim_server_stop
from flux.serve.status import runtime_read_status, serve_heartbeat_status
from flux.trace.models import TraceProfile, TraceSignal

from .models import IgnitionBridgeConfig


@dataclass(frozen=True)
class ReadinessItem:
    label: str
    state: str
    detail: str
    action_label: str = ""
    action_url: str = ""
    detail_lines: tuple[str, ...] = ()
    copy_docs_url: str = ""
    copy_table_markdown: str = ""
    copy_llm_markdown: str = ""


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


def test_bridge(config: IgnitionBridgeConfig | None = None) -> IgnitionBridgeConfig:
    config = config or bridge_config()
    try:
        version = fluxy_client(config).util.get_version(refresh=True)
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
        status = runtime_read_status(value, now=now, stale_after_seconds=stale_after_seconds)
        if status.bad_quality:
            bad_quality_count += 1
        if status.stale:
            stale_count += 1
            stale_tag_items.append(stale_tag_item(tag, status.reason, status.age_seconds))
        if status.online:
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


def dashboard_readiness(state: dict[str, object], serve_state: dict[str, object] | None = None) -> list[ReadinessItem]:
    online_count = state["online_count"]
    stale_count = state["stale_count"]
    bad_quality_count = state["bad_quality_count"]
    enabled_field_endpoints = FieldEndpoint.objects.filter(enabled=True).count()
    enabled_field_tags = FieldTag.objects.filter(enabled=True, device__endpoint__enabled=True).count()
    sim_config_ok = bool(enabled_field_endpoints and enabled_field_tags)
    trace_chart_count = TraceProfile.objects.filter(enabled=True).count()
    trace_signal_count = TraceSignal.objects.filter(profile__enabled=True).count()
    mine_counts = flux_mine_counts()
    build_counts = flux_build_counts()

    readiness = [
        ReadinessItem(
            "Flux.mine",
            "ok" if mine_counts["plc_count"] or mine_counts["hmi_count"] else "warning",
            "%s PLCs Mined, %s HMI's mined" % (mine_counts["plc_count"], mine_counts["hmi_count"]),
            "Mine sources",
            "",
            (
                "%s PLCs Mined" % mine_counts["plc_count"],
                "%s HMI's mined" % mine_counts["hmi_count"],
            ),
        ),
        ReadinessItem(
            "Flux.build",
            "ok" if build_counts["cell_count"] else "warning",
            "%s cells built" % build_counts["cell_count"],
            "Build cells",
            "",
            ("%s cells built" % build_counts["cell_count"],),
        ),
        ReadinessItem(
            "Flux.sim",
            "ok" if sim_config_ok else "error",
            "%s OPC Servers, %s Tags" % (enabled_field_endpoints, enabled_field_tags),
            "Sim setup",
            "/sim/",
            (
                "%s OPC Servers" % enabled_field_endpoints,
                "%s Tags" % enabled_field_tags,
            ),
        ),
        ReadinessItem(
            "Flux.live",
            "ok" if online_count and not stale_count and not bad_quality_count else "warning" if online_count else "error",
            "%s online, %s stale, %s bad" % (online_count, stale_count, bad_quality_count),
            "Live view",
            "/live/",
            (
                "%s online" % online_count,
                "%s stale" % stale_count,
                "%s bad" % bad_quality_count,
            ),
        ),
        ReadinessItem(
            "Flux.trace",
            "ok" if trace_chart_count else "warning",
            "%s charts, %s signals" % (trace_chart_count, trace_signal_count),
            "Trace charts",
            "/trace/",
            (
                "%s Charts" % trace_chart_count,
                "%s Signals" % trace_signal_count,
            ),
        ),
    ]
    if serve_state is not None:
        if serve_state.get("source") == "snapshots":
            detail = "%s healthy, %s warning, %s error" % (
                serve_state["ok_count"],
                serve_state["warning_count"],
                serve_state["error_count"],
            )
            detail_lines = (
                "%s healthy" % serve_state["ok_count"],
                "%s warning" % serve_state["warning_count"],
                "%s error" % serve_state["error_count"],
            )
        else:
            detail = "%s running, %s stale, %s error" % (
                serve_state["running_count"],
                serve_state["stale_count"],
                serve_state["error_count"],
            )
            detail_lines = (
                "%s running" % serve_state["running_count"],
                "%s stale" % serve_state["stale_count"],
                "%s error" % serve_state["error_count"],
            )
        readiness.append(
            ReadinessItem(
                "Flux.serve",
                serve_state["state"],
                detail,
                "Serve status",
                "/serve/",
                detail_lines,
            )
        )
    return readiness


def flux_mine_counts() -> dict[str, int]:
    return {"plc_count": 0, "hmi_count": 0}


def flux_build_counts() -> dict[str, int]:
    return {"cell_count": 0}


def ignition_bridge_status() -> dict[str, object]:
    configs = list(IgnitionBridgeConfig.objects.order_by("name"))
    connected_count = sum(1 for config in configs if config.last_test_ok)
    production_count = sum(1 for config in configs if config.role == IgnitionBridgeConfig.Role.PRODUCTION)
    simulator_count = sum(1 for config in configs if config.role == IgnitionBridgeConfig.Role.SIMULATOR)
    production_connected_count = sum(
        1 for config in configs if config.role == IgnitionBridgeConfig.Role.PRODUCTION and config.last_test_ok
    )
    simulator_connected_count = sum(
        1 for config in configs if config.role == IgnitionBridgeConfig.Role.SIMULATOR and config.last_test_ok
    )
    return {
        "state": "ok" if connected_count else "offline",
        "total_count": len(configs),
        "connected_count": connected_count,
        "production_count": production_count,
        "simulator_count": simulator_count,
        "production_connected_count": production_connected_count,
        "simulator_connected_count": simulator_connected_count,
        "configs": configs,
    }


def field_device_status() -> dict[str, object]:
    endpoints = list(FieldEndpoint.objects.prefetch_related("devices__tags", "heartbeats").order_by("name"))
    now = timezone.now()
    reconcile_field_agent_heartbeats(endpoints, now=now)
    endpoint_items = []
    enabled_endpoint_count = 0
    running_endpoint_count = 0
    enabled_device_count = 0
    enabled_tag_count = 0
    latest_seen_at = None
    refresh_endpoint_state = False

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
        if endpoint.enabled and endpoint.status == FieldEndpoint.Status.STARTING:
            refresh_endpoint_state = True
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
        "refresh_endpoint_state": refresh_endpoint_state,
        "endpoint_items": endpoint_items,
    }


def reconcile_field_agent_heartbeats(endpoints: list[FieldEndpoint], *, now) -> None:
    for endpoint in endpoints:
        if not endpoint.enabled:
            continue
        heartbeats = list(endpoint.heartbeats.all())
        live_heartbeat = None
        dead_heartbeat = None
        for heartbeat in heartbeats:
            if heartbeat.process_id and process_is_alive(heartbeat.process_id):
                live_heartbeat = heartbeat
                break
            if heartbeat.process_id:
                dead_heartbeat = heartbeat

        if live_heartbeat is not None:
            live_heartbeat.last_seen_at = now
            live_heartbeat.last_error = ""
            live_heartbeat.save(update_fields=["last_seen_at", "last_error"])
            if endpoint.status != FieldEndpoint.Status.RUNNING or endpoint.last_seen_at != now:
                endpoint.status = FieldEndpoint.Status.RUNNING
                endpoint.last_seen_at = now
                endpoint.last_error = ""
                endpoint.save(update_fields=["status", "last_seen_at", "last_error", "updated_at"])
            continue

        if dead_heartbeat is not None and endpoint.status in (FieldEndpoint.Status.STARTING, FieldEndpoint.Status.RUNNING):
            message = "FieldAgent process %s is no longer running" % dead_heartbeat.process_id
            dead_heartbeat.process_id = None
            dead_heartbeat.last_error = message
            dead_heartbeat.save(update_fields=["process_id", "last_error"])
            endpoint.status = FieldEndpoint.Status.ERROR
            endpoint.last_error = message
            endpoint.save(update_fields=["status", "last_error", "updated_at"])


def process_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def serve_status() -> dict[str, object]:
    snapshots = ServeServiceSnapshot.objects.order_by("category", "service_key")
    if snapshots.exists():
        return service_snapshot_status(snapshots, stale_after_seconds=settings.STALE_AFTER_SECONDS)
    return serve_heartbeat_status(
        ServeHeartbeat.objects.order_by("service_name", "instance_id"),
        stale_after_seconds=settings.STALE_AFTER_SECONDS,
    )


def start_sim_server(endpoint_id: int, *, requested_by=None) -> FieldEndpoint:
    request_sim_server_start(endpoint_id, requested_by=requested_by)
    return FieldEndpoint.objects.get(id=endpoint_id)


def stop_sim_server(endpoint_id: int, *, requested_by=None) -> FieldEndpoint:
    request_sim_server_stop(endpoint_id, requested_by=requested_by)
    return FieldEndpoint.objects.get(id=endpoint_id)


def refresh_runtime_tags(tags: list[RuntimeTag]) -> int:
    return sample_runtime_tags(tags, fx=fluxy_client())
