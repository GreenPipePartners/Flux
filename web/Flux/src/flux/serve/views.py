from django.shortcuts import render

from .models import ServeCommand, ServeHeartbeat


def index(request):
    heartbeats = ServeHeartbeat.objects.order_by("service_name", "instance_id")
    commands = ServeCommand.objects.select_related("requested_by").order_by("-requested_at")[:20]
    return render(
        request,
        "serve/index.html",
        {"heartbeats": heartbeats, "commands": commands},
    )
