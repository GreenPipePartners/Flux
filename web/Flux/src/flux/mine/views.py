from django.shortcuts import render

from .models import HmiScreenFact, MineRun, PlcControllerFact


def index(request):
    latest_run = MineRun.objects.order_by("-created_at").first()
    status = latest_run.status if latest_run else "warning"
    return render(
        request,
        "mine/index.html",
        {
            "platform_status": {"state": "ok" if status == MineRun.Status.COMPLETE else "warning", "label": status.title()},
            "plc_count": PlcControllerFact.objects.count(),
            "hmi_count": HmiScreenFact.objects.count(),
        },
    )
