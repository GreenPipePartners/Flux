from __future__ import annotations

import json
import os
from pathlib import Path
import time

import pytest
from django.conf import settings
from django.utils import timezone

from flux.base.models import Tag
from flux.sim.models import FieldEndpoint
from flux.sim.models import TagProvider
from flux.base.services import import_provider_json_bytes
from flux.base.runtime import LatestTagValue, RuntimeTag, TagSample
from flux.field.ignition import cleanup_field_agent_ignition, configure_field_device_ignition, safe_name
from flux.spot.models import LiveScope
from flux.opt.services import sample_runtime_demand
from flux.plane import seed_plane_samples_from_runtime_history
from flux.sim.fluxolot_fishtank import (
    FLUXOLOT_LIVE_SCOPE,
    FLUXOLOT_TAG_FOLDER,
    FLUXOLOT_TAGS,
    FLUXOLOT_TRACE_SCOPE,
    cleanup_fluxolot_fishtank_ignition,
    configure_fluxolot_fishtank_ignition,
    ensure_fluxolot_fishtank,
    ensure_fluxolot_live_scope,
    ensure_fluxolot_trace_profiles,
)
from flux.sim.output import apply_selected_output, selected_output_plan
from flux.sim.provider_tree import replace_imported_selection
from flux.sim.models import DeviceConfig, TagConfig
from flux.sim.value_profiles import build_production_profile_map, materialize_profile_sim_device
from flux.serve.field_acceptance import (
    FieldAcceptanceSource,
    endpoint_port,
    public_endpoint_url,
    start_process_with_cert,
    stop_source_and_record_offline,
    stop_field_acceptance_source,
    wait_for_good_tag_reads,
    wait_for_opc_connected,
    wait_for_port,
)
from flux.serve.field_supervisor import process_spec
from flux.serve.status import runtime_read_status
from flux.trace.models import TraceProfile


pytestmark = [
    pytest.mark.acceptance,
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(
        os.getenv("FLUX_FULL_INTEGRATION") != "1",
        reason="Set FLUX_FULL_INTEGRATION=1 to run Fluxolot Fishtank full acceptance test",
    ),
]


LIVE_SCOPE = FLUXOLOT_LIVE_SCOPE
TRACE_SCOPE = FLUXOLOT_TRACE_SCOPE
SIM_PROVIDER = "flux-full-integration-fluxolot-fishtank"
SIM_DEVICE = "fluxolot-derived-profile"
SIM_IMPORTED_PROVIDER = "fluxolot-imported-selection-acceptance"
IGNITION_TAG_PROVIDER = "default"
IGNITION_TAG_FOLDER = "FluxolotFishtankAcceptance"
IGNITION_CONNECTION_NAMES = ["Fluxolot Sir Acceptance", "Fluxolot Missus Acceptance"]
FLUXOLOT_PROVIDER_EXPORT_FIXTURE = Path(__file__).resolve().parents[1] / "sim" / "fixtures" / "fluxolot_provider_export.json"


def test_full_fluxolot_fishtank_live_trace_sim_profile_and_cleanup(client, tmp_path):
    import fluxy

    repo_root = Path(__file__).resolve().parents[5]
    project_path = Path(
        os.getenv(
            "FLUX_FIELD_AGENT_PROJECT_PATH",
            str(repo_root / "field" / "Flux.FieldAgent" / "Flux.FieldAgent.csproj"),
        )
    )
    if not project_path.exists():
        pytest.skip("Flux.FieldAgent project is required for Fluxolot Fishtank full acceptance")

    result = ensure_fluxolot_fishtank(history_days=30, history_interval_minutes=1440)
    runtime_tags = retarget_runtime_tags(list(result.runtime_tags), IGNITION_TAG_FOLDER)
    numeric_tags = [tag for tag in runtime_tags if not isinstance(getattr(tag, "latest_value", None).value, bool)]
    assert len(result.endpoints) == 2
    assert len(runtime_tags) == 26
    assert fluxolot_history_spans_days(runtime_tags) >= 29

    ensure_fluxolot_live_scope(runtime_tags)
    profiles = ensure_fluxolot_trace_profiles(runtime_tags)
    for profile in profiles:
        seed_plane_samples_from_runtime_history(profile)

    fx = fluxy.Fluxy(
        base_url=os.getenv("FLUXY_BASE_URL", "http://localhost:8088/system/webdev/flux"),
        token=os.getenv("FLUXY_TOKEN"),
        project_location=os.getenv("FLUXY_PROJECT_LOCATION", str(repo_root / "web" / "ignition_flux_project")),
    )
    public_host = os.getenv("FLUX_FULL_INTEGRATION_HOST", "localhost")
    base_port = int(os.getenv("FLUX_FULL_INTEGRATION_BASE_PORT", "5060"))
    specs = [
        process_spec(
            endpoint,
            runtime_dir=tmp_path / "runtime",
            base_port=base_port,
            project_path=project_path,
            host=public_host,
        )
        for endpoint in result.endpoints
    ]
    sources: list[FieldAcceptanceSource | None] = []

    try:
        cleanup_fluxolot_fishtank_ignition(
            fx,
            tag_provider=IGNITION_TAG_PROVIDER,
            tag_folder=IGNITION_TAG_FOLDER,
            connection_names=IGNITION_CONNECTION_NAMES,
        )
        endpoint_urls = {}
        for index, spec in enumerate(specs):
            process = start_process_with_cert(spec, tmp_path / "pki" / spec.endpoint.name)
            wait_for_port(public_host, endpoint_port(spec.endpoint_url), timeout_seconds=float(os.getenv("FLUX_FULL_INTEGRATION_PORT_TIMEOUT_SECONDS", "30")))
            endpoint_urls[spec.endpoint.name] = public_endpoint_url(spec.endpoint_url, public_host)
            sources.append(
                FieldAcceptanceSource(
                    process=process,
                    connection_name=IGNITION_CONNECTION_NAMES[index],
                    tag_provider=IGNITION_TAG_PROVIDER,
                    tag_folder=IGNITION_TAG_FOLDER,
                )
            )
        configure_fluxolot_fishtank_ignition(
            fx,
            tag_provider=IGNITION_TAG_PROVIDER,
            tag_folder=IGNITION_TAG_FOLDER,
            endpoint_urls=endpoint_urls,
            connection_names=IGNITION_CONNECTION_NAMES,
            cleanup_existing=True,
        )
        for connection_name in IGNITION_CONNECTION_NAMES:
            wait_for_opc_connected(fx, connection_name, timeout_seconds=float(os.getenv("FLUX_FULL_INTEGRATION_CONNECT_TIMEOUT_SECONDS", "45")))

        live_reads = wait_for_good_tag_reads(
            fx,
            runtime_tags,
            timeout_seconds=float(os.getenv("FLUX_FULL_INTEGRATION_INITIAL_READ_TIMEOUT_SECONDS", "45")),
        )
        assert all("Good" in value.quality for value in live_reads.values())

        demand_report = sample_runtime_demand(tags=runtime_tags, fx=fx)
        assert demand_report.sampled_count == len(runtime_tags)
        assert demand_report.leased_count == len(runtime_tags)

        latest = sample_latest_values(runtime_tags)
        assert all(value.quality_code == "Good" for value in latest.values())

        live_page = client.get(f"/spot/{LIVE_SCOPE}/")
        live_cards = client.get(f"/spot/{LIVE_SCOPE}/cards/", {"group": "Tank"})
        assert live_page.status_code == 200
        assert live_cards.status_code == 200
        assert_contains(live_page, "Sir Fluxolot")
        assert_contains(live_page, "Missus Fluxolot")
        assert_contains(live_cards, "Temperature")
        assert_contains(live_cards, "Good")

        sir_tags = [tag for tag in runtime_tags if "/Sir-Fluxolot-Fishtank_" in tag.path]
        offline_probe = stop_source_and_record_offline(
            fx,
            sources[0],
            sir_tags,
            timeout_seconds=float(os.getenv("FLUX_FULL_INTEGRATION_OFFLINE_READ_TIMEOUT_SECONDS", "30")),
            allow_deterministic_fallback=os.getenv("FLUX_FULL_INTEGRATION_ALLOW_DETERMINISTIC_OFFLINE", "1") == "1",
        )
        sources[0] = None
        assert offline_probe.timed_out or all("Good" not in quality for quality in offline_probe.qualities.values())
        offline_latest = sample_latest_values(sir_tags)
        assert all(value.quality_code != "Good" for value in offline_latest.values())
        assert all(
            runtime_read_status(
                value,
                now=timezone.now(),
                stale_after_seconds=settings.STALE_AFTER_SECONDS,
            ).stale
            for value in offline_latest.values()
        )

        sir_trace_payload = trace_payload_for_scope(client, TRACE_SCOPE, set_index=1)
        missus_trace_payload = trace_payload_for_scope(client, TRACE_SCOPE, set_index=2)
        sir_trace_chart = sir_trace_payload["traceChart"]
        missus_trace_chart = missus_trace_payload["traceChart"]
        assert sir_trace_chart["profileKey"] == "fluxolot-sir"
        assert missus_trace_chart["profileKey"] == "fluxolot-missus"
        assert any("Sir Fluxolot" in series["name"] for series in sir_trace_chart["series"])
        assert any("Missus Fluxolot" in series["name"] for series in missus_trace_chart["series"])
        assert any(point is not None for series in sir_trace_chart["series"] for point in series["y"])
        assert any(point is not None for series in missus_trace_chart["series"] for point in series["y"])

        profile_map = build_production_profile_map(numeric_tags)
        assert profile_map
        sim_tags = materialize_profile_sim_device(
            provider_name=SIM_PROVIDER,
            device_name=SIM_DEVICE,
            runtime_tags=numeric_tags,
            profile_map=profile_map,
            source_fixture="Fluxolot Fishtank",
            driver_key="fluxolot-derived",
            driver_label="Fluxolot Derived",
        )
        assert sim_tags
        assert all(tag.mode_config["source_fixture"] == "Fluxolot Fishtank" for tag in sim_tags)
    finally:
        cleanup_fluxolot_fishtank_ignition(
            fx,
            tag_provider=IGNITION_TAG_PROVIDER,
            tag_folder=IGNITION_TAG_FOLDER,
            connection_names=IGNITION_CONNECTION_NAMES,
        )
        for source in sources:
            stop_field_acceptance_source(source)
        cleanup_disposable_resources()

    assert not LiveScope.objects.filter(slug=LIVE_SCOPE).exists()
    assert not TraceProfile.objects.filter(key__in=["fluxolot-sir", "fluxolot-missus"]).exists()
    assert not DeviceConfig.objects.filter(base_device__name=SIM_DEVICE).exists()
    assert DeviceConfig.objects.filter(base_device__name="Sir-Fluxolot-Fishtank").exists()


def test_full_fluxolot_imported_selection_materializes_reads_and_cleans_up(client, tmp_path):
    import fluxy

    repo_root = Path(__file__).resolve().parents[5]
    project_path = Path(
        os.getenv(
            "FLUX_FIELD_AGENT_PROJECT_PATH",
            str(repo_root / "field" / "Flux.FieldAgent" / "Flux.FieldAgent.csproj"),
        )
    )
    if not project_path.exists():
        pytest.skip("Flux.FieldAgent project is required for Fluxolot imported selection acceptance")

    payload = json.loads(FLUXOLOT_PROVIDER_EXPORT_FIXTURE.read_text(encoding="utf-8"))
    import_provider_json_bytes(
        json.dumps(payload).encode("utf-8"),
        provider_name=SIM_IMPORTED_PROVIDER,
        source_name=FLUXOLOT_PROVIDER_EXPORT_FIXTURE.name,
    )
    selected_branch = "Sir Fluxolot/Sir-Fluxolot-Fishtank"
    replace_imported_selection(SIM_IMPORTED_PROVIDER, [selected_branch])
    plan = selected_output_plan(SIM_IMPORTED_PROVIDER)
    assert plan.selected_count == len(FLUXOLOT_TAGS)
    assert plan.create_count == len(FLUXOLOT_TAGS)

    apply_result = apply_selected_output(
        SIM_IMPORTED_PROVIDER,
        mode_by_path={tag.path: "sin_range" for tag in plan.tags},
    )
    assert apply_result.created_count == len(FLUXOLOT_TAGS)
    field_device = DeviceConfig.objects.get(browse_path=SIM_IMPORTED_PROVIDER, base_device__name="Sir-Fluxolot-Fishtank")
    field_tags = list(field_device.tags.filter(enabled=True).order_by("tag_name"))
    assert len(field_tags) == len(FLUXOLOT_TAGS)
    assert all(tag.simulation_type == TagConfig.SimulationType.WAVE for tag in field_tags if tag.data_type != Tag.DataType.BOOL)

    fx = fluxy.Fluxy(
        base_url=os.getenv("FLUXY_BASE_URL", "http://localhost:8088/system/webdev/flux"),
        token=os.getenv("FLUXY_TOKEN"),
        project_location=os.getenv("FLUXY_PROJECT_LOCATION", str(repo_root / "web" / "ignition_flux_project")),
    )
    public_host = os.getenv("FLUX_FULL_INTEGRATION_HOST", "localhost")
    base_port = int(os.getenv("FLUX_FULL_INTEGRATION_BASE_PORT", "5060"))
    endpoint = FieldEndpoint.objects.get(name="Flux sim FluxolotOPC Server")
    spec = process_spec(
        endpoint,
        runtime_dir=tmp_path / "runtime",
        base_port=base_port,
        project_path=project_path,
        host=public_host,
    )
    source: FieldAcceptanceSource | None = None
    tag_folder = "FluxolotImportedSelection"
    connection_name = "Fluxolot Imported Selection Acceptance"
    try:
        process = start_process_with_cert(spec, tmp_path / "pki" / spec.endpoint.name)
        wait_for_port(public_host, endpoint_port(spec.endpoint_url), timeout_seconds=float(os.getenv("FLUX_FULL_INTEGRATION_PORT_TIMEOUT_SECONDS", "30")))
        public_url = public_endpoint_url(spec.endpoint_url, public_host)
        configure_field_device_ignition(
            fx,
            field_device,
            tag_provider=IGNITION_TAG_PROVIDER,
            tag_folder=tag_folder,
            endpoint_url=public_url,
            connection_name=connection_name,
            cleanup_existing=True,
        )
        source = FieldAcceptanceSource(process=process, connection_name=connection_name, tag_provider=IGNITION_TAG_PROVIDER, tag_folder=tag_folder)
        wait_for_opc_connected(fx, connection_name, timeout_seconds=float(os.getenv("FLUX_FULL_INTEGRATION_CONNECT_TIMEOUT_SECONDS", "45")))
        read_paths = [f"[{IGNITION_TAG_PROVIDER}]{tag_folder}/{safe_name(field_device.name)}_{safe_name(tag.name)}" for tag in field_tags]
        wait_for_good_paths(fx, read_paths, timeout_seconds=float(os.getenv("FLUX_FULL_INTEGRATION_INITIAL_READ_TIMEOUT_SECONDS", "45")))

        replace_imported_selection(SIM_IMPORTED_PROVIDER, [])
        cleanup_result = apply_selected_output(SIM_IMPORTED_PROVIDER)
        assert cleanup_result.disabled_count == len(field_tags)
        assert TagConfig.objects.filter(sim_device=field_device, enabled=True).count() == 0
    finally:
        cleanup_field_agent_ignition(
            fx,
            tag_provider=IGNITION_TAG_PROVIDER,
            tag_folder=tag_folder,
            connection_names=[connection_name],
        )
        stop_field_acceptance_source(source)
        TagProvider.objects.filter(name=SIM_IMPORTED_PROVIDER).delete()


def sample_latest_values(runtime_tags):
    values = LatestTagValue.objects.filter(tag__in=runtime_tags).select_related("tag")
    return {value.tag_id: value for value in values}


def trace_payload_for_scope(client, scope: str, *, set_index: int) -> dict:
    preferred = client.get(f"/chart/{scope}/payload/", {"set": str(set_index)})
    assert preferred.status_code == 200
    return preferred.json()


def fluxolot_history_spans_days(runtime_tags) -> int:
    oldest = TagSample.objects.filter(tag__in=runtime_tags).order_by("read_at").first()
    newest = TagSample.objects.filter(tag__in=runtime_tags).order_by("-read_at").first()
    assert oldest is not None
    assert newest is not None
    return (newest.read_at.date() - oldest.read_at.date()).days


def assert_contains(response, text: str) -> None:
    assert text in response.content.decode("utf-8")


def wait_for_good_paths(fx, full_paths: list[str], *, timeout_seconds: float = 45):
    deadline = time.monotonic() + timeout_seconds
    last_values = {}
    last_qualities = {}
    while time.monotonic() < deadline:
        values = fx.tag.read_blocking(full_paths)
        last_values = {path: value.value for path, value in zip(full_paths, values, strict=True)}
        last_qualities = {path: value.quality for path, value in zip(full_paths, values, strict=True)}
        if all("Good" in value.quality for value in values):
            return dict(zip(full_paths, values, strict=True))
        time.sleep(0.5)
    raise TimeoutError("Tags did not all read Good; values=%r qualities=%r" % (last_values, last_qualities))


def cleanup_disposable_resources() -> None:
    LiveScope.objects.filter(slug=LIVE_SCOPE).delete()
    TraceProfile.objects.filter(key__in=["fluxolot-sir", "fluxolot-missus"]).delete()
    TagProvider.objects.filter(name=SIM_PROVIDER).delete()
    RuntimeTag.objects.filter(path__startswith=f"{IGNITION_TAG_FOLDER}/").delete()


def retarget_runtime_tags(runtime_tags: list[RuntimeTag], tag_folder: str) -> list[RuntimeTag]:
    RuntimeTag.objects.filter(path__startswith=f"{tag_folder}/").exclude(id__in=[tag.id for tag in runtime_tags]).delete()
    for tag in runtime_tags:
        tag.path = tag.path.replace(f"{FLUXOLOT_TAG_FOLDER}/", f"{tag_folder}/", 1)
        tag.save(update_fields=["path"])
    return runtime_tags
