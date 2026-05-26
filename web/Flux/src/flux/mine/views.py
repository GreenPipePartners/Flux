from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from flux.web_pulse import display_pulse_context

from .models import HmiScreenFact, MineRun, PlcControllerFact
from .services import mine_uploaded_source


def index(request):
    latest_run = MineRun.objects.order_by("-created_at").first()
    status = latest_run.status if latest_run else "warning"
    platform_status = {"state": "ok" if status == MineRun.Status.COMPLETE else "warning", "label": status.title()}
    plc_count = PlcControllerFact.objects.count()
    hmi_count = HmiScreenFact.objects.count()
    return render(
        request,
        "mine/index.html",
        {
            "platform_status": platform_status,
            "plc_count": plc_count,
            "hmi_count": hmi_count,
            "flux_web_pulse": display_pulse_context(
                source_label="Flux.mine run state",
                last_backend_at=latest_run.updated_at if latest_run else None,
                state=platform_status["state"],
                detail=f"{plc_count} PLCs mined · {hmi_count} HMIs mined",
            ),
        },
    )


@require_POST
def import_source(request):
    upload = request.FILES.get("source")
    source_type = (request.POST.get("source_type") or "auto").strip()
    label = (request.POST.get("label") or "").strip()
    if upload is None:
        messages.error(request, "Choose an L5K, L5X, or FactoryTalk ZIP file to import.")
        return redirect("mine:index")
    try:
        run = mine_uploaded_source(upload, source_type=source_type, label=label)
    except Exception as exc:
        messages.error(request, f"Mine import failed: {exc}")
        return redirect("mine:index")
    messages.success(request, f"Imported mine run {run.id}: {run.label or run.source_path}.")
    return redirect("mine:index")
