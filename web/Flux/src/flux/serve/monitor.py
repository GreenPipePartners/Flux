from __future__ import annotations

import socket
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from django.utils import timezone

from flux.base.models import FieldEndpoint

from .models import ServeHeartbeat, ServeServiceSnapshot


@dataclass(frozen=True)
class ServiceProbeResult:
    service_key: str
    display_name: str
    category: str
    desired_state: str
    observed_state: str
    severity: str
    summary: str
    detail: str = ""
    last_error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ServiceDefinition:
    service_key: str
    display_name: str
    category: str
    desired_state: str
    probe_kind: str
    probe_config: dict[str, Any] = field(default_factory=dict)
    dynamic: bool = False


@dataclass(frozen=True)
class MonitorOptions:
    web_url: str = "http://localhost:8000/"
    docs_url: str = "http://localhost:8001/"
    questdb_host: str = "localhost"
    questdb_http_port: int = 9000
    questdb_pg_port: int = 8812
    timeout_seconds: float = 1.0
    include_network: bool = True
    stale_after_seconds: int = 120


class ProbeKind:
    SELF = "self"
    HEARTBEAT = "heartbeat"
    FIELD_AGENT = "field_agent"
    HTTP = "http"
    QUESTDB = "questdb"
    BRIDGE = "bridge"


def refresh_service_snapshots(*, monitor_service_name: str = "flux-serve-monitor", options: MonitorOptions | None = None) -> dict[str, Any]:
    options = options or MonitorOptions()
    now = timezone.now()
    definitions = service_catalog(options=options, monitor_service_name=monitor_service_name)
    results = [probe_service(definition, now=now, options=options) for definition in definitions]
    current_keys = {result.service_key for result in results}
    snapshots = [upsert_snapshot(result, now=now) for result in results]
    snapshots.extend(retire_absent_dynamic_snapshots(current_keys, now=now))
    return service_snapshot_status(snapshots, now=now, stale_after_seconds=options.stale_after_seconds)


def service_catalog(*, options: MonitorOptions, monitor_service_name: str = "flux-serve-monitor") -> list[ServiceDefinition]:
    definitions = static_service_definitions(options=options, monitor_service_name=monitor_service_name)
    definitions.extend(field_agent_definitions())
    definitions.extend(bridge_definitions())
    return definitions


def static_service_definitions(*, options: MonitorOptions, monitor_service_name: str) -> list[ServiceDefinition]:
    definitions = [
        ServiceDefinition(
            "Flux.serve.monitor",
            "Flux Serve Monitor",
            "Control plane",
            ServeServiceSnapshot.DesiredState.REQUIRED,
            ProbeKind.SELF,
            {"heartbeat_service_name": monitor_service_name},
        ),
        ServiceDefinition(
            "Flux.serve.field-supervisor",
            "Flux Field Supervisor",
            "Control plane",
            ServeServiceSnapshot.DesiredState.REQUIRED,
            ProbeKind.HEARTBEAT,
            {"heartbeat_service_name": "flux-field-supervisor"},
        ),
        ServiceDefinition(
            "Flux.live.fluxolot-sampler",
            "Fluxolot Live Sampler",
            "Live proof",
            ServeServiceSnapshot.DesiredState.EXPECTED,
            ProbeKind.HEARTBEAT,
            {"heartbeat_service_name": "fluxolot-live-sampler"},
        ),
        ServiceDefinition(
            "Flux.opt.sampler",
            "Flux Opt Sampler",
            "Workers",
            ServeServiceSnapshot.DesiredState.OPTIONAL,
            ProbeKind.HEARTBEAT,
            {"heartbeat_service_name": "flux-sampling-worker"},
        ),
        ServiceDefinition(
            "Flux.trace.worker",
            "Flux Trace Worker",
            "Workers",
            ServeServiceSnapshot.DesiredState.OPTIONAL,
            ProbeKind.HEARTBEAT,
            {"heartbeat_service_name": "flux-trace-worker"},
        ),
    ]
    if options.include_network:
        definitions.extend(
            [
                ServiceDefinition(
                    "Flux.web.server",
                    "Flux Web Server",
                    "Web",
                    ServeServiceSnapshot.DesiredState.REQUIRED,
                    ProbeKind.HTTP,
                    {"url": options.web_url},
                ),
                ServiceDefinition(
                    "Flux.web.docs",
                    "Flux Web Docs",
                    "Web",
                    ServeServiceSnapshot.DesiredState.EXPECTED,
                    ProbeKind.HTTP,
                    {"url": options.docs_url},
                ),
                ServiceDefinition(
                    "Flux.plane.qdb",
                    "Flux Plane QuestDB",
                    "Data plane",
                    ServeServiceSnapshot.DesiredState.EXTERNAL,
                    ProbeKind.QUESTDB,
                    {},
                ),
            ]
        )
    else:
        definitions.extend(
            [
                skipped_definition("Flux.web.server", "Flux Web Server", "Web", ServeServiceSnapshot.DesiredState.REQUIRED, options.web_url),
                skipped_definition("Flux.web.docs", "Flux Web Docs", "Web", ServeServiceSnapshot.DesiredState.EXPECTED, options.docs_url),
                skipped_definition("Flux.plane.qdb", "Flux Plane QuestDB", "Data plane", ServeServiceSnapshot.DesiredState.EXTERNAL, options.questdb_host),
            ]
        )
    return definitions


def skipped_definition(service_key: str, display_name: str, category: str, desired_state: str, target: str) -> ServiceDefinition:
    return ServiceDefinition(
        service_key,
        display_name,
        category,
        desired_state,
        "skipped",
        {"target": target},
    )


def field_agent_definitions() -> list[ServiceDefinition]:
    endpoints = (
        FieldEndpoint.objects.prefetch_related("devices", "heartbeats")
        .filter(enabled=True, devices__enabled=True)
        .distinct()
        .order_by("name")
    )
    return [
        ServiceDefinition(
            service_key="Flux.serve.field-agent:%s" % endpoint.name,
            display_name="FieldAgent %s" % endpoint.name,
            category="Field runtime",
            desired_state=ServeServiceSnapshot.DesiredState.REQUIRED,
            probe_kind=ProbeKind.FIELD_AGENT,
            probe_config={"endpoint": endpoint},
            dynamic=True,
        )
        for endpoint in endpoints
    ]


def bridge_definitions() -> list[ServiceDefinition]:
    try:
        from dashboard.models import IgnitionBridgeConfig
    except Exception:
        return []
    return [
        ServiceDefinition(
            service_key="Flux.bridge:%s" % config.name,
            display_name="Flux Bridge %s" % config.name,
            category="External dependencies",
            desired_state=ServeServiceSnapshot.DesiredState.EXTERNAL,
            probe_kind=ProbeKind.BRIDGE,
            probe_config={"config": config},
            dynamic=True,
        )
        for config in IgnitionBridgeConfig.objects.order_by("name")
    ]


def probe_service(definition: ServiceDefinition, *, now, options: MonitorOptions) -> ServiceProbeResult:
    if definition.probe_kind == ProbeKind.SELF:
        return monitor_self_result(definition)
    if definition.probe_kind == ProbeKind.HEARTBEAT:
        return heartbeat_result(definition, now=now, stale_after_seconds=options.stale_after_seconds)
    if definition.probe_kind == ProbeKind.FIELD_AGENT:
        return field_agent_result(definition, now=now, stale_after_seconds=options.stale_after_seconds)
    if definition.probe_kind == ProbeKind.HTTP:
        return http_result(definition=definition, timeout_seconds=options.timeout_seconds)
    if definition.probe_kind == ProbeKind.QUESTDB:
        return questdb_result(definition, options)
    if definition.probe_kind == ProbeKind.BRIDGE:
        return bridge_result(definition)
    return skipped_result(definition)


def monitor_self_result(definition: ServiceDefinition) -> ServiceProbeResult:
    return ServiceProbeResult(
        service_key=definition.service_key,
        display_name=definition.display_name,
        category=definition.category,
        desired_state=definition.desired_state,
        observed_state=ServeServiceSnapshot.ObservedState.HEALTHY,
        severity=ServeServiceSnapshot.Severity.OK,
        summary="Monitor loop is writing service snapshots.",
        metadata={"heartbeat_service_name": definition.probe_config.get("heartbeat_service_name")},
    )


def heartbeat_result(definition: ServiceDefinition, *, now, stale_after_seconds: int) -> ServiceProbeResult:
    heartbeat_service_name = definition.probe_config["heartbeat_service_name"]
    heartbeat = latest_heartbeat(heartbeat_service_name)
    metadata = {"heartbeat_service_name": heartbeat_service_name}
    if heartbeat is None:
        severity = missing_severity(definition.desired_state)
        return ServiceProbeResult(
            service_key=definition.service_key,
            display_name=definition.display_name,
            category=definition.category,
            desired_state=definition.desired_state,
            observed_state=ServeServiceSnapshot.ObservedState.MISSING,
            severity=severity,
            summary="No heartbeat has been recorded.",
            metadata=metadata,
        )
    age_seconds = int((now - heartbeat.last_seen_at).total_seconds()) if heartbeat.last_seen_at else None
    metadata.update(
        {
            "heartbeat_id": heartbeat.id,
            "instance_id": heartbeat.instance_id,
            "status": heartbeat.status,
            "age_seconds": age_seconds,
        }
    )
    if heartbeat.status == ServeHeartbeat.Status.ERROR:
        return ServiceProbeResult(
            service_key=definition.service_key,
            display_name=definition.display_name,
            category=definition.category,
            desired_state=definition.desired_state,
            observed_state=ServeServiceSnapshot.ObservedState.ERROR,
            severity=ServeServiceSnapshot.Severity.ERROR,
            summary="Heartbeat reports error.",
            detail=heartbeat.current_job,
            last_error=heartbeat.last_error,
            metadata=metadata,
        )
    if age_seconds is None or age_seconds > stale_after_seconds:
        return ServiceProbeResult(
            service_key=definition.service_key,
            display_name=definition.display_name,
            category=definition.category,
            desired_state=definition.desired_state,
            observed_state=ServeServiceSnapshot.ObservedState.STALE,
            severity=ServeServiceSnapshot.Severity.WARNING,
            summary="Heartbeat is stale.",
            detail="Last seen age is %ss; stale threshold is %ss." % (age_seconds, stale_after_seconds),
            metadata=metadata,
        )
    if heartbeat.status == ServeHeartbeat.Status.RUNNING:
        return ServiceProbeResult(
            service_key=definition.service_key,
            display_name=definition.display_name,
            category=definition.category,
            desired_state=definition.desired_state,
            observed_state=ServeServiceSnapshot.ObservedState.HEALTHY,
            severity=ServeServiceSnapshot.Severity.OK,
            summary="Fresh running heartbeat.",
            detail=heartbeat.current_job,
            metadata=metadata,
        )
    return ServiceProbeResult(
        service_key=definition.service_key,
        display_name=definition.display_name,
        category=definition.category,
        desired_state=definition.desired_state,
        observed_state=ServeServiceSnapshot.ObservedState.DEGRADED,
        severity=ServeServiceSnapshot.Severity.WARNING,
        summary="Heartbeat is fresh but not running.",
        detail=heartbeat.current_job,
        metadata=metadata,
    )


def field_agent_result(definition: ServiceDefinition, *, now, stale_after_seconds: int) -> ServiceProbeResult:
    endpoint = definition.probe_config["endpoint"]
    heartbeat = endpoint.heartbeats.order_by("-last_seen_at").first()
    metadata = {"endpoint_id": endpoint.id, "endpoint_name": endpoint.name, "endpoint_status": endpoint.status}
    if heartbeat is None:
        return ServiceProbeResult(
            service_key=definition.service_key,
            display_name=definition.display_name,
            category=definition.category,
            desired_state=definition.desired_state,
            observed_state=ServeServiceSnapshot.ObservedState.MISSING,
            severity=ServeServiceSnapshot.Severity.ERROR,
            summary="Enabled endpoint has no FieldAgent heartbeat.",
            metadata=metadata,
        )
    age_seconds = int((now - heartbeat.last_seen_at).total_seconds()) if heartbeat.last_seen_at else None
    metadata.update({"heartbeat_id": heartbeat.id, "instance_id": heartbeat.instance_id, "age_seconds": age_seconds})
    if endpoint.status == FieldEndpoint.Status.ERROR or heartbeat.last_error:
        return ServiceProbeResult(
            service_key=definition.service_key,
            display_name=definition.display_name,
            category=definition.category,
            desired_state=definition.desired_state,
            observed_state=ServeServiceSnapshot.ObservedState.ERROR,
            severity=ServeServiceSnapshot.Severity.ERROR,
            summary="FieldAgent reports an error.",
            last_error=heartbeat.last_error or endpoint.last_error,
            metadata=metadata,
        )
    if age_seconds is None or age_seconds > stale_after_seconds:
        return ServiceProbeResult(
            service_key=definition.service_key,
            display_name=definition.display_name,
            category=definition.category,
            desired_state=definition.desired_state,
            observed_state=ServeServiceSnapshot.ObservedState.STALE,
            severity=ServeServiceSnapshot.Severity.WARNING,
            summary="FieldAgent heartbeat is stale.",
            detail="Last seen age is %ss; stale threshold is %ss." % (age_seconds, stale_after_seconds),
            metadata=metadata,
        )
    return ServiceProbeResult(
        service_key=definition.service_key,
        display_name=definition.display_name,
        category=definition.category,
        desired_state=definition.desired_state,
        observed_state=ServeServiceSnapshot.ObservedState.HEALTHY,
        severity=ServeServiceSnapshot.Severity.OK,
        summary="FieldAgent heartbeat is fresh.",
        metadata=metadata,
    )


def skipped_result(definition: ServiceDefinition) -> ServiceProbeResult:
    return ServiceProbeResult(
        service_key=definition.service_key,
        display_name=definition.display_name,
        category=definition.category,
        desired_state=definition.desired_state,
        observed_state=ServeServiceSnapshot.ObservedState.UNKNOWN,
        severity=ServeServiceSnapshot.Severity.UNKNOWN,
        summary="Network probe skipped." if definition.probe_kind == "skipped" else "No probe registered.",
        metadata={"probe": definition.probe_kind, **definition.probe_config},
    )


def bridge_result(definition: ServiceDefinition) -> ServiceProbeResult:
    config = definition.probe_config["config"]
    metadata = {
        "bridge_id": config.id,
        "bridge_name": config.name,
        "role": config.role,
        "base_url": config.base_url,
        "last_test_at": config.last_test_at.isoformat() if config.last_test_at else None,
        "token_set": bool(config.token),
        "probe": "stored_bridge_test",
    }
    if config.last_test_ok:
        return ServiceProbeResult(
            service_key=definition.service_key,
            display_name=definition.display_name,
            category=definition.category,
            desired_state=definition.desired_state,
            observed_state=ServeServiceSnapshot.ObservedState.HEALTHY,
            severity=ServeServiceSnapshot.Severity.OK,
            summary=config.last_test_message or "Bridge test is healthy.",
            metadata=metadata,
        )
    return ServiceProbeResult(
        service_key=definition.service_key,
        display_name=definition.display_name,
        category=definition.category,
        desired_state=definition.desired_state,
        observed_state=ServeServiceSnapshot.ObservedState.DEGRADED if config.last_test_at else ServeServiceSnapshot.ObservedState.UNKNOWN,
        severity=ServeServiceSnapshot.Severity.WARNING,
        summary=config.last_test_message or "Bridge has not been tested.",
        metadata=metadata,
    )


def http_result(*, definition: ServiceDefinition, timeout_seconds: float) -> ServiceProbeResult:
    url = definition.probe_config["url"]
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            status_code = response.status
    except (OSError, urllib.error.URLError) as exc:
        return ServiceProbeResult(
            service_key=definition.service_key,
            display_name=definition.display_name,
            category=definition.category,
            desired_state=definition.desired_state,
            observed_state=ServeServiceSnapshot.ObservedState.MISSING,
            severity=missing_severity(definition.desired_state),
            summary="HTTP probe failed.",
            last_error=str(exc),
            metadata={"url": url, "probe": "http"},
        )
    observed = ServeServiceSnapshot.ObservedState.HEALTHY if 200 <= status_code < 400 else ServeServiceSnapshot.ObservedState.DEGRADED
    severity = ServeServiceSnapshot.Severity.OK if observed == ServeServiceSnapshot.ObservedState.HEALTHY else ServeServiceSnapshot.Severity.WARNING
    return ServiceProbeResult(
        service_key=definition.service_key,
        display_name=definition.display_name,
        category=definition.category,
        desired_state=definition.desired_state,
        observed_state=observed,
        severity=severity,
        summary="HTTP %s" % status_code,
        metadata={"url": url, "probe": "http", "status_code": status_code},
    )


def questdb_result(definition: ServiceDefinition, options: MonitorOptions) -> ServiceProbeResult:
    http_ok, http_error = tcp_available(options.questdb_host, options.questdb_http_port, timeout_seconds=options.timeout_seconds)
    pg_ok, pg_error = tcp_available(options.questdb_host, options.questdb_pg_port, timeout_seconds=options.timeout_seconds)
    metadata = {
        "host": options.questdb_host,
        "http_port": options.questdb_http_port,
        "pg_port": options.questdb_pg_port,
        "http_ok": http_ok,
        "pg_ok": pg_ok,
        "probe": "tcp",
    }
    if http_ok and pg_ok:
        return ServiceProbeResult(
            service_key=definition.service_key,
            display_name=definition.display_name,
            category=definition.category,
            desired_state=definition.desired_state,
            observed_state=ServeServiceSnapshot.ObservedState.HEALTHY,
            severity=ServeServiceSnapshot.Severity.OK,
            summary="QuestDB HTTP and PG ports are reachable.",
            metadata=metadata,
        )
    if http_ok or pg_ok:
        return ServiceProbeResult(
            service_key=definition.service_key,
            display_name=definition.display_name,
            category=definition.category,
            desired_state=definition.desired_state,
            observed_state=ServeServiceSnapshot.ObservedState.DEGRADED,
            severity=ServeServiceSnapshot.Severity.WARNING,
            summary="QuestDB is partially reachable.",
            last_error="http=%s pg=%s" % (http_error or "ok", pg_error or "ok"),
            metadata=metadata,
        )
    return ServiceProbeResult(
        service_key=definition.service_key,
        display_name=definition.display_name,
        category=definition.category,
        desired_state=definition.desired_state,
        observed_state=ServeServiceSnapshot.ObservedState.MISSING,
        severity=ServeServiceSnapshot.Severity.WARNING,
        summary="QuestDB ports are not reachable.",
        last_error="http=%s pg=%s" % (http_error, pg_error),
        metadata=metadata,
    )


def tcp_available(host: str, port: int, *, timeout_seconds: float) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return True, ""
    except OSError as exc:
        return False, str(exc)


def latest_heartbeat(service_name: str) -> ServeHeartbeat | None:
    return ServeHeartbeat.objects.filter(service_name=service_name).order_by("-last_seen_at", "-id").first()


def missing_severity(desired_state: str) -> str:
    if desired_state == ServeServiceSnapshot.DesiredState.REQUIRED:
        return ServeServiceSnapshot.Severity.ERROR
    if desired_state == ServeServiceSnapshot.DesiredState.OPTIONAL:
        return ServeServiceSnapshot.Severity.WARNING
    return ServeServiceSnapshot.Severity.WARNING


def upsert_snapshot(result: ServiceProbeResult, *, now) -> ServeServiceSnapshot:
    snapshot, _created = ServeServiceSnapshot.objects.update_or_create(
        service_key=result.service_key,
        defaults={
            "display_name": result.display_name,
            "category": result.category,
            "desired_state": result.desired_state,
            "observed_state": result.observed_state,
            "severity": result.severity,
            "last_checked_at": now,
            "summary": result.summary[:255],
            "detail": result.detail,
            "last_error": result.last_error,
            "metadata": result.metadata,
        },
    )
    return snapshot


def retire_absent_dynamic_snapshots(current_keys: set[str], *, now) -> list[ServeServiceSnapshot]:
    stale_snapshots = ServeServiceSnapshot.objects.filter(
        service_key__startswith="Flux.serve.field-agent:"
    ).exclude(service_key__in=current_keys)
    bridge_snapshots = ServeServiceSnapshot.objects.filter(service_key__startswith="Flux.bridge:").exclude(service_key__in=current_keys)
    retired = []
    for snapshot in list(stale_snapshots) + list(bridge_snapshots):
        snapshot.desired_state = ServeServiceSnapshot.DesiredState.DISABLED
        snapshot.observed_state = ServeServiceSnapshot.ObservedState.STOPPED
        snapshot.severity = ServeServiceSnapshot.Severity.OK
        snapshot.last_checked_at = now
        snapshot.summary = "Service is disabled or no longer configured."
        snapshot.detail = ""
        snapshot.last_error = ""
        snapshot.save(
            update_fields=[
                "desired_state",
                "observed_state",
                "severity",
                "last_checked_at",
                "summary",
                "detail",
                "last_error",
                "updated_at",
            ]
        )
        retired.append(snapshot)
    return retired


def service_snapshot_status(snapshots, *, now=None, stale_after_seconds: int = 120) -> dict[str, Any]:
    now = now or timezone.now()
    items = [snapshot_status_item(snapshot, now=now, stale_after_seconds=stale_after_seconds) for snapshot in snapshots]
    ok_count = sum(1 for item in items if item["severity"] == ServeServiceSnapshot.Severity.OK)
    warning_count = sum(1 for item in items if item["severity"] == ServeServiceSnapshot.Severity.WARNING)
    error_count = sum(1 for item in items if item["severity"] == ServeServiceSnapshot.Severity.ERROR)
    unknown_count = sum(1 for item in items if item["severity"] == ServeServiceSnapshot.Severity.UNKNOWN)
    stale_count = sum(1 for item in items if item["stale"])
    total_count = len(items)
    state = "ok" if total_count and ok_count == total_count else "error" if error_count else "warning" if warning_count or unknown_count else "unknown"
    return {
        "state": state,
        "total_count": total_count,
        "ok_count": ok_count,
        "warning_count": warning_count,
        "error_count": error_count,
        "unknown_count": unknown_count,
        "stale_count": stale_count,
        "items": items,
        "source": "snapshots",
    }


def snapshot_status_item(snapshot: ServeServiceSnapshot, *, now, stale_after_seconds: int) -> dict[str, Any]:
    age_seconds = int((now - snapshot.last_checked_at).total_seconds()) if snapshot.last_checked_at else None
    is_stale = age_seconds is None or age_seconds > stale_after_seconds
    severity = snapshot.severity
    observed_state = snapshot.observed_state
    summary = snapshot.summary
    if is_stale and snapshot.severity != ServeServiceSnapshot.Severity.ERROR:
        severity = ServeServiceSnapshot.Severity.WARNING
        observed_state = ServeServiceSnapshot.ObservedState.STALE
        summary = "Snapshot is stale; monitor has not refreshed this service within %ss." % stale_after_seconds
    return {
        "snapshot": snapshot,
        "service_key": snapshot.service_key,
        "display_name": snapshot.display_name,
        "category": snapshot.category,
        "desired_state": snapshot.desired_state,
        "observed_state": observed_state,
        "severity": severity,
        "last_checked_at": snapshot.last_checked_at,
        "age_seconds": age_seconds,
        "stale": is_stale,
        "summary": summary,
        "last_error": snapshot.last_error,
        "metadata": snapshot.metadata,
    }
