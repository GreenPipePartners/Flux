from django.shortcuts import render

from runtime.models import TagSample


def index(request):
    samples = TagSample.objects.select_related("tag").order_by("-read_at")[:50]
    return render(request, "trace/index.html", {"samples": samples})
