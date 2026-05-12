from django.conf import settings
from django.shortcuts import render
from django.utils import timezone

from runtime.models import RuntimeTag


def index(request):
    tags = RuntimeTag.objects.select_related("latest_value", "schedule").order_by(
        "asset_name", "display_name"
    )
    now = timezone.now()
    stale_after_seconds = settings.STALE_AFTER_SECONDS
    stale_count = 0
    bad_quality_count = 0
    online_count = 0

    for tag in tags:
        value = getattr(tag, "latest_value", None)
        if value is None:
            stale_count += 1
            continue
        if value.quality_code.lower() != "good":
            bad_quality_count += 1
        if value.is_stale(now, stale_after_seconds):
            stale_count += 1
        else:
            online_count += 1

    return render(
        request,
        "live/index.html",
        {
            "tags": tags,
            "online_count": online_count,
            "stale_count": stale_count,
            "bad_quality_count": bad_quality_count,
            "stale_after_seconds": stale_after_seconds,
        },
    )
