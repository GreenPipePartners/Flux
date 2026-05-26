from __future__ import annotations

import socket
from dataclasses import dataclass, field
from urllib.parse import urlparse

from django.conf import settings
from django.utils import timezone

from flux.base.field_selectors import enabled_runtime_totals, endpoint_runtime_counts
from flux.sim.models import FieldEndpoint
from flux.base.runtime import RuntimeTag
from flux.bridge.models import IgnitionBridgeConfig
from flux.bridge.services import fluxy_client
from flux.opt.services import sample_runtime_tags
from flux.serve.models import ServeHeartbeat, ServeServiceSnapshot
from flux.serve.monitor import service_snapshot_status
from flux.serve.server_commands import request_sim_server_start, request_sim_server_stop
from flux.serve.status import runtime_read_status, serve_heartbeat_status
from flux.trace.models import TraceProfile, TraceSignal

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
    meta: dict[str, object] = field(default_factory=dict)

def port_is_open(host: str, port: int, timeout: float = 0.15) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def stale_tag_item(tag: RuntimeTag, reason: str, age_seconds: int | None) -> dict[str, object]:
    legacy_source_missing = stale_reason_is_legacy_source_missing(reason)
    return {
        "tag": tag,
        "reason": reason,
        "age_seconds": age_seconds,
        "source_context": "[%s] %s" % (tag.provider, tag.get_category_display()),
        "legacy_source_missing": legacy_source_missing,
        "status_label": "legacy source missing" if legacy_source_missing else "stale",
    }


def stale_reason_is_legacy_source_missing(reason: str) -> bool:
    """Identify stale rows caused by old Flux Field provider references.

    These rows are preserved as runtime evidence, but the dashboard should not
    mix them into normal stale-refresh triage as if a current provider simply
    needs a retry.
    """

    normalized = reason.replace("\\\"", '"')
    return "Flux Field" in normalized and "does not exist" in normalized


def endpoint_url_parts(endpoint_url: str) -> dict[str, object]:
    try:
        parsed = urlparse(endpoint_url)
        port = parsed.port
    except ValueError:
        return {"host": "", "port": None}
    return {"host": parsed.hostname or "", "port": port}


def field_endpoint_observed_state(endpoint: FieldEndpoint, latest_heartbeat, age_seconds: int | None) -> str:
    stored = "last reported %s" % endpoint.status
    if not endpoint.enabled:
        return "disabled"
    if latest_heartbeat is None:
        return "%s · no heartbeat" % stored
    if age_seconds is None or age_seconds > settings.STALE_AFTER_SECONDS:
        return "%s · stale heartbeat" % stored
    if latest_heartbeat.last_error:
        return "%s · heartbeat error" % stored
    if endpoint.status != FieldEndpoint.Status.RUNNING:
        return "%s · fresh heartbeat" % stored
    return "reported running · fresh heartbeat"


def field_endpoint_has_fresh_running_evidence(endpoint: FieldEndpoint, latest_heartbeat, age_seconds: int | None) -> bool:
    return bool(
        endpoint.enabled
        and endpoint.status == FieldEndpoint.Status.RUNNING
        and latest_heartbeat is not None
        and not latest_heartbeat.last_error
        and age_seconds is not None
        and age_seconds <= settings.STALE_AFTER_SECONDS
    )


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
    sim_totals = enabled_runtime_totals()
    enabled_field_endpoints = sim_totals["endpoint_count"]
    enabled_field_tags = sim_totals["tag_count"]
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
            "/mine/",
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
            "/build/",
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
            "Flux.spot",
            "ok" if online_count and not stale_count and not bad_quality_count else "warning" if online_count else "error",
            "%s online, %s stale, %s bad" % (online_count, stale_count, bad_quality_count),
            "Spot view",
            "/spot/",
            (
                "%s online" % online_count,
                "%s stale" % stale_count,
                "%s bad" % bad_quality_count,
            ),
        ),
        ReadinessItem(
            "Flux.chart",
            "ok" if trace_chart_count else "warning",
            "%s charts, %s signals" % (trace_chart_count, trace_signal_count),
            "Charts",
            "/chart/",
            (
                "%s Charts" % trace_chart_count,
                "%s Signals" % trace_signal_count,
            ),
            meta={"chart_count": trace_chart_count, "signal_count": trace_signal_count},
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
    endpoints = list(FieldEndpoint.objects.prefetch_related("heartbeats").order_by("name"))
    runtime_counts = endpoint_runtime_counts({endpoint.id for endpoint in endpoints})
    now = timezone.now()
    endpoint_items = []
    enabled_endpoint_count = 0
    running_endpoint_count = 0
    enabled_device_count = 0
    enabled_tag_count = 0
    latest_seen_at = None
    refresh_endpoint_state = False

    for endpoint in endpoints:
        heartbeats = list(endpoint.heartbeats.all())
        latest_heartbeat = max(heartbeats, key=lambda heartbeat: heartbeat.last_seen_at, default=None)
        latest_heartbeat_at = latest_heartbeat.last_seen_at if latest_heartbeat else None
        seen_at = max((seen for seen in (endpoint.last_seen_at, latest_heartbeat_at) if seen), default=None)
        if seen_at is not None and (latest_seen_at is None or seen_at > latest_seen_at):
            latest_seen_at = seen_at
        if endpoint.enabled:
            enabled_endpoint_count += 1
        if endpoint.enabled and endpoint.status == FieldEndpoint.Status.STARTING:
            refresh_endpoint_state = True
        endpoint_counts = runtime_counts.get(endpoint.id, {"device_count": 0, "tag_count": 0})
        endpoint_enabled_device_count = endpoint_counts["device_count"]
        endpoint_enabled_tag_count = endpoint_counts["tag_count"]
        enabled_device_count += endpoint_enabled_device_count
        enabled_tag_count += endpoint_enabled_tag_count
        age_seconds = int((now - seen_at).total_seconds()) if seen_at else None
        heartbeat_age_seconds = int((now - latest_heartbeat_at).total_seconds()) if latest_heartbeat_at else None
        online = field_endpoint_has_fresh_running_evidence(endpoint, latest_heartbeat, heartbeat_age_seconds)
        if online:
            running_endpoint_count += 1
        endpoint_parts = endpoint_url_parts(endpoint.endpoint_url)
        endpoint_items.append(
            {
                "endpoint": endpoint,
                "enabled_device_count": endpoint_enabled_device_count,
                "enabled_tag_count": endpoint_enabled_tag_count,
                "latest_seen_at": seen_at,
                "latest_heartbeat": latest_heartbeat,
                "endpoint_host": endpoint_parts["host"],
                "endpoint_port": endpoint_parts["port"],
                "observed_state": field_endpoint_observed_state(endpoint, latest_heartbeat, heartbeat_age_seconds),
                "age_seconds": age_seconds,
                "heartbeat_age_seconds": heartbeat_age_seconds,
                "online": online,
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
