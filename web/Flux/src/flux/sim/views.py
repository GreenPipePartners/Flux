from django.shortcuts import render

from .models import SimHistoryBackfill, SimSchedule, SimTag


def index(request):
    return render(
        request,
        "sim/index.html",
        {
            "schedules": SimSchedule.objects.prefetch_related("tags"),
            "tags": SimTag.objects.select_related("schedule"),
            "backfills": SimHistoryBackfill.objects.order_by("-created_at")[:10],
        },
    )
