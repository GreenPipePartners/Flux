from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from flux.sim.models import TagNode
from flux.base.services import import_provider_from_fluxy, import_provider_json_bytes

from .engine import delete_tag_branch
from .models import SimJob
from .output import normalize_default_modes, save_provider_default_modes, selection_config_from_post
from .provider_tree import set_imported_selection
from .rehydrate import (
    apply_rehydration_plan,
    build_rehydration_plan,
    delete_rehydrated_paths,
    materialize_rehydration_backing,
)


def sim_job_input_dir() -> Path:
    path = settings.BASE_DIR.parents[1] / ".runtime" / "sim-jobs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_sim_job_input(content: bytes, *, suffix: str) -> Path:
    path = sim_job_input_dir() / f"{uuid4().hex}{suffix}"
    path.write_bytes(content)
    return path


def enqueue_import_provider_json(*, content: bytes, provider_name: str, source_name: str) -> SimJob:
    input_path = write_sim_job_input(content, suffix=".json")
    return SimJob.objects.create(
        kind=SimJob.Kind.IMPORT_PROVIDER_JSON,
        provider=provider_name,
        input_path=str(input_path),
        payload={"provider_name": provider_name, "source_name": source_name},
        progress_label="Queued JSON provider import",
    )


def enqueue_import_provider_ignition(*, source_provider: str, provider_name: str) -> SimJob:
    return SimJob.objects.create(
        kind=SimJob.Kind.IMPORT_PROVIDER_IGNITION,
        provider=provider_name,
        payload={"source_provider": source_provider, "provider_name": provider_name},
        progress_label="Queued Ignition provider import",
    )


def enqueue_remove_ignition_tags(*, provider: str, folder_path: str) -> SimJob:
    return SimJob.objects.create(
        kind=SimJob.Kind.REMOVE_IGNITION_TAGS,
        provider=provider,
        payload={"provider": provider, "folder_path": folder_path.strip("/")},
        progress_label="Queued Ignition tag removal",
    )


def enqueue_apply_selection(
    *,
    provider: str,
    selection_paths: list[str],
    selection_enabled: list[str],
    selection_modes: list[str],
    selection_configs: list[str],
    default_modes: dict[str, str],
    rehydrate: bool,
) -> SimJob:
    return SimJob.objects.create(
        kind=SimJob.Kind.APPLY_SELECTION,
        provider=provider,
        payload={
            "provider": provider,
            "selection_paths": selection_paths,
            "selection_enabled": selection_enabled,
            "selection_modes": selection_modes,
            "selection_configs": selection_configs,
            "default_modes": normalize_default_modes(default_modes),
            "rehydrate": rehydrate,
        },
        progress_total=len(selection_paths),
        progress_label="Queued simulator output apply",
    )


def claim_next_sim_job() -> SimJob | None:
    with transaction.atomic():
        job = (
            SimJob.objects.select_for_update()
            .filter(status=SimJob.Status.QUEUED)
            .order_by("created_at", "id")
            .first()
        )
        if job is None:
            return None
        job.mark_running()
        return job


def run_next_sim_job() -> str:
    job = claim_next_sim_job()
    if job is None:
        return "idle"
    try:
        result = execute_sim_job(job)
    except Exception as exc:
        fail_sim_job(job, error=str(exc))
        return f"job={job.id} failed: {exc}"
    complete_sim_job(job, result=result)
    return f"job={job.id} complete kind={job.kind}"


def execute_sim_job(job: SimJob) -> dict[str, Any]:
    if job.kind == SimJob.Kind.IMPORT_PROVIDER_JSON:
        return execute_import_provider_json(job)
    if job.kind == SimJob.Kind.IMPORT_PROVIDER_IGNITION:
        return execute_import_provider_ignition(job)
    if job.kind == SimJob.Kind.REMOVE_IGNITION_TAGS:
        return execute_remove_ignition_tags(job)
    if job.kind == SimJob.Kind.APPLY_SELECTION:
        return execute_apply_selection(job)
    raise ValueError(f"Unsupported sim job kind: {job.kind}")


def execute_import_provider_json(job: SimJob) -> dict[str, Any]:
    update_sim_job_progress(job, label="Reading provider JSON")
    content = Path(job.input_path).read_bytes()
    result = import_provider_json_bytes(
        content,
        provider_name=str(job.payload.get("provider_name") or job.provider),
        source_name=str(job.payload.get("source_name") or Path(job.input_path).name),
    )
    return {"provider": result.provider.name, "total_nodes": result.total_nodes, "counts": dict(result.counts)}


def execute_import_provider_ignition(job: SimJob) -> dict[str, Any]:
    source_provider = str(job.payload.get("source_provider") or "")
    provider_name = str(job.payload.get("provider_name") or source_provider)
    update_sim_job_progress(job, label=f"Exporting Ignition provider {source_provider}")
    result = import_provider_from_fluxy(
        fluxy_client(tag_provider=source_provider),
        source_provider=source_provider,
        provider_name=provider_name,
    )
    return {"provider": result.provider.name, "total_nodes": result.total_nodes, "counts": dict(result.counts)}


def execute_remove_ignition_tags(job: SimJob) -> dict[str, Any]:
    provider = str(job.payload.get("provider") or job.provider)
    folder_path = str(job.payload.get("folder_path") or "").strip("/")
    update_sim_job_progress(job, label=f"Deleting [{provider}]{folder_path}")
    deleted = delete_tag_branch(fluxy_client(tag_provider=provider), provider=provider, folder_path=folder_path)
    return {"provider": provider, "folder_path": folder_path, "deleted": deleted}


def execute_apply_selection(job: SimJob) -> dict[str, Any]:
    payload = job.payload
    provider = str(payload.get("provider") or job.provider)
    selection_paths = list(payload.get("selection_paths") or [])
    selection_enabled = list(payload.get("selection_enabled") or [])
    selection_modes = list(payload.get("selection_modes") or [])
    selection_configs = list(payload.get("selection_configs") or [])
    while len(selection_modes) < len(selection_paths):
        selection_modes.append("")
    while len(selection_configs) < len(selection_paths):
        selection_configs.append("")

    update_sim_job_progress(job, total=len(selection_paths), label="Saving simulator selections")
    default_modes = save_provider_default_modes(
        provider,
        normalize_default_modes(dict(payload.get("default_modes") or {})),
    )
    saved_count = 0
    for path, enabled, mode, raw_config in zip(
        selection_paths, selection_enabled, selection_modes, selection_configs, strict=False
    ):
        config = None
        if enabled == "1" and (mode or raw_config) and atomic_tag_path(provider, path):
            config = selection_config_from_post(mode, raw_config)
        set_imported_selection(provider, path, enabled=enabled == "1", config=config)
        saved_count += 1
    update_sim_job_progress(job, current=saved_count, label="Simulator selections saved")

    result: dict[str, Any] = {
        "provider": provider,
        "selection_count": saved_count,
        "default_modes": default_modes,
        "rehydrated_tags": 0,
        "backing_tags": 0,
        "deleted_tags": 0,
        "deleted_backing_tags": 0,
    }
    if not payload.get("rehydrate"):
        return result

    scoped_paths = submitted_rehydration_paths(selection_paths, selection_enabled)
    removed_paths = submitted_removed_paths(selection_paths, selection_enabled)
    client = None
    if removed_paths:
        update_sim_job_progress(job, label="Deleting deselected rehydrated branches")
        client = fluxy_client()
        deleted = delete_rehydrated_paths(client, provider=provider, paths=removed_paths)
        result["deleted_tags"] = deleted.tag_branch_count
        result["deleted_backing_tags"] = deleted.backing_tag_count

    if scoped_paths is None or scoped_paths:
        update_sim_job_progress(job, label="Materializing OPC backing tags")
        backing = materialize_rehydration_backing(provider, selected_paths=scoped_paths)
        update_sim_job_progress(job, label="Building rehydration plan")
        plan = build_rehydration_plan(provider, selected_paths=scoped_paths)
    else:
        backing = None
        plan = None

    if plan is not None:
        result["rehydrated_tags"] = plan.tag_count
        result["backing_tags"] = backing.tag_count if backing is not None else 0
    if plan is not None and plan.tag_count:
        update_sim_job_progress(job, total=plan.tag_count, label="Configuring Ignition tags")
        client = client or fluxy_client()
        apply_rehydration_plan(client, plan)
        update_sim_job_progress(job, current=plan.tag_count, label="Ignition tag configuration complete")
    return result


def update_sim_job_progress(
    job: SimJob,
    *,
    current: int | None = None,
    total: int | None = None,
    label: str | None = None,
) -> None:
    update_fields = ["updated_at"]
    if current is not None:
        job.progress_current = current
        update_fields.append("progress_current")
    if total is not None:
        job.progress_total = total
        update_fields.append("progress_total")
    if label is not None:
        job.progress_label = label[:255]
        update_fields.append("progress_label")
    job.save(update_fields=update_fields)


def complete_sim_job(job: SimJob, *, result: dict[str, Any]) -> None:
    job.status = SimJob.Status.COMPLETE
    job.result = result
    job.error = ""
    job.completed_at = timezone.now()
    job.progress_label = "Complete"
    job.save(update_fields=["status", "result", "error", "completed_at", "progress_label", "updated_at"])


def fail_sim_job(job: SimJob, *, error: str) -> None:
    job.status = SimJob.Status.FAILED
    job.error = error
    job.completed_at = timezone.now()
    job.progress_label = "Failed"
    job.save(update_fields=["status", "error", "completed_at", "progress_label", "updated_at"])


def latest_sim_jobs(limit: int = 8) -> list[SimJob]:
    return list(SimJob.objects.order_by("-created_at", "-id")[:limit])


def sim_job_summary() -> dict[str, int | str]:
    active_count = SimJob.objects.filter(status__in=[SimJob.Status.QUEUED, SimJob.Status.RUNNING]).count()
    failed_count = SimJob.objects.filter(status=SimJob.Status.FAILED).count()
    complete_count = SimJob.objects.filter(status=SimJob.Status.COMPLETE).count()
    state = "error" if failed_count else "warning" if active_count else "ok"
    return {
        "state": state,
        "active_count": active_count,
        "failed_count": failed_count,
        "complete_count": complete_count,
        "total_count": SimJob.objects.count(),
    }


def fluxy_client(*, tag_provider: str | None = None):
    import fluxy

    kwargs = {
        "base_url": os.getenv("FLUXY_BASE_URL", "http://localhost:8088/system/webdev/flux"),
        "token": os.getenv("FLUXY_TOKEN"),
    }
    if tag_provider is not None:
        kwargs["tag_provider"] = tag_provider
    return fluxy.Fluxy(**kwargs)


def submitted_rehydration_paths(selection_paths: list[str], selection_enabled: list[str]) -> list[str] | None:
    if not selection_paths:
        return None
    return [
        path.strip("/")
        for path, enabled in zip(selection_paths, selection_enabled, strict=False)
        if enabled == "1" and path.strip("/")
    ]


def submitted_removed_paths(selection_paths: list[str], selection_enabled: list[str]) -> list[str]:
    return [
        path.strip("/")
        for path, enabled in zip(selection_paths, selection_enabled, strict=False)
        if enabled != "1" and path.strip("/")
    ]


def atomic_tag_path(provider: str, path: str) -> bool:
    return TagNode.objects.filter(provider__name=provider, path=path.strip("/"), tag_type="AtomicTag").exists()
