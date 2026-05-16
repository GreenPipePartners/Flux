from django.http import JsonResponse
from django.shortcuts import render
from django.utils.dateparse import parse_datetime

from flux.base.runtime import TagSample

from .selectors import trace_sample_series


def index(request):
    samples = TagSample.objects.select_related("tag").order_by("-read_at")[:50]
    return render(
        request,
        "trace/index.html",
        {
            "samples": samples,
            "trace_chart": trace_sample_series(),
        },
    )


def live(request):
    return render(
        request,
        "trace/live.html",
        {
            "trace_chart": trace_sample_series(samples_per_tag=120),
            "poll_seconds": 5,
            "window_minutes": 15,
        },
    )


def live_samples(request):
    since = parse_datetime(request.GET.get("since", ""))
    return JsonResponse(trace_sample_series(samples_per_tag=120, since=since))
