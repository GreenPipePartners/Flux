from django.shortcuts import render

from .models import BuildRun


def index(request):
    latest_run = BuildRun.objects.order_by("-created_at").first()
    status = latest_run.status if latest_run else "warning"
    return render(
        request,
        "build/index.html",
        {
            "platform_status": {"state": "ok" if status == BuildRun.Status.COMPLETE else "warning", "label": status.title()},
            "cell_count": BuildRun.objects.filter(status=BuildRun.Status.COMPLETE).count(),
        },
    )
